"""Server configuration (from server/.env) and runtime preferences (from the UI)."""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

SERVER_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = SERVER_DIR.parent
DATA_DIR = SERVER_DIR / "data"
ENV_FILE = SERVER_DIR / ".env"

log = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    host: str = "0.0.0.0"
    http_port: int = 8000
    https_port: int = 8443  # 0 disables HTTPS (the iPhone camera needs it)
    mdns_enabled: bool = True
    mdns_hostname: str = "dynabraille"

    # Shared secret the ESP32 presents when it connects.
    device_token: str = "change-me"
    # "" = off, "auto" = first ESP32-looking USB port, or an explicit port like "COM5".
    device_serial_port: str = ""
    device_serial_baud: int = 115200

    # Extra camera besides the iPhone page: "" (none), a webcam index ("0"),
    # or an MJPEG/RTSP URL from an IP-camera app.
    camera_source: str = ""
    vision_enabled: bool = True
    yolo_model: str = "yolo11n.pt"
    yolo_image_size: int = 640

    elevenlabs_api_key: str = ""
    elevenlabs_agent_id: str = ""
    elevenlabs_voice_id: str = "JBFqnCBsd6RMkjVDRZzb"
    elevenlabs_tts_model: str = "eleven_flash_v2_5"
    # Speech-to-text for the phone's hold-to-talk button. Language "" = auto-detect.
    elevenlabs_stt_model: str = "scribe_v2"
    elevenlabs_stt_language: str = "en"
    # Optional LLM for the agent (provision script); empty keeps ElevenLabs' default.
    elevenlabs_llm: str = ""

    web_dist: Path = REPO_DIR / "web" / "dist"

    @property
    def elevenlabs_ready(self) -> bool:
        return bool(self.elevenlabs_api_key and self.elevenlabs_agent_id)


class Preferences(BaseModel):
    """Settings the user changes from the dashboard; persisted to data/preferences.json."""

    char_ms: int = Field(900, ge=150, le=4000)
    gap_ms: int = Field(250, ge=60, le=2000)
    auto_braille: bool = False  # continuous: braille whatever is in front of the camera
    announce: bool = True
    min_confidence: float = Field(0.45, ge=0.1, le=0.95)
    focus_stable_ms: int = Field(700, ge=0, le=5000)
    # Solenoid power budget, sent to the cell on connect. None = keep the firmware's own.
    hold_duty: int | None = Field(None, ge=10, le=100)  # % power once a solenoid is pulled in
    pull_in_ms: int | None = Field(None, ge=10, le=500)  # full power this long first


class PreferenceStore:
    def __init__(self, path: Path = DATA_DIR / "preferences.json"):
        self.path = path
        self._lock = threading.Lock()
        self.value = self._load()

    def _load(self) -> Preferences:
        try:
            return Preferences.model_validate_json(self.path.read_text("utf-8"))
        except FileNotFoundError:
            return Preferences()
        except Exception:
            log.warning("ignoring unreadable %s", self.path)
            return Preferences()

    def update(self, changes: dict) -> Preferences:
        with self._lock:
            merged = self.value.model_dump() | {k: v for k, v in changes.items() if v is not None}
            self.value = Preferences.model_validate(merged)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self.value.model_dump(), indent=2), "utf-8")
            return self.value
