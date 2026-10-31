"""python -m dynabraille  — runs the processing server.

Two listeners share one app:
  * HTTP  (default :8000) for the ESP32, the dashboard on this computer, and ca.crt
  * HTTPS (default :8443) for the iPhone, because iOS only allows camera access on HTTPS
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
import socket
import sys

import uvicorn

from .app import create_app
from .network import ensure_certificates
from .settings import ENV_FILE, Settings


class _Server(uvicorn.Server):
    # Two servers run in one loop; main() owns Ctrl+C for both.
    @contextlib.contextmanager
    def capture_signals(self):
        yield

    def install_signal_handlers(self) -> None:  # uvicorn < 0.29
        pass


def _ipv6_loopback_free(port: int) -> bool:
    """True if we can listen on [::1]:port (uvicorn exits the process if a bind fails)."""
    try:
        with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as s:
            s.bind(("::1", port))
        return True
    except OSError:
        return False


def main() -> None:
    for stream in (sys.stdout, sys.stderr):  # Windows consoles default to cp1252
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                        datefmt="%H:%M:%S")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    settings = Settings()
    app = create_app(settings)
    ctl = app.state.controller

    common = dict(host=settings.host, log_level="warning", ws_ping_interval=15, ws_ping_timeout=15)
    servers = [_Server(uvicorn.Config(app, port=settings.http_port, lifespan="on", **common))]
    if settings.https_port:
        _, cert, key = ensure_certificates(settings.mdns_hostname)
        servers.append(_Server(uvicorn.Config(app, port=settings.https_port, lifespan="off",
                                              ssl_certfile=str(cert), ssl_keyfile=str(key), **common)))
    if settings.host == "0.0.0.0" and _ipv6_loopback_free(settings.http_port):
        # Windows resolves "localhost" to ::1 first and waits ~2 s before trying
        # 127.0.0.1 when nothing answers there, so answer on ::1 too.
        servers.append(_Server(uvicorn.Config(app, port=settings.http_port, lifespan="off",
                                              **(common | {"host": "::1"}))))

    def stop(*_):
        for server in servers:
            server.should_exit = True

    signal.signal(signal.SIGINT, stop)
    with contextlib.suppress(AttributeError, ValueError):
        signal.signal(signal.SIGTERM, stop)

    urls = ctl.urls()
    env_note = "" if ENV_FILE.exists() else "  (no server/.env yet - using defaults; copy .env.example)"
    print(f"\n  DynaBraille server{env_note}")
    print(f"  Dashboard     {urls['dashboard'][0]}")
    for url in urls["camera"][:2]:
        print(f"  iPhone camera {url}")
    for url in urls["ca_certificate"][:1]:
        print(f"  iPhone cert   {url}   (install once, see docs/IPHONE.md)")
    for url in urls["device_ws"][:1]:
        print(f"  ESP32         {url}  or mDNS auto-discovery")
    print()

    async def run() -> None:
        await asyncio.gather(*(s.serve() for s in servers))

    asyncio.run(run())


if __name__ == "__main__":
    main()
