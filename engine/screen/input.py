"""Real mouse and keyboard through pyautogui. All coordinates here are logical points.

pyautogui's failsafe stays on: slamming the mouse into a screen corner raises FailSafeException,
which the SDK turns into StoppedError.
"""
from __future__ import annotations

import sys
import time

_pg = None

IS_MAC = sys.platform == "darwin"
TWEEN_SECONDS = 0.25

KEY_ALIASES = {
    "cmd": "command" if IS_MAC else "ctrl",
    "command": "command" if IS_MAC else "ctrl",
    "mod": "command" if IS_MAC else "ctrl",
    "meta": "command" if IS_MAC else "win",
    "control": "ctrl",
    "option": "alt",
    "opt": "alt",
    "return": "enter",
    "esc": "escape",
    "del": "delete",
    "arrowup": "up",
    "arrowdown": "down",
    "arrowleft": "left",
    "arrowright": "right",
    "pgup": "pageup",
    "pgdn": "pagedown",
}


def pg():
    global _pg
    if _pg is None:
        import pyautogui

        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.02
        _pg = pyautogui
    return _pg


def failsafe_exception():
    return pg().FailSafeException


def norm_key(key: str) -> str:
    k = key.strip().lower()
    return KEY_ALIASES.get(k, k)


def move(x: float, y: float, duration: float = TWEEN_SECONDS):
    pg().moveTo(x, y, duration=duration, tween=pg().easeInOutQuad)


def click(x: float, y: float, button: str = "left", clicks: int = 1):
    move(x, y)
    pg().click(x=x, y=y, button=button, clicks=clicks, interval=0.08)


def drag(x1: float, y1: float, x2: float, y2: float, duration: float = 0.6):
    move(x1, y1)
    pg().mouseDown(button="left")
    try:
        pg().moveTo(x2, y2, duration=duration, tween=pg().easeInOutQuad)
    finally:
        pg().mouseUp(button="left")


def scroll(amount: int, x: float | None = None, y: float | None = None):
    """Positive scrolls up, negative scrolls down (pyautogui convention)."""
    if x is not None and y is not None:
        move(x, y, duration=0.1)
    pg().scroll(int(amount))


def _paste(text: str):
    import pyperclip

    try:
        previous = pyperclip.paste()
    except Exception:
        previous = None
    pyperclip.copy(text)
    hotkey("cmd", "v")
    time.sleep(0.05)
    if previous is not None:
        try:
            pyperclip.copy(previous)
        except Exception:
            pass


def type_text(text: str, interval: float = 0.012):
    # pyautogui.write only handles plain ASCII reliably; paste anything else.
    if text.isascii():
        pg().write(text, interval=interval)
    else:
        _paste(text)


def press(key: str, presses: int = 1):
    pg().press(norm_key(key), presses=presses, interval=0.05)


def hotkey(*keys: str):
    pg().hotkey(*[norm_key(k) for k in keys], interval=0.04)


def select_all():
    hotkey("cmd", "a")


def caret_to_end():
    if IS_MAC:
        hotkey("command", "down")
    else:
        hotkey("ctrl", "end")


def mouse_position() -> tuple[int, int]:
    p = pg().position()
    return int(p[0]), int(p[1])
