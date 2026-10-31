"""ElevenLabs: conversation credentials for the voice agent, text-to-speech and speech-to-text.

The API key stays on the server. Browsers get a short-lived WebRTC token or
signed WebSocket URL for the agent, synthesized audio for announcements, and
transcripts of what was said while the phone's hold-to-talk button was held.
"""
from __future__ import annotations

import hashlib
from collections import OrderedDict

import httpx

from .settings import Settings

API = "https://api.elevenlabs.io"


class ElevenLabsError(RuntimeError):
    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.status = status


class ElevenLabs:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._client = httpx.AsyncClient(base_url=API, timeout=20)
        self._tts_cache: OrderedDict[str, bytes] = OrderedDict()

    async def close(self) -> None:
        await self._client.aclose()

    def status(self) -> dict:
        s = self.settings
        return {
            "api_key": bool(s.elevenlabs_api_key),
            "agent_id": s.elevenlabs_agent_id or None,
            "ready": s.elevenlabs_ready,
            "tts": bool(s.elevenlabs_api_key),
        }

    def _headers(self) -> dict:
        if not self.settings.elevenlabs_api_key:
            raise ElevenLabsError("ELEVENLABS_API_KEY is not set in server/.env", 503)
        return {"xi-api-key": self.settings.elevenlabs_api_key}

    async def _get(self, path: str, **params) -> dict:
        response = await self._client.get(path, params=params, headers=self._headers())
        if response.status_code >= 400:
            raise ElevenLabsError(f"ElevenLabs {response.status_code}: {response.text[:300]}")
        return response.json()

    async def conversation_credentials(self, connection: str) -> dict:
        agent_id = self.settings.elevenlabs_agent_id
        if not agent_id:
            raise ElevenLabsError(
                "ELEVENLABS_AGENT_ID is not set. Run: python scripts/provision_agent.py", 503)
        if connection == "websocket":
            data = await self._get("/v1/convai/conversation/get-signed-url", agent_id=agent_id)
            return {"connection": "websocket", "signed_url": data["signed_url"]}
        data = await self._get("/v1/convai/conversation/token", agent_id=agent_id)
        return {"connection": "webrtc", "token": data["token"]}

    async def tts(self, text: str) -> bytes:
        s = self.settings
        key = hashlib.sha1(f"{s.elevenlabs_voice_id}|{s.elevenlabs_tts_model}|{text}".encode()).hexdigest()
        if key in self._tts_cache:
            self._tts_cache.move_to_end(key)
            return self._tts_cache[key]
        response = await self._client.post(
            f"/v1/text-to-speech/{s.elevenlabs_voice_id}/stream",
            params={"output_format": "mp3_44100_64"},
            headers=self._headers(),
            json={"text": text, "model_id": s.elevenlabs_tts_model},
        )
        if response.status_code >= 400:
            raise ElevenLabsError(f"ElevenLabs TTS {response.status_code}: {response.text[:300]}")
        audio = response.content
        # Camera announcements repeat a lot ("person ahead"); don't pay for them twice.
        self._tts_cache[key] = audio
        if len(self._tts_cache) > 200:
            self._tts_cache.popitem(last=False)
        return audio

    async def stt(self, audio: bytes, content_type: str) -> str:
        s = self.settings
        ext = {"audio/mp4": "m4a", "audio/aac": "aac", "audio/mpeg": "mp3", "audio/wav": "wav",
               "audio/ogg": "ogg"}.get(content_type.split(";")[0].strip(), "webm")
        data = {"model_id": s.elevenlabs_stt_model, "tag_audio_events": "false"}
        if s.elevenlabs_stt_language:
            data["language_code"] = s.elevenlabs_stt_language
        response = await self._client.post(
            "/v1/speech-to-text",
            headers=self._headers(),
            data=data,
            files={"file": (f"speech.{ext}", audio, content_type or "application/octet-stream")},
        )
        if response.status_code >= 400:
            raise ElevenLabsError(f"ElevenLabs speech-to-text {response.status_code}: {response.text[:300]}")
        return (response.json().get("text") or "").strip()
