"""Apps and windows through the OS launcher and window list, verified by screenshot."""
from __future__ import annotations

import time

from ..screen import windows
from .context import ACTION_LOCK, current
from .errors import ElementNotFoundError, WindowLostError
from .questions import _check


def _front_matches(name: str) -> bool:
    w = windows.active_window()
    n = name.lower()
    return n in (w.get("app") or "").lower() or n in (w.get("title") or "").lower()


def open_app(name: str) -> None:
    """Open (or switch to) an application by name, e.g. open_app("Safari"), and wait until it is in front."""
    ctx = current()
    with ACTION_LOCK:
        ctx.check_stop()
        ctx.status(f"Opening app: {name}")
        ctx.pending = None
        if ctx.dry_run:
            ctx.log(f"[dry run] open_app({name!r})")
            ctx.set_scope(name)
            return
        try:
            windows.open_app(name)
        except Exception as e:
            raise ElementNotFoundError(f"Could not open app {name!r}: {e}", fix="Check the app name.") from e
        deadline = time.time() + 10
        while time.time() < deadline:
            ctx.sleep(0.4)
            if _front_matches(name):
                break
        ctx.settle()
        ctx.invalidate_window()
        if not _front_matches(name) and not _check(ctx, f"the {name} app is open and in front")["result"]:
            raise WindowLostError(f"{name} did not come to the front", screenshot=ctx.last_shot.image if ctx.last_shot else None)
        ctx.set_scope(name)  # from now on the agent looks at this app's window
        ctx.metrics.steps += 1
        ctx.log(f"open_app({name!r})")
        ctx.push_metrics()


def focus_window(title: str) -> None:
    """Bring the window whose app name or title contains `title` to the front."""
    ctx = current()
    with ACTION_LOCK:
        ctx.check_stop()
        ctx.status(f"Focusing window: {title}")
        ctx.pending = None
        if ctx.dry_run:
            ctx.log(f"[dry run] focus_window({title!r})")
            return
        ok = windows.focus_window(title)
        ctx.settle(1.0)
        ctx.invalidate_window()
        if not ok and not _front_matches(title):
            raise WindowLostError(f"No window matching {title!r} could be focused")
        ctx.set_scope(windows.active_window().get("app") or title)  # look at the app that owns that window
        ctx.metrics.steps += 1
        ctx.log(f"focus_window({title!r})")


def active_window() -> str:
    """Name of the frontmost app and window, e.g. "Safari | Orders - Acme"."""
    w = windows.active_window()
    return " | ".join(v for v in (w.get("app"), w.get("title")) if v)
