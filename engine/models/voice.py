"""Speech to text. Meta: Muse Voice Transcribe through the OpenAI-compatible audio endpoint.
OpenRouter has no transcription endpoint, so there the audio goes to a chat model that accepts audio input."""
from __future__ import annotations

import base64
import shutil
import subprocess
import time

from ..config import config
from .client import ModelClient, text_part

TRANSCRIBE_PROMPT = (
    "Transcribe this voice command exactly as spoken. Reply with the transcript only, no quotes or commentary. "
    "If there is no speech, reply with an empty string."
)


def to_wav(audio: bytes) -> bytes | None:
    """Browser recordings are webm/opus, which chat audio inputs rarely accept; convert with ffmpeg if present."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    try:
        out = subprocess.run(
            [ffmpeg, "-loglevel", "error", "-i", "pipe:0", "-ac", "1", "-ar", "16000", "-f", "wav", "pipe:1"],
            input=audio,
            capture_output=True,
            timeout=30,
        )
        return out.stdout if out.returncode == 0 and out.stdout else None
    except Exception:
        return None


class Voice:
    def __init__(self, client: ModelClient):
        self.client = client

    def transcribe(self, audio: bytes, mime: str = "audio/webm") -> str:
        base = mime.split(";")[0]
        if self.client.openrouter:
            return self._via_chat(audio, base)
        ext = {"audio/webm": "webm", "audio/ogg": "ogg", "audio/wav": "wav", "audio/mp4": "m4a"}.get(base, "webm")
        t0 = time.time()
        # TODO(meta-api): confirm the transcription endpoint matches OpenAI's /audio/transcriptions.
        resp = self.client.client.audio.transcriptions.create(model=config.voice_model, file=(f"speech.{ext}", audio, base))
        self.client.record_external("voice", time.time() - t0, 0.0)
        return (getattr(resp, "text", None) or str(resp)).strip()

    def _via_chat(self, audio: bytes, base: str) -> str:
        wav = audio if base == "audio/wav" else to_wav(audio)
        data, fmt = (wav, "wav") if wav else (audio, base.split("/")[-1])
        part = {"type": "input_audio", "input_audio": {"data": base64.b64encode(data).decode(), "format": fmt}}
        reply = self.client.chat(
            "voice",
            config.voice_model,
            [{"role": "user", "content": [part, text_part(TRANSCRIBE_PROMPT)]}],
            max_tokens=400,
            temperature=0.0,
        )
        return reply.strip().strip('"').strip()
