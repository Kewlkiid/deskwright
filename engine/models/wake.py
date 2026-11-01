"""Wake word: "Hey Agent, <task>" spoken while the voice button is on.

The app records each utterance it hears (the page's voice-activity detection) and sends it here. Recognition runs
on this Mac (Speech framework, on-device only), so nothing leaves the machine unless it starts with the wake phrase;
only then does the rest become a task. Without on-device recognition, the cloud voice model is used instead.
"""
from __future__ import annotations

import os
import re
import sys
import tempfile
import time

from ..config import config

try:
    if sys.platform != "darwin":
        raise ImportError
    import Speech  # pyobjc-framework-Speech
    from Foundation import NSURL, NSOperationQueue
except ImportError:
    Speech = None


def wake_pattern() -> re.Pattern:
    """config.wake_word ("agent") preceded by a greeting: "hey agent", "hi agent", "ok agent", "okay agent"."""
    name = re.escape(config.wake_word.strip().lower())
    return re.compile(rf"^\W*(?:hey|hi|ok|okay|yo)\W+{name}\b\W*", re.I)


def match_wake(text: str) -> tuple[bool, str]:
    """(heard the wake phrase, what was said after it)."""
    m = wake_pattern().match(text or "")
    if not m:
        return False, ""
    return True, text[m.end():].strip()


def on_device_available() -> bool:
    if Speech is None:
        return False
    try:
        r = Speech.SFSpeechRecognizer.alloc().init()
        return bool(r and r.isAvailable() and r.supportsOnDeviceRecognition())
    except Exception:  # noqa: BLE001
        return False


def transcribe_on_device(wav: bytes, timeout: float = 12.0) -> str | None:
    """Transcribe a WAV clip with on-device recognition. None only when that isn't available on this Mac; a clip
    with no recognisable speech (Apple reports it as an error) gives ""."""
    if Speech is None:
        return None
    recognizer = Speech.SFSpeechRecognizer.alloc().init()
    if not recognizer or not recognizer.isAvailable() or not recognizer.supportsOnDeviceRecognition():
        return None
    # Results go to the main queue by default, which the engine's worker threads never service: use a private queue.
    recognizer.setQueue_(NSOperationQueue.alloc().init())
    fd, path = tempfile.mkstemp(suffix=".wav")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(wav)
        request = Speech.SFSpeechURLRecognitionRequest.alloc().initWithURL_(NSURL.fileURLWithPath_(path))
        request.setRequiresOnDeviceRecognition_(True)  # never sent to Apple's servers
        out: dict = {}

        def handler(result, error):
            if error is not None:
                out["done"] = True
                return
            if result is not None:
                out["text"] = str(result.bestTranscription().formattedString())
                if result.isFinal():
                    out["done"] = True

        task = recognizer.recognitionTaskWithRequest_resultHandler_(request, handler)
        end = time.time() + timeout
        while not out.get("done") and time.time() < end:
            time.sleep(0.05)
        if not out.get("done"):
            task.cancel()
        return out.get("text") or ""
    finally:
        os.unlink(path)
