"""Talking back: Deskwright says what it's doing and reads chat replies aloud.

Voice: Kyutai Pocket TTS (on this Mac's CPU, streamed to the speakers chunk by chunk, so speech starts within a few
hundred ms). Meta has no text-to-speech model. If Pocket TTS can't load, the Mac's own `say` is used instead.

Narration never lags behind the run: a new step replaces a step that hasn't been spoken yet, and important lines
(approvals, questions, results, replies) cut in. While it speaks, the app pauses wake-word listening so the
microphone doesn't hear Deskwright itself ("speaking" events).
"""
from __future__ import annotations

import re
import subprocess
import threading
import time
from collections import deque
from urllib.parse import urlparse

from .config import config


def clean(text: str) -> str:
    """Markdown and symbols out, so it reads naturally."""
    text = re.sub(r"```.*?```", " ", text or "", flags=re.S)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)  # links -> their text
    text = re.sub(r"[*_`#>]+", "", text)
    text = re.sub(r"^\s*[-•]\s+", "", text, flags=re.M)
    text = re.sub(r"https?://(\S+)", lambda m: urlparse("http://" + m.group(1)).netloc or "a link", text)
    return re.sub(r"\s+", " ", text).strip()


def short_target(target: str) -> str:
    """'circular server icon with a white letter C in the far-left sidebar' -> 'circular server icon'."""
    t = re.sub(r"[\"“”]|(?<![A-Za-z])['‘’]|['‘’](?![A-Za-z])", "", clean(target)).strip()  # quotes, not apostrophes
    t = re.split(r"\s+(?:in|at|on|under|below|above|near|next to|inside|from|with|within|to the|beside|that|which)\s+",
                 t, maxsplit=1)[0]
    words = t.split()
    return " ".join(words[:6])


class Speaker:
    def __init__(self, emit):
        self.emit = emit  # to the app only (never back through the narrator)
        self.enabled = False
        self.state = "off"  # off | loading | ready | unavailable
        self.backend = ""  # "Pocket TTS" or "macOS voice"
        self._items: deque = deque()
        self._cv = threading.Condition()
        self._cut = threading.Event()  # stop the current utterance
        self._model = None
        self._voice = None
        self._loading = False
        self.speaking = False
        self._recent: deque = deque(maxlen=3)  # what it said lately: the mic hears that too
        threading.Thread(target=self._worker, name="speaker", daemon=True).start()

    # Control ---------------------------------------------------------------
    def set_enabled(self, on: bool):
        self.enabled = bool(on)
        if not self.enabled:
            self.stop()
            self._status("off")
            return
        if self._model is None and not self._loading and self.backend != "macOS voice":
            self._loading = True
            self._status("loading")
            threading.Thread(target=self._load, name="tts-load", daemon=True).start()
        else:
            self._status("ready")

    def _status(self, state: str):
        self.state = state
        self.emit("voice_status", state=state, backend=self.backend)

    def _load(self):
        try:
            from pocket_tts import TTSModel

            model = TTSModel.load_model()
            self._voice = model.get_state_for_audio_prompt(config.tts_voice)
            self._model = model
            self.backend = "Pocket TTS"
        except Exception:  # noqa: BLE001 - not installed, no weights offline...: the Mac's voice still works
            self.backend = "macOS voice"
        self._loading = False
        self._status("ready" if self.enabled else "off")

    def say(self, text: str, important: bool = False):
        text = clean(text)
        if not self.enabled or not text:
            return
        with self._cv:
            if important:
                self._items.clear()
                self._cut.set()
            else:
                # Keep up with the run: an unspoken step is replaced by the newer one.
                while self._items and not self._items[-1][1]:
                    self._items.pop()
            self._items.append((text[:400], important))
            self._cv.notify()

    def stop(self):
        with self._cv:
            self._items.clear()
            self._cut.set()

    def recent_text(self) -> str:
        """The last few things it said (or is saying), to tell its own voice from the user's."""
        return " ".join(self._recent)

    # Playback ----------------------------------------------------------------
    def _worker(self):
        stream = None
        while True:
            with self._cv:
                while not self._items:
                    self._cv.wait()
                text, _ = self._items.popleft()
                self._cut.clear()
                self._recent.append(text)
            while self._loading and not self._cut.is_set():
                time.sleep(0.1)  # first sentence after turning voice on: wait for the model
            self.speaking = True
            self.emit("speaking", on=True)
            try:
                if self._model is not None:
                    stream = self._play_pocket(text, stream)
                else:
                    self._play_say(text)
            except Exception:  # noqa: BLE001 - a missing audio device mustn't take the engine down
                stream = None
            with self._cv:
                idle = not self._items
            if idle:
                self.speaking = False
                time.sleep(0.25)  # the room's echo dies down
                self.emit("speaking", on=False)

    def _play_pocket(self, text: str, stream):
        import numpy as np
        import sounddevice as sd

        if stream is None:
            stream = sd.OutputStream(samplerate=self._model.sample_rate, channels=1, dtype="float32")
            stream.start()
        for chunk in self._model.generate_audio_stream(self._voice, text, stop=self._cut):
            if self._cut.is_set():
                break
            stream.write(np.ascontiguousarray(chunk.numpy().reshape(-1, 1), dtype=np.float32))
        return stream

    def _play_say(self, text: str):
        p = subprocess.Popen(["say", text])
        while p.poll() is None:
            if self._cut.wait(0.05):
                p.terminate()
                break


class Narrator:
    """Turns the run's events into short spoken lines."""

    VERBS = {"click": "Clicking", "double-click": "Double-clicking", "right-click": "Right-clicking",
             "type into": "Typing into", "hover over": "Pointing at", "drag": "Dragging"}

    def __init__(self, speaker: Speaker):
        self.speaker = speaker

    def on_event(self, type: str, data: dict):
        s = self.speaker
        if not s.enabled:
            return
        if type == "chat_reply":
            s.say(data.get("text", ""), important=True)
        elif type == "wake_heard":
            s.say("Yes?", important=True)
        elif type == "element_found" and data.get("verb") in self.VERBS:
            s.say(f"{self.VERBS[data['verb']]} {short_target(data.get('target', ''))}")
        elif type == "status":
            text = data.get("text") or ""
            m = re.match(r"Opening app: (.+)", text)
            if m:
                s.say(f"Opening {m.group(1)}")
            elif text.startswith("Opening http"):
                s.say(f"Opening {urlparse(text.split(' ', 1)[1]).netloc.removeprefix('www.')}")
            elif text.startswith("Fixing line"):
                s.say("Something changed. Fixing it.")
            elif text.startswith("Known way back"):
                s.say("I've seen this before. Going back.")
        elif type == "confirm_request":
            first = (data.get("summary") or "").splitlines()[0] if data.get("summary") else "this step"
            s.say(f"I need your approval. {first}", important=True)
        elif type == "ask_user":
            s.say(data.get("question", ""), important=True)
        elif type == "teach_recording":
            if data.get("recording"):
                s.say("Recording. Show me the task.", important=True)
            elif not data.get("cancelled"):
                s.say("Got it. Working out the steps.", important=True)
        elif type == "run_finished":
            status = data.get("status")
            if status == "succeeded":
                said = " ".join(str(r.get("text") or "") for r in data.get("results") or [])
                s.say(("Done. " + clean(said)[:260]).strip(), important=True)
            elif status == "stopped":
                s.say("Stopped.", important=True)
            elif status == "declined":
                s.say("Okay, I won't do that.", important=True)
            else:
                msg = clean(((data.get("error") or {}).get("message") or ""))[:140]
                s.say(f"I couldn't finish that. {msg}", important=True)
