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


def name_pattern() -> str:
    """The start words: config.wake_word ("agent,deskwright"). "Deskwright" also as recognition tends to write it."""
    alts = []
    for w in config.wake_word.split(","):
        w = w.strip().lower()
        if not w:
            continue
        if w == "deskwright":
            alts.append(r"desk\W?(?:wright|right|write|rite|ride)")
        else:
            alts.append(re.escape(w))
    return "(?:" + "|".join(alts or ["agent"]) + ")"


def wake_pattern() -> re.Pattern:
    """A start word, optionally after a greeting: "agent", "deskwright", "hey agent", "ok deskwright"..."""
    return re.compile(rf"^\W*(?:(?:hey|hi|ok|okay|yo)\W+)?{name_pattern()}\b\W*", re.I)


def match_wake(text: str) -> tuple[bool, str]:
    """(heard the start word, what was said after it)."""
    m = wake_pattern().match(text or "")
    if not m:
        return False, ""
    return True, text[m.end():].strip()


# Spoken commands besides "<start word>, <task>". Most work with or without the start word; the app only acts on
# approve/decline when an approval is waiting and on send when there's text in the box.
CLOSE_WORDS = r"(?:send|send it|submit|done|over|enter|that's it|that is it)"
APPROVE = (r"approve|approved|i approve|approve it|approve that|yes|yeah|yep|yup|sure|ok(?:ay)?(?: do it)?|do it|"
           r"go ahead|go for it|allow(?: it)?|accept(?: it)?|confirm(?:ed)?|yes please|yes do it|sounds good")
DECLINE = (r"(?:decline|declined|deny|denied|reject)(?: it| that)?|no|nope|don'?t|do not|don'?t do it|never ?mind|"
           r"no thanks")
SEND = (r"sen[dt](?: it| that| the message| message)?|submit(?: it| that)?|hit (?:send|enter)|press (?:send|enter)|"
        r"post it|enter|go")
STOP = r"stop|stop it|stop that|stop stop|halt|abort|cancel|cancel (?:it|that|the task)|stop the task|stop everything"
HUSH = r"stop talking|be quiet|quiet|shush|shut up|silence|hush|enough|stop speaking"


def _commands(name: str) -> list[tuple[str, re.Pattern]]:
    a = rf"(?:(?:hey|hi|ok|okay)\W+)?{name}"  # "agent", "hey agent", "deskwright"
    opt = rf"(?:{a}\W+)?"  # the start word in front is optional
    tail = rf"(?:\W+{name})?\W*$"  # ...and so is one at the end ("send it agent")

    def cmd(words: str) -> str:
        return rf"^\W*{opt}(?:{words}){tail}"

    return [
        # "enter input <text>", "agent input <text>", "task input <text>", "type <text>": typed in and sent; a trailing
        # close word ("... send", "... done") is dropped
        ("input", re.compile(rf"^\W*(?:enter|{a}|task|type)\W+input\W+(?P<text>.+?)(?:\W+{CLOSE_WORDS})?\W*$", re.I)),
        ("teach_stop", re.compile(cmd(r"(?:i'?m\W+|i\W+am\W+|we'?re\W+)?(?:done|finish(?:ed)?|stop(?:ped)?)\W+(?:teaching|recording)"), re.I)),
        ("teach_cancel", re.compile(cmd(r"cancel\W+(?:teaching|recording|the\W+demo(?:nstration)?)"), re.I)),
        ("teach", re.compile(rf"^\W*(?:{a}\W+teach(?:\W+mode)?|teach\W+mode|teach\W+{name}|let\W+me\W+teach\W+you"
                             rf"(?:\W+{name})?|{a}\W+let\W+me\W+teach\W+you)\W*$", re.I)),
        # "agent save task", "save that", "save it as a task", "save task as morning report"
        ("save", re.compile(rf"^\W*(?:{a}\W+save|save(?=\W+(?:it|that|this|task|the\W+task)))(?:\W+(?:it|that|this))?"
                            rf"(?:\W+(?:the\W+)?task|\W+as\W+a\W+task)?(?:\W+(?:as|called|named)\W+(?P<text>.+?))?"
                            rf"(?:\W+{name})?\W*$", re.I)),
        ("hush", re.compile(cmd(HUSH), re.I)),
        ("stop", re.compile(cmd(STOP), re.I)),
        ("approve", re.compile(cmd(APPROVE), re.I)),
        ("decline", re.compile(cmd(DECLINE), re.I)),
        # "sent" too: on-device recognition often hears "send" as "sent"
        ("send", re.compile(cmd(SEND), re.I)),
        ("listen_off", re.compile(rf"^\W*{a}\W+stop\W+listening\W*$", re.I)),
    ]


def parse_voice(text: str) -> tuple[str, str] | None:
    """What an utterance asks for: ("input", text), ("approve"|"decline"|"send"|"stop"|"hush"|"teach"|"teach_stop"|
    "teach_cancel"|"save"|"listen_off", ""), ("task", text) after a start word, ("wake", "") for a bare start word,
    or None (not for the agent)."""
    text = (text or "").strip()
    name = name_pattern()
    for action, pat in _commands(name):
        m = pat.match(text)
        if m:
            return action, (m.groupdict().get("text") or "").strip()
    heard, rest = match_wake(text)
    if heard:
        return ("task", rest) if rest else ("wake", "")
    return None


def without_spoken(heard: str, spoken: str) -> str:
    """What the microphone heard minus the words Deskwright itself was saying (it hears its own voice while it
    talks): the user's words, roughly in order."""
    said: dict[str, int] = {}
    for w in re.findall(r"[a-z0-9']+", (spoken or "").lower()):
        said[w] = said.get(w, 0) + 1
    out = []
    for w in (heard or "").split():
        k = re.sub(r"[^a-z0-9']", "", w.lower())
        if k and said.get(k, 0) > 0:
            said[k] -= 1
            continue
        out.append(w)
    return " ".join(out)


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
