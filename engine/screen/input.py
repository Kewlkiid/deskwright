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
    if IS_MAC and clicks > 1:
        _mac_multi_click(x, y, button, clicks)
        return
    pg().click(x=x, y=y, button=button, clicks=clicks, interval=0.08)


def _mac_multi_click(x: float, y: float, button: str, clicks: int):
    """A real double (or triple) click. macOS apps tell a double-click by the click count each mouse event carries;
    separate single clicks (what pyautogui sends) all say "1", so Calendar, Finder and others never see one."""
    import Quartz as Q

    down, up, btn = {
        "right": (Q.kCGEventRightMouseDown, Q.kCGEventRightMouseUp, Q.kCGMouseButtonRight),
    }.get(button, (Q.kCGEventLeftMouseDown, Q.kCGEventLeftMouseUp, Q.kCGMouseButtonLeft))
    for n in range(1, clicks + 1):
        for kind in (down, up):
            e = Q.CGEventCreateMouseEvent(None, kind, (x, y), btn)
            Q.CGEventSetIntegerValueField(e, Q.kCGMouseEventClickState, n)
            Q.CGEventPost(Q.kCGHIDEventTap, e)
            time.sleep(0.02)
        time.sleep(0.05)


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
    release_fn()  # a held fn (left by anything) turns e into the emoji picker and d into Dictation
    # pyautogui.write only handles plain ASCII reliably; paste anything else.
    if text.isascii():
        pg().write(text, interval=interval)
    else:
        _paste(text)


# macOS counts arrows, home/end and page keys as fn keys. A synthetic combo with one of them (cmd+left, cmd+down)
# leaves the system thinking fn is still held, and then fn+E opens the emoji picker and fn+D the Dictation prompt:
# typing "New York" came out as "Nw Y". Release fn after any of them.
FN_KEYS = {"left", "right", "up", "down", "home", "end", "pageup", "pagedown", "delete", "fn"}


def release_fn():
    if not IS_MAC:
        return
    try:
        import Quartz

        if Quartz.CGEventSourceKeyState(Quartz.kCGEventSourceStateCombinedSessionState, 63):
            src = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
            up = Quartz.CGEventCreateKeyboardEvent(src, 63, False)  # 63: the fn key
            Quartz.CGEventSetFlags(up, 0)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)
    except Exception:  # noqa: BLE001
        pass


def press(key: str, presses: int = 1):
    release_fn()
    pg().press(norm_key(key), presses=presses, interval=0.05)
    if norm_key(key) in FN_KEYS:
        release_fn()


def hotkey(*keys: str):
    keys = [norm_key(k) for k in keys]
    release_fn()
    pg().hotkey(*keys, interval=0.04)
    if FN_KEYS & set(keys):
        release_fn()


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
