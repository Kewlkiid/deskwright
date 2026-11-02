"""Talking back: Deskwright says what it's doing and reads chat replies aloud.

Voice: Meta MMS-TTS (Massively Multilingual Speech, facebook/mms-tts-eng: a 36M VITS model on this Mac's CPU, about
0.2 s per short sentence). Sentences are made and played one at a time, so speech starts quickly and can be cut between
them. If MMS-TTS can't load, the Mac's own `say` is used instead.

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


_ONES = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
         "seventeen eighteen nineteen").split()
_TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()


def number_words(n: int) -> str:
    """12 -> 'twelve', 2025 -> 'two thousand twenty five'."""
    if n < 20:
        return _ONES[n]
    if n < 100:
        return _TENS[n // 10] + ("" if n % 10 == 0 else " " + _ONES[n % 10])
    for size, name in ((10**9, "billion"), (10**6, "million"), (1000, "thousand"), (100, "hundred")):
        if n >= size:
            rest = n % size
            return number_words(n // size) + " " + name + ("" if rest == 0 else " " + number_words(rest))
    return str(n)


def speakable(text: str) -> str:
    """Digits and symbols as words: MMS-TTS was trained on letters only."""
    text = re.sub(r"(?<=\d),(?=\d{3})", "", text).replace("%", " percent").replace("&", " and ")
    text = re.sub(r"(\d+)\.(\d+)", lambda m: f"{m.group(1)} point {' '.join(m.group(2))}", text)
    return re.sub(r"\d+", lambda m: number_words(int(m.group())) if len(m.group()) <= 12 else " ".join(m.group()), text)


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
        self.backend = ""  # "Meta MMS-TTS" or "macOS voice"
        self._items: deque = deque()
        self._cv = threading.Condition()
        self._cut = threading.Event()  # stop the current utterance
        self._model = None
        self._tok = None
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
            import torch
            from transformers import AutoTokenizer, VitsModel

            tok = AutoTokenizer.from_pretrained(config.tts_model)
            model = VitsModel.from_pretrained(config.tts_model).eval()
            model.noise_scale = 0.9  # livelier pitch and energy than the default 0.667
            with torch.inference_mode():
                model(**tok("ready", return_tensors="pt"))  # warm up, so the first line is quick too
            self._tok = tok
            self._model = model
            self.backend = "Meta MMS-TTS"
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
                    stream = self._play_mms(text, stream)
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

    def _play_mms(self, text: str, stream):
        import numpy as np
        import sounddevice as sd
        import torch

        rate = self._model.config.sampling_rate
        if stream is None:
            stream = sd.OutputStream(samplerate=rate, channels=1, dtype="float32")
            stream.start()
        for sentence in re.split(r"(?<=[.!?;:])\s+", text):
            inputs = self._tok(speakable(sentence), return_tensors="pt")
            if self._cut.is_set():
                break
            if inputs.input_ids.shape[-1] < 2:
                continue  # nothing it can say
            with torch.inference_mode():
                wav = self._model(**inputs).waveform[0].numpy()
            for i in range(0, len(wav), rate // 10):  # 0.1 s at a time, so a cut is quick
                if self._cut.is_set():
                    return stream
                stream.write(np.ascontiguousarray(wav[i:i + rate // 10].reshape(-1, 1)))
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
            opts = data.get("options") or []
            s.say(data.get("question", "") + (" " + ", or ".join(opts) + "?" if opts else ""), important=True)
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
