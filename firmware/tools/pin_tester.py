"""Pin tester: click the ESP32's pins in a browser and see which solenoid moves.

    server\\.venv\\Scripts\\python firmware\\tools\\pin_tester.py              (finds the ESP32 itself)
    server\\.venv\\Scripts\\python firmware\\tools\\pin_tester.py --port COM5

Needs the pin finder on the board (scripts\\flash-firmware.ps1 -PinFinder) and the serial
port free, so close any serial monitor first. Opens http://localhost:8765.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import re
import threading
import time
import webbrowser
from collections import deque
from contextlib import asynccontextmanager

import serial
import uvicorn
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from serial.tools import list_ports

HERE = pathlib.Path(__file__).resolve().parent
PAGE = HERE / "pin_tester.html"
CONFIG_H = HERE.parent / "dynabraille_esp32" / "config.h"
CONFIG_EXAMPLE = HERE.parent / "dynabraille_esp32" / "config.example.h"
OUTPUT_PINS = {2, 4, 5, 12, 13, 14, 15, 16, 17, 18, 19, 21, 22, 23, 25, 26, 27, 32, 33, 1}
ESP32_USB = {(0x10C4, 0xEA60), (0x1A86, 0x7523), (0x1A86, 0x55D4), (0x0403, 0x6001)}


def find_port() -> str | None:
    for port in list_ports.comports():
        if (port.vid, port.pid) in ESP32_USB or port.vid == 0x303A:
            return port.device
    return None


class SerialLink:
    """Owns the serial port on a thread; lines go to the browser, commands come back."""

    def __init__(self, port: str | None, loop: asyncio.AbstractEventLoop, publish):
        self.port_spec, self.loop, self.publish = port, loop, publish
        self.status = {"state": "starting", "port": port}
        self._serial: serial.Serial | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        threading.Thread(target=self._run, daemon=True).start()

    def _set(self, **status) -> None:
        self.status = status
        self.loop.call_soon_threadsafe(self.publish, {"type": "status", **status})

    def _run(self) -> None:
        while True:
            port = self.port_spec or find_port()
            if not port:
                self._set(state="missing", port=None)
                time.sleep(2)
                continue
            try:
                ser = serial.Serial()
                ser.port, ser.baudrate, ser.timeout = port, 115200, 0.2
                ser.dtr = ser.rts = False  # these lines reset this board into its bootloader
                ser.open()
            except serial.SerialException as exc:
                busy = "denied" in str(exc).lower() or "busy" in str(exc).lower()
                self._set(state="busy" if busy else "error", port=port, detail=str(exc))
                time.sleep(2)
                continue
            self._serial = ser
            self._set(state="connected", port=port)
            self.send("x")  # start from a known state: everything off
            try:
                while True:
                    raw = ser.readline()
                    if raw:
                        line = raw.decode("utf-8", "replace").rstrip("\r\n")
                        if line.strip() and line.strip() != ">":
                            self.loop.call_soon_threadsafe(self.publish, {"type": "line", "text": line})
            except serial.SerialException as exc:
                self._set(state="error", port=port, detail=str(exc))
            finally:
                self._serial = None
                try:
                    ser.close()
                except Exception:
                    pass
            time.sleep(1)

    def send(self, text: str) -> bool:
        with self._lock:
            if not self._serial:
                return False
            self._serial.write((text + "\n").encode())
            return True


class SavePins(BaseModel):
    pins: list[int] = []  # S1..S6, or empty to leave them as they are
    button: int | None = None
    button_to_3v3: bool | None = None


def saved_solenoid_pins() -> list[int]:
    """SOLENOID_PINS from config.h, so the button search can leave those pins alone."""
    if not CONFIG_H.exists():
        return []
    match = re.search(r"#define SOLENOID_PINS \{([^}]*)\}", CONFIG_H.read_text(encoding="utf-8"))
    return [int(v) for v in re.findall(r"\d+", match.group(1))] if match else []


def save_config(pins: list[int], button: int | None, button_to_3v3: bool | None) -> list[str]:
    if not CONFIG_H.exists():
        CONFIG_H.write_text(CONFIG_EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    text = CONFIG_H.read_text(encoding="utf-8")
    lines = []
    if pins:
        lines.append("#define SOLENOID_PINS {" + ", ".join(map(str, pins)) + "}")
        text = re.sub(r"#define SOLENOID_PINS \{[^}]*\}", lines[-1], text)
    if button is not None:
        lines.append(f"#define BUTTON_PIN {button}")
        text = re.sub(r"#define BUTTON_PIN -?\d+", lines[-1], text)
    if button_to_3v3 is not None:
        lines.append(f"#define BUTTON_ACTIVE_HIGH {int(button_to_3v3)}")
        if re.search(r"#define BUTTON_ACTIVE_HIGH \d", text):
            text = re.sub(r"#define BUTTON_ACTIVE_HIGH \d", lines[-1], text)
        else:
            text = re.sub(r"(#define BUTTON_PIN -?\d+[^
]*
)", r"" + lines[-1] + "
", text)
    CONFIG_H.write_text(text, encoding="utf-8")
    return lines


def create_app(port: str | None) -> FastAPI:
    clients: set[WebSocket] = set()
    history: deque[str] = deque(maxlen=300)
    state: dict = {}

    def publish(message: dict) -> None:
        if message["type"] == "line":
            history.append(message["text"])
        data = json.dumps(message)
        for ws in list(clients):
            asyncio.ensure_future(ws.send_text(data))

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        state["link"] = SerialLink(port, asyncio.get_running_loop(), publish)
        state["link"].start()
        yield

    app = FastAPI(title="DynaBraille pin tester", lifespan=lifespan)

    @app.get("/", response_class=HTMLResponse)
    async def page():
        return PAGE.read_text(encoding="utf-8")

    @app.post("/api/save")
    async def save(body: SavePins):
        if body.pins and (len(body.pins) != 6 or len(set(body.pins)) != 6 or not set(body.pins) <= OUTPUT_PINS):
            raise HTTPException(422, "Need six different output GPIOs, one per solenoid.")
        if not body.pins and body.button is None:
            raise HTTPException(422, "Nothing to save yet.")
        lines = save_config(body.pins, body.button, body.button_to_3v3)
        return {"saved": str(CONFIG_H), "lines": lines}

    @app.websocket("/ws")
    async def socket(ws: WebSocket):
        await ws.accept()
        clients.add(ws)
        link: SerialLink = state["link"]
        await ws.send_text(json.dumps({"type": "status", **link.status}))
        await ws.send_text(json.dumps({"type": "history", "lines": list(history)}))
        try:
            while True:
                message = json.loads(await ws.receive_text())
                cmd = message.get("cmd")
                if cmd in ("p", "on", "off"):
                    link.send(f"{cmd} {int(message['gpio'])}")
                elif cmd == "raw" and message.get("text") == "b":
                    skip = saved_solenoid_pins()  # don't pull the solenoid gates up
                    link.send("b " + ",".join(map(str, skip)) if skip else "b")
                elif cmd == "raw" and message.get("text") in ("x", "h"):
                    link.send(message["text"])
        except WebSocketDisconnect:
            pass
        finally:
            clients.discard(ws)

    return app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", help="serial port, e.g. COM5 (default: find the ESP32)")
    parser.add_argument("--http", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    url = f"http://localhost:{args.http}/"
    print(f"Pin tester on {url}  (Ctrl+C to stop and free the serial port)")
    if not args.no_browser:
        threading.Timer(1.0, webbrowser.open, [url]).start()
    uvicorn.run(create_app(args.port), host="127.0.0.1", port=args.http, log_level="warning")


if __name__ == "__main__":
    main()
