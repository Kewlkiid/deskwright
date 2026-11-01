"""Speech to text. Meta: Muse Voice Transcribe on its own route (POST /v1/asr/transcribe: a multipart form with a
JSON `request` part and the `audio` part), falling back to Muse Spark (audio in chat) if that fails. OpenRouter has no
transcription endpoint, so there the audio goes to a chat model that accepts audio input."""
from __future__ import annotations

import base64
import json
import shutil
import subprocess
import time
import urllib.error
import urllib.request
import uuid

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
        # After a failed Muse Voice Transcribe call, voice goes to Muse Spark (audio in chat) for the rest of the session.
        self.endpoint_missing = False

    def transcribe(self, audio: bytes, mime: str = "audio/webm") -> str:
        base = mime.split(";")[0]
        if self.client.openrouter:
            return self._via_chat(audio, base, config.voice_model)
        if not self.endpoint_missing:
            wav = audio if base == "audio/wav" else to_wav(audio)
            if wav:
                try:
                    return self.muse_transcribe(wav)
                except Exception:  # noqa: BLE001 - the chat fallback below still works
                    self.endpoint_missing = True
        return self._via_chat(audio, base, config.vision_model)

    def muse_transcribe(self, wav: bytes) -> str:
        """Muse Voice Transcribe file endpoint. Takes a WAV clip; returns the transcript."""
        from .client import interruptible

        boundary = uuid.uuid4().hex

        def part(name: str, content: bytes, ctype: str, filename: str | None = None) -> bytes:
            disp = f'form-data; name="{name}"' + (f'; filename="{filename}"' if filename else "")
            return f"--{boundary}\r\nContent-Disposition: {disp}\r\nContent-Type: {ctype}\r\n\r\n".encode() + content + b"\r\n"

        request = {"model": config.voice_model, "audioEncoding": "WAV"}
        body = (part("request", json.dumps(request).encode(), "application/json")
                + part("audio", wav, "audio/wav", "speech.wav") + f"--{boundary}--\r\n".encode())
        req = urllib.request.Request(
            config.base_url.rstrip("/") + "/asr/transcribe", data=body,
            headers={"Authorization": f"Bearer {config.api_key}", "Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        t0 = time.time()
        with interruptible(lambda: urllib.request.urlopen(req, timeout=config.request_timeout)) as resp:
            data = json.loads(resp.read().decode())
        seconds = (data.get("audioDurationMs") or 0) / 1000
        self.client.record_external("voice", time.time() - t0, seconds / 3600 * 0.18)  # $0.18 per audio hour
        return (data.get("transcript") or "").strip()

    def _via_chat(self, audio: bytes, base: str, model: str) -> str:
        wav = audio if base == "audio/wav" else to_wav(audio)
        data, fmt = (wav, "wav") if wav else (audio, base.split("/")[-1])
        part = {"type": "input_audio", "input_audio": {"data": base64.b64encode(data).decode(), "format": fmt}}
        reply = self.client.chat(
            "voice",
            model,
            [{"role": "user", "content": [part, text_part(TRANSCRIBE_PROMPT)]}],
            max_tokens=400,
            temperature=0.0,
        )
        return reply.strip().strip('"').strip()
