"""Apps and windows through the OS launcher and window list, verified by screenshot."""
from __future__ import annotations

import time

from ..config import config
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
        if windows.blocked_app(name):
            from .errors import BlockedAppError

            raise BlockedAppError(f"{name} is on the never-open list, so Deskwright won't open it.")
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
        nudged = False
        while time.time() < deadline:
            ctx.sleep(0.4)
            if _front_matches(name):
                break
            if not nudged and time.time() > deadline - 8.5 and not config.fake_screen:
                # Running but not coming forward (macOS limits a background process activating apps): raise it
                # through Accessibility instead.
                from ..screen import ax

                nudged = ax.bring_to_front(name)
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
        if windows.blocked_app(title):
            from .errors import BlockedAppError

            raise BlockedAppError(f"{title} is on the never-open list, so Deskwright won't switch to it.")
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


def menu(*path: str) -> None:
    """Press a menu-bar item of the current app by its titles, e.g. menu("File", "Open…") or
    menu("View", "Show Sidebar"). Exact and fast (no searching the screen); a trailing "…" can be left out."""
    ctx = current()
    with ACTION_LOCK:
        ctx.check_stop()
        app = ctx.scope_app or (windows.active_window().get("app") or "")
        ctx.status("Menu: " + " > ".join(path))
        if ctx.dry_run or config.fake_screen:
            ctx.log(f"[dry run] menu{path}")
            return
        from ..screen import ax

        # Same look as a click: the menu-bar title it opens gets the box and the pointer ripple.
        box = ax.menu_title_box(app, path[0]) if path else None
        if box:
            point = [(box[0] + box[2]) / 2, (box[1] + box[3]) / 2]
            ctx.emit("element_found", target=" › ".join(path), verb="click", line=ctx.current_line,
                     segment=ctx.segment, box=box, point=point, from_cache=False, source="ax")
            ctx.sleep(config.show_delay)
            ctx.emit("pointer", kind="click", point=point)
        if not ax.press_menu(app, list(path)):
            raise ElementNotFoundError(
                f"No menu item {' > '.join(path)!r} in {app or 'the app'}'s menu bar",
                fix="Check the menu and item titles on screen (they're case-insensitive), or use another route.",
                detail={"target": " > ".join(path)},
            )
        ctx.pending = None
        ctx.settle(1.0)
        ctx.invalidate_window()
        ctx.metrics.steps += 1
        ctx.log(f"menu{path}")
