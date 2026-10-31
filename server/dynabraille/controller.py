"""The processing server's brain: camera -> scene -> braille cell + speech."""
from __future__ import annotations

import asyncio
import itertools
import logging
import time
from collections import deque
from dataclasses import dataclass, field

from . import __version__, braille
from .devices import DeviceManager
from .elevenlabs import ElevenLabs
from .hub import Hub
from .network import lan_addresses
from .scene import Detection, FocusTracker, braille_listing, summarize
from .settings import Preferences, PreferenceStore, Settings
from .vision import VisionService

log = logging.getLogger(__name__)
SIM_HOLD_MS = 8000  # mirrors the firmware's STATIC_HOLD_MS for the simulated cell


@dataclass
class BrailleJob:
    id: int
    text: str
    source: str  # camera | capture | assistant | manual
    cells: list[braille.Cell]
    char_ms: int
    gap_ms: int
    index: int = -1
    active: bool = True
    started_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "text": self.text, "source": self.source,
            "cells": [c.to_dict() for c in self.cells],
            "char_ms": self.char_ms, "gap_ms": self.gap_ms,
            "index": self.index, "active": self.active, "started_at": self.started_at,
            "duration_ms": len(self.cells) * (self.char_ms + self.gap_ms),
        }


class Controller:
    def __init__(self, settings: Settings, prefs: PreferenceStore | None = None):
        self.settings = settings
        self.prefs = prefs or PreferenceStore()
        self.hub = Hub()
        self.devices = DeviceManager(on_event=self._on_device_event, on_change=self._devices_changed)
        self.vision = VisionService(settings, on_status=self._vision_changed)
        self.elevenlabs = ElevenLabs(settings)
        self.focus = FocusTracker(stable_ms=self.prefs.value.focus_stable_ms)

        self.detections: list[Detection] = []
        self.detections_at = 0.0
        self.job: BrailleJob | None = None
        self.mask = 0
        self.rest = True  # every solenoid off (the cell's idle state)
        self.capture: dict | None = None
        self.capture_jpeg: bytes | None = None
        self.events: deque[dict] = deque(maxlen=60)
        self.started_at = time.time()
        self._ids = itertools.count(1)
        self._sim_task: asyncio.Task | None = None
        self._pending_camera_word: str | None = None
        self._tasks: list[asyncio.Task] = []

    # ------------------------------------------------------------------ lifecycle

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        self.vision.start(loop, self.process_frame)
        self._tasks.append(loop.create_task(self._heartbeat()))

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        self.vision.stop()
        await self.elevenlabs.close()

    async def _heartbeat(self) -> None:
        while True:
            await asyncio.sleep(1)
            self.hub.broadcast({"type": "vision.status", "vision": self.vision.status()})

    # ------------------------------------------------------------------ state for clients

    def urls(self) -> dict:
        s = self.settings
        ips = lan_addresses()
        hosts = ([f"{s.mdns_hostname}.local"] if s.mdns_enabled else []) + ips
        return {
            "dashboard": [f"http://{h}:{s.http_port}/" for h in ["localhost", *ips]],
            "camera": [f"https://{h}:{s.https_port}/camera" for h in hosts] if s.https_port else [],
            "ca_certificate": [f"http://{h}:{s.http_port}/ca.crt" for h in ips],
            "device_ws": [f"ws://{h}:{s.http_port}/ws/device" for h in ips],
        }

    def snapshot(self) -> dict:
        return {
            "server": {"version": __version__, "started_at": self.started_at, "urls": self.urls()},
            "prefs": self.prefs.value.model_dump(),
            "devices": self.devices.snapshot(),
            "vision": self.vision.status(),
            "detections": [d.to_dict() for d in self.detections] if self.vision.camera_online else [],
            "focus": self.focus.current.to_dict() if self.focus.current else None,
            "job": self.job.to_dict() if self.job else None,
            "mask": self.mask,
            "rest": self.rest,
            "capture": self.capture,
            "assistant": self.elevenlabs.status(),
            "clients": dict(self.hub.roles()),
            "events": list(self.events),
        }

    def note(self, kind: str, text: str, level: str = "info") -> None:
        entry = {"t": time.time(), "kind": kind, "text": text, "level": level}
        self.events.append(entry)
        self.hub.broadcast({"type": "event", "entry": entry})
        log.log(logging.WARNING if level == "warn" else logging.INFO, "[%s] %s", kind, text)

    def update_prefs(self, changes: dict) -> Preferences:
        prefs = self.prefs.update(changes)
        self.focus.stable_ms = prefs.focus_stable_ms
        self.hub.broadcast({"type": "prefs", "prefs": prefs.model_dump()})
        if {"hold_duty", "pull_in_ms"} & changes.keys() and self.devices.online:
            asyncio.get_running_loop().create_task(self.devices.send_all(self.device_config()))
        return prefs

    def device_config(self) -> dict:
        """Settings the cell should use; only the ones the user has set."""
        prefs = self.prefs.value
        config = {"type": "config"}
        if prefs.hold_duty is not None:
            config["hold_duty"] = prefs.hold_duty
        if prefs.pull_in_ms is not None:
            config["pull_in_ms"] = prefs.pull_in_ms
        return config

    def _devices_changed(self) -> None:
        self.hub.broadcast({"type": "devices", "devices": self.devices.snapshot()})
        # Mirror what the physical cell reports (e.g. all pins up at rest on this build).
        first = next(iter(self.devices.sessions.values()), None)
        if first is not None and not (self.job and self.job.active):
            self._set_mask(first.mask, first.rest)

    def _vision_changed(self) -> None:
        self.hub.broadcast({"type": "vision.status", "vision": self.vision.status()})
        if self.vision.detector_state == "ready":
            self.note("vision", f"Object detection ready ({self.vision.settings.yolo_model} on {self.vision.device})")
        elif self.vision.detector_error:
            self.note("vision", f"Object detection unavailable: {self.vision.detector_error}", "warn")

    # ------------------------------------------------------------------ braille output

    async def show_text(self, text: str, source: str = "manual") -> BrailleJob:
        cells = braille.encode(text)
        if not cells:
            raise ValueError("Nothing in that text can be shown in braille.")
        prefs = self.prefs.value
        await self._cancel_current()
        job = BrailleJob(next(self._ids), text.strip(), source, cells, prefs.char_ms, prefs.gap_ms)
        self.job = job
        self.hub.broadcast({"type": "braille.job", "job": job.to_dict()})
        if source != "camera":
            self.note("braille", f"Showing '{job.text}' ({source})")
        if self.devices.online:
            await self.devices.send_all({
                "type": "show", "id": job.id, "cells": [c.mask for c in cells],
                "char_ms": job.char_ms, "gap_ms": job.gap_ms,
            })
        else:
            self._sim_task = asyncio.create_task(self._simulate(job))
        return job

    async def show_cell(self, mask: int, hold_ms: int | None = None) -> None:
        await self._cancel_current()
        hold = min(hold_ms or SIM_HOLD_MS, SIM_HOLD_MS)
        if self.devices.online:
            await self.devices.send_all({"type": "cell", "mask": mask, "hold_ms": hold})
        else:
            self._sim_task = asyncio.create_task(self._simulate_hold(mask, hold))

    async def test_dot(self, dot: int) -> None:
        await self._cancel_current()
        if self.devices.online:
            await self.devices.send_all({"type": "test", "dot": dot, "ms": 600})
        else:
            self._sim_task = asyncio.create_task(self._simulate_hold(1 << (dot - 1), 600))

    async def stop_braille(self) -> None:
        await self._cancel_current()
        self._pending_camera_word = None
        if self.devices.online:
            await self.devices.send_all({"type": "stop"})
        else:
            self._set_mask(0, rest=True)

    async def replay(self) -> BrailleJob | None:
        if not self.job:
            return None
        return await self.show_text(self.job.text, self.job.source)

    async def _cancel_current(self) -> None:
        if self._sim_task and not self._sim_task.done():
            self._sim_task.cancel()
            try:
                await self._sim_task
            except asyncio.CancelledError:
                pass
        if self.job and self.job.active:
            self._finish(self.job.id, cancelled=True)

    async def _simulate(self, job: BrailleJob) -> None:
        """No cell connected: play the same timeline the firmware would."""
        try:
            for index, cell in enumerate(job.cells):
                self._progress(job.id, index)
                self._set_mask(cell.mask)
                await asyncio.sleep(job.char_ms / 1000)
                self._set_mask(0)
                await asyncio.sleep(job.gap_ms / 1000)
            self._set_mask(0, rest=True)
            self._finish(job.id, cancelled=False)
        except asyncio.CancelledError:
            self._set_mask(0, rest=True)
            raise

    async def _simulate_hold(self, mask: int, hold_ms: int) -> None:
        try:
            self._set_mask(mask)
            await asyncio.sleep(hold_ms / 1000)
        finally:
            self._set_mask(0, rest=True)

    def _set_mask(self, mask: int, rest: bool = False) -> None:
        if mask != self.mask or rest != self.rest:
            self.mask, self.rest = mask, rest
            self.hub.broadcast({"type": "braille.dots", "mask": mask, "rest": rest})

    def _progress(self, job_id: int, index: int) -> None:
        if self.job and self.job.id == job_id:
            self.job.index = index
            self.hub.broadcast({"type": "braille.progress", "id": job_id, "index": index})

    def _finish(self, job_id: int, cancelled: bool) -> None:
        if not (self.job and self.job.id == job_id and self.job.active):
            return
        self.job.active = False
        self.hub.broadcast({"type": "braille.done", "id": job_id, "cancelled": cancelled})
        if not cancelled and self._pending_camera_word:
            asyncio.get_running_loop().create_task(self._flush_pending_camera_word())

    async def _on_device_event(self, device_id: str, message: dict) -> None:
        kind = message.get("type")
        if kind == "hello":
            config = self.device_config()
            if len(config) > 1 and device_id in self.devices.sessions:
                await self.devices.sessions[device_id].send(config)
        elif kind == "dots":
            self._set_mask(int(message.get("mask", 0)), bool(message.get("rest", False)))
        elif kind == "progress":
            self._progress(message.get("id"), int(message.get("index", 0)))
        elif kind == "done":
            self._finish(message.get("id"), bool(message.get("cancelled")))
        elif kind == "button":
            await self.handle_button(str(message.get("event", "")), device_id)
        elif kind == "error":
            self.note("device", f"{device_id}: {message.get('message')}", "warn")

    # ------------------------------------------------------------------ tactile button

    async def handle_button(self, event: str, device_id: str | None = None) -> None:
        self.hub.broadcast({"type": "button", "event": event, "device_id": device_id})
        if event == "short":
            self.note("button", "Button: capture the scene")
            await self.capture_scene(trigger="button")
        elif event == "double":
            self.note("button", "Double press: repeat last word")
            await self.replay()
        elif event == "long":
            prefs = self.update_prefs({"auto_braille": not self.prefs.value.auto_braille})
            state = "on" if prefs.auto_braille else "paused"
            self.note("button", f"Long press: camera braille {state}")
            self.hub.speak(f"Camera braille {state}.", intent="notice")

    # ------------------------------------------------------------------ vision

    async def process_frame(self, jpeg: bytes, source: str) -> dict:
        await self.vision.publish(jpeg, source)
        detections, infer_ms = await self.vision.detect(jpeg, self.prefs.value.min_confidence)
        self.detections, self.detections_at = detections, time.monotonic()
        changed = self.focus.update(detections)
        focus = self.focus.current.to_dict() if self.focus.current else None
        payload = [d.to_dict() for d in detections]
        self.hub.broadcast({"type": "vision.detections", "detections": payload, "focus": focus,
                            "infer_ms": round(infer_ms, 1)}, role="dashboard")
        if changed:
            await self._on_focus(changed)
        return {"detections": payload, "focus": focus, "infer_ms": round(infer_ms, 1)}

    async def capture_scene(self, trigger: str = "button") -> dict:
        """Freeze the current frame, find everything in it, spell it on the cell and say it."""
        if not self.vision.camera_online or not self.vision.latest_jpeg:
            message = "The camera isn't connected. Open the camera page on the iPhone."
            self.hub.speak(message, intent="notice")
            raise LookupError(message)
        if self.vision.detector_state != "ready":
            message = "Object detection is still starting. Try again in a moment."
            self.hub.speak(message, intent="notice")
            raise LookupError(message)

        jpeg = self.vision.latest_jpeg
        detections, infer_ms = await self.vision.detect(jpeg, self.prefs.value.min_confidence)
        detections.sort(key=Detection.focus_score, reverse=True)
        text = braille_listing(detections)
        self.capture_jpeg = jpeg
        self.capture = {
            "id": self.vision.frame_id, "at": time.time(), "trigger": trigger,
            "summary": summarize(detections), "braille_text": text,
            "detections": [d.to_dict() for d in detections], "infer_ms": round(infer_ms, 1),
        }
        self.hub.broadcast({"type": "scene.capture", "capture": self.capture})
        self.note("capture", f"Captured: {text}")
        await self.show_text(text, "capture")
        self.hub.speak(self.capture["summary"], intent="capture")
        return self.capture

    async def _on_focus(self, det: Detection) -> None:
        self.hub.broadcast({"type": "scene.focus", "focus": det.to_dict(), "word": det.braille_word})
        self.note("vision", f"Now in focus: {det.describe()}")
        prefs = self.prefs.value
        if prefs.announce:
            where = "ahead" if det.position == "ahead" else f"on your {det.position}"
            self.hub.speak(f"{det.label} {where}", intent="announce")
        if prefs.auto_braille:
            await self._show_camera_word(det.braille_word)

    async def _show_camera_word(self, word: str) -> None:
        # Words the user or assistant asked for are never cut off by the camera.
        if self.job and self.job.active and self.job.source != "camera":
            self._pending_camera_word = word
            return
        self._pending_camera_word = None
        await self.show_text(word, "camera")

    async def _flush_pending_camera_word(self) -> None:
        word, self._pending_camera_word = self._pending_camera_word, None
        current = self.focus.current
        if word and self.prefs.value.auto_braille and current and current.braille_word == word:
            await self.show_text(word, "camera")

    def scene_report(self) -> dict:
        online = self.vision.camera_online
        fresh = online and time.monotonic() - self.detections_at < 3
        detections = sorted(self.detections if fresh else [], key=Detection.focus_score, reverse=True)
        if not online:
            summary = "The camera isn't connected, so I can't see anything right now."
        elif self.vision.detector_state != "ready":
            summary = "The camera is on, but object detection isn't ready yet."
        else:
            summary = summarize(detections)
        lux = next((d.lux for d in self.devices.sessions.values() if d.lux is not None), None)
        return {
            "camera_online": online,
            "detector": self.vision.detector_state,
            "summary": summary,
            "objects": [d.to_dict() for d in detections],
            "focus": self.focus.current.to_dict() if self.focus.current and fresh else None,
            "light_level_lux": lux,
        }
