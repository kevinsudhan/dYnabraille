"""Connected braille cells (ESP32). One device can be linked over WiFi and USB at once."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable

log = logging.getLogger(__name__)

Sender = Callable[[dict], Awaitable[None]]
STATUS_FIELDS = ("rssi", "ip", "uptime_ms", "heap", "lux", "light_aid", "battery_v", "battery_pct",
                 "hold_duty", "pull_in_ms")


@dataclass
class DeviceSession:
    id: str
    name: str = "Braille cell"
    fw: str = "?"
    ip: str | None = None
    features: dict = field(default_factory=dict)
    max_on_ms: int | None = None
    rest_mask: int = 0  # what the cell physically shows with every solenoid off
    dot_to_solenoid: list[int] = field(default_factory=lambda: [1, 2, 3, 4, 5, 6])
    solenoid_on_raises: bool = True
    hold_duty: int | None = None
    pull_in_ms: int | None = None
    pwm: bool | None = None
    rssi: int | None = None
    uptime_ms: int | None = None
    heap: int | None = None
    lux: float | None = None
    light_aid: bool | None = None
    battery_v: float | None = None
    battery_pct: int | None = None
    mask: int = 0
    rest: bool = True
    connected_at: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.monotonic)
    links: dict[str, Sender] = field(default_factory=dict)

    @property
    def transport(self) -> str:
        # WiFi is preferred; the firmware mirrors every message to USB serial too.
        return "wifi" if "wifi" in self.links else "usb"

    async def send(self, message: dict) -> None:
        await self.links[self.transport](message)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "fw": self.fw, "ip": self.ip,
            "transport": self.transport, "links": sorted(self.links),
            "features": self.features, "max_on_ms": self.max_on_ms, "rest_mask": self.rest_mask,
            "dot_to_solenoid": self.dot_to_solenoid, "solenoid_on_raises": self.solenoid_on_raises,
            "hold_duty": self.hold_duty, "pull_in_ms": self.pull_in_ms, "pwm": self.pwm,
            "rssi": self.rssi, "uptime_ms": self.uptime_ms, "heap": self.heap,
            "lux": self.lux, "light_aid": self.light_aid,
            "battery_v": self.battery_v, "battery_pct": self.battery_pct,
            "mask": self.mask, "rest": self.rest, "connected_at": self.connected_at,
        }


class DeviceManager:
    def __init__(self, on_event: Callable[[str, dict], Awaitable[None]],
                 on_change: Callable[[], None]):
        self.sessions: dict[str, DeviceSession] = {}
        self._on_event = on_event  # (device_id, message) for dots/progress/done/button/...
        self._on_change = on_change  # device list or status changed

    @property
    def online(self) -> bool:
        return bool(self.sessions)

    def attach(self, device_id: str, transport: str, sender: Sender) -> DeviceSession:
        session = self.sessions.get(device_id)
        if session is None:
            session = self.sessions[device_id] = DeviceSession(id=device_id)
            log.info("device %s connected over %s", device_id, transport)
        session.links[transport] = sender
        session.last_seen = time.monotonic()
        self._on_change()
        return session

    def detach(self, device_id: str, transport: str, sender: Sender | None = None) -> None:
        session = self.sessions.get(device_id)
        if not session:
            return
        if sender is not None and session.links.get(transport) is not sender:
            return  # the device already reconnected on a newer socket
        session.links.pop(transport, None)
        if not session.links:
            del self.sessions[device_id]
            log.info("device %s disconnected", device_id)
        self._on_change()

    async def handle(self, device_id: str, transport: str, message: dict) -> None:
        session = self.sessions.get(device_id)
        if session is None:
            return
        session.last_seen = time.monotonic()
        if transport != session.transport:
            return  # same message already arrived on the preferred link

        kind = message.get("type")
        if kind == "hello":
            session.name = message.get("name") or session.name
            session.fw = message.get("fw") or session.fw
            session.ip = message.get("ip") or session.ip
            session.features = message.get("features") or {}
            session.max_on_ms = message.get("max_on_ms")
            session.rest_mask = int(message.get("rest_mask", 0))
            session.dot_to_solenoid = message.get("dot_to_solenoid") or session.dot_to_solenoid
            session.solenoid_on_raises = bool(message.get("solenoid_on_raises", True))
            session.hold_duty = message.get("hold_duty")
            session.pull_in_ms = message.get("pull_in_ms")
            session.pwm = message.get("pwm")
            self._on_change()
            await self._on_event(device_id, message)  # lets the controller send our settings
        elif kind == "status":
            for key in STATUS_FIELDS:
                if key in message:
                    setattr(session, key, message[key])
            session.mask = message.get("mask", session.mask)
            session.rest = message.get("rest", session.rest)
            self._on_change()
        else:
            if kind == "dots":
                session.mask = int(message.get("mask", 0))
                session.rest = bool(message.get("rest", False))
            await self._on_event(device_id, message)

    async def send_all(self, message: dict) -> None:
        sessions = list(self.sessions.values())
        results = await asyncio.gather(*(s.send(message) for s in sessions), return_exceptions=True)
        for session, result in zip(sessions, results):
            if isinstance(result, Exception):
                log.warning("send to %s failed: %s", session.id, result)

    def snapshot(self) -> list[dict]:
        return [s.to_dict() for s in self.sessions.values()]
