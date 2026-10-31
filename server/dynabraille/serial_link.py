"""Optional USB-serial link to the ESP32 (for bench testing without WiFi)."""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import time

from .devices import DeviceManager

log = logging.getLogger(__name__)

# USB-UART bridges used on ESP32 dev boards, plus Espressif's native USB.
ESP32_USB_IDS = {(0x10C4, 0xEA60), (0x1A86, 0x7523), (0x1A86, 0x55D4), (0x0403, 0x6001)}
ESPRESSIF_VID = 0x303A


def find_esp32_port() -> str | None:
    from serial.tools import list_ports

    for port in list_ports.comports():
        if (port.vid, port.pid) in ESP32_USB_IDS or port.vid == ESPRESSIF_VID:
            return port.device
    return None


class SerialLink:
    def __init__(self, port: str, baud: int, devices: DeviceManager, loop: asyncio.AbstractEventLoop):
        self.port_spec = port
        self.baud = baud
        self.devices = devices
        self.loop = loop
        self._stop = threading.Event()
        self._write_lock = threading.Lock()
        self._serial = None
        self.device_id: str | None = None

    def start(self) -> None:
        threading.Thread(target=self._run, name="serial-link", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()

    def _write(self, message: dict) -> None:
        with self._write_lock:
            if self._serial:
                self._serial.write((json.dumps(message) + "\n").encode())

    async def _send(self, message: dict) -> None:
        await asyncio.to_thread(self._write, message)

    def _run(self) -> None:
        import serial

        while not self._stop.is_set():
            port = find_esp32_port() if self.port_spec == "auto" else self.port_spec
            if not port:
                self._stop.wait(5)
                continue
            try:
                ser = serial.Serial()
                ser.port, ser.baudrate, ser.timeout = port, self.baud, 0.5
                # On ESP32 dev boards DTR/RTS drive BOOT/EN: toggling them on open
                # would reset the chip into its bootloader.
                ser.dtr = ser.rts = False
                ser.open()
                try:
                    self._serial = ser
                    log.info("serial link open on %s", port)
                    self._pump(ser)
                finally:
                    ser.close()
            except serial.SerialException as exc:
                log.debug("serial %s unavailable: %s", port, exc)
            finally:
                self._serial = None
                if self.device_id:
                    self.loop.call_soon_threadsafe(self.devices.detach, self.device_id, "usb")
                    self.device_id = None
            self._stop.wait(3)

    def _pump(self, ser) -> None:
        last_poll = 0.0
        while not self._stop.is_set():
            now = time.monotonic()
            if now - last_poll > (5 if self.device_id else 1.5):
                last_poll = now
                self._write({"type": "status"})  # also how we learn the device id
            line = ser.readline().decode("utf-8", "replace").strip()
            if not line.startswith("{"):
                continue  # firmware log lines start with "#"
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not self.device_id and message.get("device_id"):
                self.device_id = message["device_id"]
                fut = asyncio.run_coroutine_threadsafe(self._attach(), self.loop)
                fut.result(timeout=5)
                self._write({"type": "hello"})  # name, firmware, solenoid layout
            if self.device_id:
                asyncio.run_coroutine_threadsafe(
                    self.devices.handle(self.device_id, "usb", message), self.loop)

    async def _attach(self) -> None:
        self.devices.attach(self.device_id, "usb", self._send)
