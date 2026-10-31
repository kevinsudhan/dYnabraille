"""Camera frames in, detections out.

Frames normally arrive as JPEGs from the iPhone camera page over a WebSocket.
An optional OpenCV source (webcam index or MJPEG/RTSP URL) feeds the same pipeline.
Detection runs on one worker thread; YOLO is loaded in the background at startup.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Awaitable, Callable

import cv2
import numpy as np

from .scene import Detection
from .settings import SERVER_DIR, Settings

log = logging.getLogger(__name__)
MODELS_DIR = SERVER_DIR / "models"


class VisionService:
    def __init__(self, settings: Settings, on_status: Callable[[], None]):
        self.settings = settings
        self._on_status = on_status
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="yolo")
        self._model = None
        self.detector_state = "disabled" if not settings.vision_enabled else "loading"
        self.detector_error: str | None = None
        self.device = "cpu"

        self.frame_id = 0
        self.latest_jpeg: bytes | None = None
        self.latest_at = 0.0
        self.source: str | None = None
        self._frame_times: list[float] = []
        self._new_frame = asyncio.Condition()
        self._stop = threading.Event()

    # ------------------------------------------------------------------ lifecycle

    def start(self, loop: asyncio.AbstractEventLoop,
              on_frame: Callable[[bytes, str], Awaitable[object]]) -> None:
        self._loop = loop
        if self.settings.vision_enabled:
            self._pool.submit(self._load_model)
        if self.settings.camera_source.strip():
            threading.Thread(target=self._capture_loop, args=(on_frame,), name="camera",
                             daemon=True).start()

    def stop(self) -> None:
        self._stop.set()
        self._pool.shutdown(wait=False, cancel_futures=True)

    def _set_state(self, state: str, error: str | None = None) -> None:
        self.detector_state, self.detector_error = state, error
        self._loop.call_soon_threadsafe(self._on_status)

    def _load_model(self) -> None:
        try:
            from ultralytics import YOLO
        except ImportError:
            self._set_state("unavailable", "ultralytics not installed (pip install -r requirements-vision.txt)")
            return
        try:
            MODELS_DIR.mkdir(parents=True, exist_ok=True)
            name = self.settings.yolo_model
            path = Path(name) if Path(name).is_absolute() else MODELS_DIR / name
            started = time.perf_counter()
            model = YOLO(str(path))  # downloads official weights on first run
            import torch
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
            model.predict(np.zeros((480, 640, 3), np.uint8), verbose=False, device=self.device)
            self._model = model
            log.info("YOLO %s ready on %s in %.1fs", name, self.device, time.perf_counter() - started)
            self._set_state("ready")
        except Exception as exc:
            log.exception("could not load YOLO")
            self._set_state("error", str(exc))

    # ------------------------------------------------------------------ frames

    async def publish(self, jpeg: bytes, source: str) -> None:
        """Make a frame the latest one (for the dashboard's live view)."""
        now = time.monotonic()
        self.latest_jpeg, self.latest_at, self.source = jpeg, now, source
        self._frame_times = [t for t in self._frame_times if now - t < 2.0] + [now]
        self.frame_id += 1
        async with self._new_frame:
            self._new_frame.notify_all()

    @property
    def fps(self) -> float:
        times = [t for t in self._frame_times if time.monotonic() - t < 2.0]
        return round(len(times) / 2.0, 1)

    @property
    def camera_online(self) -> bool:
        return self.latest_jpeg is not None and time.monotonic() - self.latest_at < 3.0

    async def detect(self, jpeg: bytes, min_confidence: float) -> tuple[list[Detection], float]:
        if self._model is None:
            return [], 0.0
        return await asyncio.get_running_loop().run_in_executor(
            self._pool, self._detect, jpeg, min_confidence)

    def _detect(self, jpeg: bytes, min_confidence: float) -> tuple[list[Detection], float]:
        image = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            return [], 0.0
        height, width = image.shape[:2]
        started = time.perf_counter()
        result = self._model.predict(image, conf=min_confidence, imgsz=self.settings.yolo_image_size,
                                     verbose=False, device=self.device)[0]
        elapsed_ms = (time.perf_counter() - started) * 1000
        detections = []
        if result.boxes is not None:
            for xyxy, conf, cls in zip(result.boxes.xyxy.tolist(), result.boxes.conf.tolist(),
                                       result.boxes.cls.tolist()):
                x1, y1, x2, y2 = xyxy
                detections.append(Detection(
                    label=result.names[int(cls)], confidence=float(conf),
                    box=(x1 / width, y1 / height, x2 / width, y2 / height)))
        return detections, elapsed_ms

    async def mjpeg(self):
        """multipart/x-mixed-replace body that follows the latest frame."""
        last = -1
        while True:
            async with self._new_frame:
                await self._new_frame.wait_for(lambda: self.frame_id != last)
            last, jpeg = self.frame_id, self.latest_jpeg
            yield (b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
                   + str(len(jpeg)).encode() + b"\r\n\r\n" + jpeg + b"\r\n")

    # ------------------------------------------------------------------ optional OpenCV source

    def _capture_loop(self, on_frame: Callable[[bytes, str], Awaitable[object]]) -> None:
        spec = self.settings.camera_source.strip()
        source: int | str = int(spec) if spec.isdigit() else spec
        while not self._stop.is_set():
            backend = cv2.CAP_DSHOW if isinstance(source, int) and hasattr(cv2, "CAP_DSHOW") else cv2.CAP_ANY
            cap = cv2.VideoCapture(source, backend)
            if not cap.isOpened():
                log.warning("camera %s not available, retrying", spec)
                self._stop.wait(5)
                continue
            log.info("camera source %s open", spec)
            while not self._stop.is_set():
                ok, frame = cap.read()
                if not ok:
                    break
                ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
                if ok:
                    # Waits for detection, so this naturally runs at inference speed.
                    asyncio.run_coroutine_threadsafe(on_frame(buf.tobytes(), "camera"), self._loop).result()
            cap.release()
            self._stop.wait(2)

    def status(self) -> dict:
        return {
            "detector": self.detector_state,
            "detector_error": self.detector_error,
            "model": self.settings.yolo_model,
            "device": self.device,
            "camera_online": self.camera_online,
            "source": self.source,
            "fps": self.fps,
        }
