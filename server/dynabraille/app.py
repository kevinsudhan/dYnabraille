"""HTTP API, WebSockets and the web UI."""
from __future__ import annotations

import asyncio
import json
import logging
import secrets
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__, braille
from .controller import Controller
from .elevenlabs import ElevenLabsError
from .network import Advertiser, ca_der, CERT_DIR
from .serial_link import SerialLink
from .settings import Settings

log = logging.getLogger(__name__)

MAX_SPEECH_BYTES = 4_000_000  # about a minute of compressed speech


class ShowText(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    source: Literal["manual", "assistant"] = "manual"


class ShowCell(BaseModel):
    dots: list[int] = Field(default_factory=list)
    hold_ms: int | None = Field(None, ge=50, le=4000)


class TestDot(BaseModel):
    dot: int = Field(ge=1, le=6)


class PowerSolenoids(BaseModel):
    on: list[int] = Field(default_factory=list)  # solenoid numbers in the hardware's own numbering
    hold_ms: int = Field(4000, ge=200, le=8000)


class Light(BaseModel):
    mode: Literal["auto", "on", "off"]


class PrefsPatch(BaseModel):
    char_ms: int | None = None
    gap_ms: int | None = None
    auto_braille: bool | None = None
    announce: bool | None = None
    min_confidence: float | None = None
    focus_stable_ms: int | None = None
    hold_duty: int | None = None
    pull_in_ms: int | None = None


class Speech(BaseModel):
    text: str = Field(min_length=1, max_length=400)


def create_app(settings: Settings | None = None, controller: Controller | None = None) -> FastAPI:
    settings = settings or Settings()
    ctl = controller or Controller(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        loop = asyncio.get_running_loop()
        ctl.start(loop)
        serial_link = advertiser = None
        if settings.device_serial_port:
            serial_link = SerialLink(settings.device_serial_port, settings.device_serial_baud, ctl.devices, loop)
            serial_link.start()
        if settings.mdns_enabled:
            advertiser = Advertiser(settings.mdns_hostname, settings.http_port, settings.https_port)
            await advertiser.start()
        if settings.device_token == "change-me":
            ctl.note("server", "DEVICE_TOKEN is still 'change-me' - set your own in server/.env", "warn")
        yield
        if serial_link:
            serial_link.stop()
        if advertiser:
            await advertiser.stop()
        await ctl.stop()

    app = FastAPI(title="DynaBraille", version=__version__, lifespan=lifespan)
    app.state.controller = ctl

    # ------------------------------------------------------------------ WebSockets

    @app.websocket("/ws/device")
    async def device_socket(ws: WebSocket):
        """The ESP32 braille cell. Authenticated with DEVICE_TOKEN."""
        token = ws.query_params.get("token", "")
        if not secrets.compare_digest(token.encode(), settings.device_token.encode()):
            log.warning("rejected device from %s: bad token", ws.client.host if ws.client else "?")
            await ws.close(code=4401)
            return
        await ws.accept()
        device_id = ws.query_params.get("id") or f"device-{ws.client.host}"

        async def send(message: dict) -> None:
            await ws.send_text(json.dumps(message))

        ctl.devices.attach(device_id, "wifi", send)
        ctl.note("device", f"{device_id} connected over WiFi ({ws.client.host})")
        await send({"type": "welcome", "proto": 2, "server": __version__})
        try:
            while True:
                try:
                    message = json.loads(await ws.receive_text())
                except json.JSONDecodeError:
                    continue
                if isinstance(message, dict):
                    await ctl.devices.handle(device_id, "wifi", message)
        except WebSocketDisconnect:
            pass
        finally:
            ctl.devices.detach(device_id, "wifi", send)
            ctl.note("device", f"{device_id} disconnected")

    @app.websocket("/ws/camera")
    async def camera_socket(ws: WebSocket):
        """iPhone camera page. Binary frames: 4-byte big-endian sequence number + JPEG."""
        await ws.accept()
        who = ws.client.host if ws.client else "?"
        ctl.note("camera", f"Phone camera connected ({who})")
        try:
            while True:
                message = await ws.receive()
                if message["type"] == "websocket.disconnect":
                    break
                data = message.get("bytes")
                if not data or len(data) < 5:
                    continue
                seq = int.from_bytes(data[:4], "big")
                result = await ctl.process_frame(data[4:], "iphone")
                await ws.send_text(json.dumps({"type": "result", "seq": seq, **result}))
        except WebSocketDisconnect:
            pass
        finally:
            ctl.note("camera", f"Phone camera disconnected ({who})")

    @app.websocket("/ws/ui")
    async def ui_socket(ws: WebSocket):
        await ws.accept()
        role = ws.query_params.get("role", "dashboard")
        await ctl.hub.serve(ws, role if role in ("dashboard", "phone") else "dashboard", ctl.snapshot())

    # ------------------------------------------------------------------ REST

    @app.get("/api/health")
    async def health():
        return {"ok": True, "version": __version__}

    @app.get("/api/state")
    async def state():
        return ctl.snapshot()

    @app.post("/api/braille/show")
    async def braille_show(body: ShowText):
        try:
            job = await ctl.show_text(body.text, body.source)
        except ValueError as exc:
            raise HTTPException(422, str(exc))
        return job.to_dict()

    @app.post("/api/braille/cell")
    async def braille_cell(body: ShowCell):
        await ctl.show_cell(braille.dots_to_mask(body.dots), body.hold_ms)
        return {"ok": True}

    @app.post("/api/braille/stop")
    async def braille_stop():
        await ctl.stop_braille()
        return {"ok": True}

    @app.post("/api/braille/replay")
    async def braille_replay():
        job = await ctl.replay()
        if not job:
            raise HTTPException(409, "Nothing has been shown yet.")
        return job.to_dict()

    @app.get("/api/braille/preview")
    async def braille_preview(text: str = Query(max_length=500)):
        return {"cells": [c.to_dict() for c in braille.encode(text)]}

    @app.post("/api/device/test")
    async def device_test(body: TestDot):
        await ctl.test_dot(body.dot)
        return {"ok": True}

    @app.post("/api/device/solenoids")
    async def device_solenoids(body: PowerSolenoids):
        """Power exactly these solenoids (S1..S6) at once, e.g. to see how many the supply can hold."""
        session = next(iter(ctl.devices.sessions.values()), None)
        if session is None:
            raise HTTPException(409, "No braille cell connected.")
        if not set(body.on) <= set(range(1, 7)):
            raise HTTPException(422, "Solenoids are numbered 1 to 6.")
        if not body.on:
            await ctl.stop_braille()
            return {"ok": True, "on": []}
        # The firmware takes braille dots; translate through the cell's own layout and polarity.
        mask = 0
        for dot, solenoid in enumerate(session.dot_to_solenoid, start=1):
            powered = solenoid in body.on
            if powered == session.solenoid_on_raises:
                mask |= 1 << (dot - 1)
        await ctl.show_cell(mask, body.hold_ms)  # the firmware releases everything after hold_ms
        return {"ok": True, "on": sorted(body.on), "hold_ms": body.hold_ms}

    @app.post("/api/device/selftest")
    async def device_selftest():
        """Run the power-on solenoid sequence (S1..S6, one at a time) again."""
        if not ctl.devices.online:
            raise HTTPException(409, "No braille device connected.")
        await ctl.stop_braille()
        await ctl.devices.send_all({"type": "selftest"})
        return {"ok": True}

    @app.post("/api/device/light")
    async def device_light(body: Light):
        if not ctl.devices.online:
            raise HTTPException(409, "No braille device connected.")
        await ctl.devices.send_all({"type": "light", "mode": body.mode})
        return {"ok": True}

    @app.post("/api/device/button")
    async def device_button(event: Literal["short", "double", "long"]):
        """Same as pressing the tactile button; handy without hardware."""
        await ctl.handle_button(event, None)
        return {"ok": True}

    @app.get("/api/prefs")
    async def get_prefs():
        return ctl.prefs.value.model_dump()

    @app.patch("/api/prefs")
    async def patch_prefs(body: PrefsPatch):
        try:
            return ctl.update_prefs(body.model_dump(exclude_none=True)).model_dump()
        except ValueError as exc:
            raise HTTPException(422, str(exc))

    @app.get("/api/scene")
    async def scene():
        return ctl.scene_report()

    @app.post("/api/scene/capture")
    async def scene_capture(trigger: Literal["dashboard", "phone"] = "dashboard"):
        """Same as the tactile button: capture this frame, braille + speak what's in it."""
        try:
            return await ctl.capture_scene(trigger=trigger)
        except LookupError as exc:
            raise HTTPException(409, str(exc))

    @app.get("/api/assistant/session")
    async def assistant_session(connection: Literal["webrtc", "websocket"] = "webrtc"):
        try:
            return await ctl.elevenlabs.conversation_credentials(connection)
        except ElevenLabsError as exc:
            raise HTTPException(exc.status, str(exc))

    @app.post("/api/tts")
    async def tts(body: Speech):
        try:
            audio = await ctl.elevenlabs.tts(body.text)
        except ElevenLabsError as exc:
            raise HTTPException(exc.status, str(exc))
        return Response(audio, media_type="audio/mpeg", headers={"Cache-Control": "no-store"})

    @app.post("/api/stt")
    async def stt(request: Request):
        """Transcribe one hold-to-talk recording (raw audio body, e.g. audio/mp4 from Safari)."""
        audio = await request.body()
        if len(audio) < 200:
            raise HTTPException(422, "The recording is empty.")
        if len(audio) > MAX_SPEECH_BYTES:
            raise HTTPException(413, "That recording is too long. Keep it under a minute.")
        try:
            text = await ctl.elevenlabs.stt(audio, request.headers.get("content-type", ""))
        except ElevenLabsError as exc:
            raise HTTPException(exc.status, str(exc))
        return {"text": text}

    @app.get("/api/vision/stream")
    async def vision_stream():
        return StreamingResponse(ctl.vision.mjpeg(), media_type="multipart/x-mixed-replace; boundary=frame",
                                 headers={"Cache-Control": "no-store"})

    @app.get("/api/vision/frame.jpg")
    async def vision_frame():
        if not ctl.vision.latest_jpeg:
            raise HTTPException(404, "No camera frame yet.")
        return Response(ctl.vision.latest_jpeg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})

    @app.get("/api/vision/capture.jpg")
    async def vision_capture():
        if not ctl.capture_jpeg:
            raise HTTPException(404, "Nothing captured yet.")
        return Response(ctl.capture_jpeg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})

    @app.get("/ca.crt")
    async def ca_certificate():
        """Install on the iPhone once so it trusts this server's HTTPS certificate."""
        path = CERT_DIR / "ca.pem"
        if not path.exists():
            raise HTTPException(404, "HTTPS is disabled (HTTPS_PORT=0).")
        return Response(ca_der(path), media_type="application/x-x509-ca-cert",
                        headers={"Content-Disposition": 'attachment; filename="DynaBraille-CA.crt"'})

    # ------------------------------------------------------------------ web UI

    dist = settings.web_dist
    if (dist / "index.html").exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        async def spa(path: str):
            file = (dist / path).resolve()
            if path and file.is_file() and dist.resolve() in file.parents:
                return FileResponse(file)
            return FileResponse(dist / "index.html", headers={"Cache-Control": "no-cache"})
    else:
        @app.get("/", include_in_schema=False)
        async def not_built():
            return HTMLResponse(
                "<h1>DynaBraille server is running</h1><p>The web UI isn't built yet. Run "
                "<code>npm install && npm run build</code> in <code>web/</code>, or use the dev "
                "server: <code>npm run dev</code> (http://localhost:5173).</p>")

    return app
