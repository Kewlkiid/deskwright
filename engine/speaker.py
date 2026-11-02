"""Talking back: Deskwright says what it's doing and reads chat replies aloud, in the app's language.

Voice: Meta MMS-TTS (Massively Multilingual Speech, facebook/mms-tts-eng/-spa/-fra/-deu/-por: a 36M VITS model on
this Mac's CPU, about 0.2 s per short sentence). Sentences are made and played one at a time, so speech starts
quickly and can be cut between them. If MMS-TTS can't load, the Mac's own `say` is used instead.
With TTS_ENGINE=pocket (demo recordings), English is spoken by Kyutai Pocket TTS, streamed chunk by chunk.

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

from . import i18n
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
    """Digits and symbols as words: MMS-TTS was trained on letters only. Other languages via num2words."""
    num_lang = i18n.info()["num_lang"]
    if num_lang and num_lang != "en":
        try:
            from num2words import num2words

            text = re.sub(r"(?<=\d),(?=\d{3})", "", text)
            return re.sub(r"\d+(?:\.\d+)?", lambda m: num2words(float(m.group()) if "." in m.group() else int(m.group()),
                                                                lang=num_lang) if len(m.group()) <= 12 else m.group(), text)
        except Exception:  # noqa: BLE001 - not installed: the digits are dropped, the rest is still said
            return text
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
        self._voice = None  # Pocket TTS voice state
        self._loading = False
        self._lang = i18n.lang()  # the language the loaded voice speaks
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

    def set_language(self, code: str):
        """Switch the voice to the language the app is set to (a different MMS-TTS checkpoint)."""
        if code == self._lang:
            return
        self.stop()
        self._lang = code
        self._model = self._tok = None
        self.backend = ""
        if self.enabled:
            self.enabled = False
            self.set_enabled(True)

    def _status(self, state: str):
        self.state = state
        self.emit("voice_status", state=state, backend=self.backend)

    def _load(self):
        if config.tts_engine == "pocket" and self._lang == "en" and self._load_pocket():
            self._loading = False
            self._status("ready" if self.enabled else "off")
            return
        name = config.tts_model if self._lang == "en" else i18n.info(self._lang)["tts_model"]
        try:
            if not name:
                raise ImportError("no MMS-TTS voice for this language")
            import torch
            from transformers import AutoTokenizer, VitsModel

            tok = AutoTokenizer.from_pretrained(name)
            model = VitsModel.from_pretrained(name).eval()
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

    def _load_pocket(self) -> bool:
        try:
            from pocket_tts import TTSModel

            model = TTSModel.load_model()
            self._voice = model.get_state_for_audio_prompt(config.tts_voice)
        except Exception:  # noqa: BLE001 - not installed or no weights: MMS-TTS speaks instead
            return False
        self._tok = None
        self._model = model
        self.backend = "Pocket TTS"
        return True

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
            if config.speech_log:
                try:
                    import json

                    with open(config.speech_log, "a") as f:
                        f.write(json.dumps({"t": time.time(), "text": text, "lang": self._lang}) + "\n")
                except OSError:
                    pass
            try:
                if self.backend == "Pocket TTS" and self._model is not None:
                    stream = self._play_pocket(text, stream)
                elif self._model is not None:
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

    @staticmethod
    def _stream(stream, rate: int):
        """The output stream, reopened when the voice's sample rate differs (Pocket 24 kHz, MMS 16 kHz)."""
        import sounddevice as sd

        if stream is not None and int(stream.samplerate) != int(rate):
            stream.close()
            stream = None
        if stream is None:
            stream = sd.OutputStream(samplerate=rate, channels=1, dtype="float32")
            stream.start()
        return stream

    def _play_pocket(self, text: str, stream):
        import numpy as np

        stream = self._stream(stream, self._model.sample_rate)
        for chunk in self._model.generate_audio_stream(self._voice, text, stop=self._cut):
            if self._cut.is_set():
                break
            stream.write(np.ascontiguousarray(chunk.numpy().reshape(-1, 1), dtype=np.float32))
        return stream

    def _play_mms(self, text: str, stream):
        import numpy as np
        import torch

        rate = self._model.config.sampling_rate
        stream = self._stream(stream, rate)
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
        voice = i18n.info(self._lang)["say_voice"]
        p = subprocess.Popen(["say", *(["-v", voice] if voice else []), text])
        while p.poll() is None:
            if self._cut.wait(0.05):
                p.terminate()
                break


class Narrator:
    """Turns the run's events into short spoken lines, in the app's language."""

    VERBS = {"click": "clicking", "double-click": "double_clicking", "right-click": "right_clicking",
             "type into": "typing_into", "hover over": "pointing_at", "drag": "dragging"}

    def __init__(self, speaker: Speaker):
        self.speaker = speaker

    def on_event(self, type: str, data: dict):
        s = self.speaker
        if not s.enabled:
            return
        L = i18n.line
        if type == "chat_reply":
            s.say(data.get("text", ""), important=True)
        elif type == "wake_heard":
            s.say(L("yes"), important=True)
        elif type == "element_found" and data.get("verb") in self.VERBS:
            verb = L(self.VERBS[data["verb"]])
            # Targets are described in English for the models: other languages hear just what's happening.
            s.say(f"{verb} {short_target(data.get('target', ''))}" if i18n.lang() == "en" else verb)
        elif type == "status":
            text = data.get("text") or ""
            m = re.match(r"Opening app: (.+)", text)
            if m:
                s.say(L("opening", m.group(1)))
            elif text.startswith("Opening http"):
                s.say(L("opening", urlparse(text.split(" ", 1)[1]).netloc.removeprefix("www.")))
            elif text.startswith("Fixing line"):
                s.say(L("fixing"))
            elif text.startswith("Known way back"):
                s.say(L("known_way"))
        elif type == "confirm_request":
            first = (data.get("summary") or "").splitlines()[0] if data.get("summary") else L("this_step")
            s.say(L("approval", first), important=True)
        elif type == "ask_user":
            opts = data.get("options") or []
            s.say(data.get("question", "") + (" " + f", {L('or')} ".join(opts) + "?" if opts else ""), important=True)
        elif type == "teach_recording":
            if data.get("recording"):
                s.say(L("recording"), important=True)
            elif not data.get("cancelled"):
                s.say(L("got_it"), important=True)
        elif type == "run_finished":
            status = data.get("status")
            if status == "succeeded":
                said = " ".join(str(r.get("text") or "") for r in data.get("results") or [])
                s.say(L("done", clean(said)[:260]).strip(), important=True)
            elif status == "stopped":
                s.say(L("stopped"), important=True)
            elif status == "declined":
                s.say(L("declined"), important=True)
            else:
                msg = clean(((data.get("error") or {}).get("message") or ""))[:140]
                s.say(L("failed", msg), important=True)
