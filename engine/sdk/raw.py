"""Raw input: pyautogui directly, no model calls."""
from __future__ import annotations

from contextlib import contextmanager

from ..config import config
from ..screen import capture as cap
from ..screen import input as inp
from .context import ACTION_LOCK, current
from .errors import StoppedError


@contextmanager
def guarded():
    """Turn pyautogui's corner failsafe into StoppedError."""
    try:
        yield
    except inp.failsafe_exception() as e:  # type: ignore[misc]
        current().stop_event.set()
        raise StoppedError("Failsafe: mouse moved to a screen corner") from e


def run_input(fn, *args, **kwargs):
    ctx = current()
    ctx.check_stop()
    if config.fake_screen:
        ctx.log(f"[fake screen] {fn.__name__}{args}")
        cap.bump_fake_screen()
        return
    if ctx.dry_run and fn is not inp.move:
        ctx.log(f"[dry run] {fn.__name__}{args}")
        if fn in (inp.click, inp.drag):
            with guarded():
                inp.move(*args[:2])
        return
    with guarded():
        fn(*args, **kwargs)


def _before_raw():
    """Check the previous action's expectation (pixel diff only) before the raw input changes the screen."""
    ctx = current()
    if ctx.pending is not None:
        ctx.resolve_pending(ctx.capture())


def _announce_escape(*keys: str):
    """The UI stops the run on Esc; tell it this Esc comes from the script, not from the user."""
    if any(inp.norm_key(k) in ("escape", "esc") for k in keys):
        current().emit("suppress_esc")
        current().sleep(0.05)


def _after_raw(action: str):
    ctx = current()
    ctx.metrics.steps += 1
    ctx.log(action)
    ctx.settle(1.0)
    ctx.push_metrics()


def type_text(text: str) -> None:
    """Type text at the current keyboard focus. No model call."""
    with ACTION_LOCK:
        text = str(text)
        _before_raw()
        current().status(f"Typing: {text[:40]}")
        for i in range(0, len(text), 40):
            run_input(inp.type_text, text[i : i + 40])
        _after_raw(f"type_text({text[:40]!r})")


def press(key: str, times: int = 1) -> None:
    """Press a key, e.g. press("enter"), press("tab", times=3). Names: enter, tab, escape, backspace, delete,
    up, down, left, right, home, end, pageup, pagedown, space, f1-f12."""
    with ACTION_LOCK:
        _before_raw()
        current().status(f"Pressing: {key}")
        _announce_escape(key)
        run_input(inp.press, key, times)
        _after_raw(f"press({key!r}, times={times})")


def hotkey(*keys: str) -> None:
    """Press a key combination, e.g. hotkey("cmd", "s"). "cmd" is Command on macOS and Ctrl elsewhere."""
    with ACTION_LOCK:
        _before_raw()
        current().status("Shortcut: " + "+".join(keys))
        _announce_escape(*keys)
        run_input(inp.hotkey, *keys)
        current().invalidate_window()
        _after_raw(f"hotkey{keys}")


def scroll(amount: int) -> None:
    """Scroll at the current mouse position. Negative scrolls down, positive scrolls up (about 3 lines per unit)."""
    with ACTION_LOCK:
        _before_raw()
        current().status(f"Scrolling {'down' if amount < 0 else 'up'}")
        run_input(inp.scroll, int(amount))
        _after_raw(f"scroll({amount})")


def clear_focused_input() -> None:
    """Select everything in the focused text field and delete it."""
    with ACTION_LOCK:
        _before_raw()
        run_input(inp.select_all)
        run_input(inp.press, "backspace")
        _after_raw("clear_focused_input()")
