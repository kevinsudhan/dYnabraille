"""Fan-out of live events to browser clients (dashboard and iPhone camera page)."""
from __future__ import annotations

import asyncio
import json
import logging
from collections import Counter

from fastapi import WebSocket

log = logging.getLogger(__name__)


class _Client:
    def __init__(self, ws: WebSocket, role: str):
        self.ws = ws
        self.role = role
        self.queue: asyncio.Queue[str] = asyncio.Queue(maxsize=256)

    def push(self, message: str) -> None:
        if self.queue.full():  # a stalled client loses old events, never blocks others
            self.queue.get_nowait()
        self.queue.put_nowait(message)


class Hub:
    def __init__(self) -> None:
        self._clients: set[_Client] = set()

    def roles(self) -> Counter:
        return Counter(c.role for c in self._clients)

    async def serve(self, ws: WebSocket, role: str, snapshot: dict) -> None:
        """Run one client connection until it closes."""
        client = _Client(ws, role)
        self._clients.add(client)
        client.push(json.dumps({"type": "snapshot", **snapshot}))
        self.broadcast({"type": "clients", "roles": dict(self.roles())})

        async def writer() -> None:
            while True:
                await ws.send_text(await client.queue.get())

        writer_task = asyncio.create_task(writer())
        try:
            while True:  # we only read to notice disconnects
                await ws.receive_text()
        except Exception:
            pass
        finally:
            writer_task.cancel()
            self._clients.discard(client)
            self.broadcast({"type": "clients", "roles": dict(self.roles())})

    def broadcast(self, event: dict, role: str | None = None) -> None:
        message = json.dumps(event)
        for client in list(self._clients):
            if role is None or client.role == role:
                client.push(message)

    def speak(self, text: str, intent: str = "announce") -> None:
        """Send speech to one place: the iPhone if one is connected, else dashboards.

        intent: "announce" (short camera update), "capture" (result of the capture
        button), "describe" (answer to "what's around me"), or "notice" (system
        message). An open assistant session decides how to voice it, so speech
        doesn't talk over the agent.
        """
        target = "phone" if self.roles().get("phone") else "dashboard"
        self.broadcast({"type": "speak", "text": text, "intent": intent}, role=target)
