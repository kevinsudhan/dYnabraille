"""Pretend to be the ESP32 braille cell, using the same WebSocket protocol as the firmware.

It models the real build: solenoids numbered row by row (S1 S2 / S3 S4 / S5 S6),
unpowered solenoid = pin up = dot felt, so the idle cell has all six pins up.

    python scripts/fake_device.py                       # localhost:8000, token from server/.env
    python scripts/fake_device.py --host 192.168.1.20

While it runs, type s / d / l + Enter to send a short / double / long button press.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import threading
import time
from pathlib import Path

import websockets

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dynabraille.braille import mask_to_dots  # noqa: E402
from dynabraille.settings import Settings  # noqa: E402

MAX_CHAR_MS = 4000
STATIC_HOLD_MS = 8000
DOT_TO_SOLENOID = [1, 3, 5, 2, 4, 6]
REST_MASK = 0b111111  # all pins up when every solenoid is off


def render(mask: int) -> str:
    dot = lambda n: "●" if mask & (1 << (n - 1)) else "○"  # noqa: E731
    return f"{dot(1)}{dot(4)} {dot(2)}{dot(5)} {dot(3)}{dot(6)}  {chr(0x2800 + mask)}  {mask_to_dots(mask)}"


def powered_for(mask: int) -> list[int]:
    """Solenoids (S1..S6) the firmware would switch on to show this braille mask."""
    return sorted(DOT_TO_SOLENOID[d] for d in range(6) if not mask & (1 << d))


class FakeCell:
    def __init__(self, ws, device_id: str):
        self.ws, self.device_id = ws, device_id
        self.mask = REST_MASK
        self.rest = True
        self.job: asyncio.Task | None = None
        self.started = time.monotonic()

    async def emit(self, message: dict) -> None:
        await self.ws.send(json.dumps(message))

    async def set_mask(self, mask: int, rest: bool = False) -> None:
        if rest:
            mask = REST_MASK
        if mask != self.mask or rest != self.rest:
            self.mask, self.rest = mask, rest
            label = "rest" if rest else f"powered S{powered_for(mask)}"
            print("  cell", render(mask), label)
            await self.emit({"type": "dots", "mask": mask, "rest": rest})

    async def play(self, job_id: int, cells: list[int], char_ms: int, gap_ms: int) -> None:
        try:
            for index, mask in enumerate(cells):
                await self.emit({"type": "progress", "id": job_id, "index": index, "count": len(cells)})
                await self.set_mask(mask)
                await asyncio.sleep(min(char_ms, MAX_CHAR_MS) / 1000)
                await self.set_mask(0)  # blank gap: all solenoids on
                await asyncio.sleep(max(gap_ms, 60) / 1000)
            await self.set_mask(0, rest=True)
            await self.emit({"type": "done", "id": job_id, "cancelled": False})
        except asyncio.CancelledError:
            await self.emit({"type": "done", "id": job_id, "cancelled": True})
            raise

    async def hold(self, mask: int, ms: int) -> None:
        await self.set_mask(mask)
        await asyncio.sleep(min(ms, STATIC_HOLD_MS) / 1000)
        await self.set_mask(0, rest=True)

    def run(self, coro) -> None:
        if self.job and not self.job.done():
            self.job.cancel()
        self.job = asyncio.create_task(coro)

    async def handle(self, message: dict) -> None:
        kind = message.get("type")
        if kind == "show":
            print(f"show #{message['id']}: {len(message['cells'])} cells")
            self.run(self.play(message["id"], message["cells"], message.get("char_ms", 900),
                               message.get("gap_ms", 250)))
        elif kind in ("cell", "braille", "character"):
            mask = message.get("mask")
            if mask is None:
                mask = sum(1 << (d - 1) for d in message.get("dots", []) if 1 <= d <= 6)
            self.run(self.hold(mask, message.get("hold_ms", STATIC_HOLD_MS)))
        elif kind == "test":
            solenoid = message.get("solenoid") or DOT_TO_SOLENOID[message["dot"] - 1]
            dot = DOT_TO_SOLENOID.index(solenoid)  # only this solenoid on: its pin drops
            self.run(self.hold(REST_MASK & ~(1 << dot), message.get("ms", 600)))
        elif kind in ("stop", "reset"):
            if self.job:
                self.job.cancel()
            await self.set_mask(0, rest=True)
        elif kind == "status":
            await self.status()
        elif kind == "ping":
            await self.emit({"type": "pong", "t": message.get("t")})

    async def status(self) -> None:
        await self.emit({"type": "status", "device_id": self.device_id, "rssi": -52,
                         "uptime_ms": int((time.monotonic() - self.started) * 1000), "heap": 210000,
                         "mask": self.mask, "rest": self.rest, "battery_v": 3.95, "battery_pct": 72, "lux": 140.0,
                         "light_aid": False, "ip": "127.0.0.1"})


async def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows consoles default to cp1252
    settings = Settings()
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=settings.http_port)
    parser.add_argument("--token", default=settings.device_token)
    parser.add_argument("--id", default="dynabraille-sim001")
    args = parser.parse_args()

    url = f"ws://{args.host}:{args.port}/ws/device?token={args.token}&id={args.id}"
    loop = asyncio.get_running_loop()
    presses: asyncio.Queue[str] = asyncio.Queue()

    def read_keys() -> None:
        names = {"s": "short", "d": "double", "l": "long"}
        for line in sys.stdin:
            if line.strip() in names:
                loop.call_soon_threadsafe(presses.put_nowait, names[line.strip()])

    threading.Thread(target=read_keys, daemon=True).start()

    async for ws in websockets.connect(url):
        cell = FakeCell(ws, args.id)
        print(f"connected to {args.host}:{args.port} as {args.id}  (s/d/l + Enter = button)")
        await cell.emit({"type": "hello", "proto": 2, "device_id": args.id, "name": "Simulated cell",
                         "fw": "sim", "dots": 6, "max_on_ms": 20000, "rest_mask": REST_MASK,
                         "dot_to_solenoid": DOT_TO_SOLENOID, "solenoid_on_raises": False, "ip": "127.0.0.1",
                         "features": {"button": True, "lux": True, "light_aid": False, "battery": True}})
        await cell.status()

        async def heartbeat() -> None:
            while True:
                await asyncio.sleep(5)
                await cell.status()

        async def buttons() -> None:
            while True:
                event = await presses.get()
                print("button", event)
                await cell.emit({"type": "button", "event": event})

        tasks = [asyncio.create_task(heartbeat()), asyncio.create_task(buttons())]
        try:
            async for raw in ws:
                await cell.handle(json.loads(raw))
        except websockets.ConnectionClosed:
            print("disconnected; retrying")
        finally:
            for task in tasks:
                task.cancel()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
