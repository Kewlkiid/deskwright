"""Raw input: pyautogui directly, no model calls."""
from __future__ import annotations

from contextlib import contextmanager

from ..config import config
from ..screen import capture as cap
from ..screen import input as inp
from .context import ACTION_LOCK, current
from .errors import StoppedError, WindowLostError
from .safety import MESSAGE_FIELD, ask_approval, is_sensitive, owed_summary


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


def _before_raw(action: str = "", sends: bool = False, commits: bool = True):
    """Check the previous action's expectation (pixel diff only) before the raw input changes the screen, and ask
    first when this input stands in for a step that needed approval or sends a message that was just typed."""
    ctx = current()
    if ctx.pending is not None:
        ctx.resolve_pending(ctx.capture())
    if ctx.owed_confirm and commits:
        ask_approval(ctx, owed_summary(ctx, action))
    elif sends and ctx.typed_target and (MESSAGE_FIELD.search(ctx.typed_target) or is_sensitive(ctx.typed_target)):
        ask_approval(ctx, f"{action}: sends the text typed into “{ctx.typed_target}”")


OWN_APPS = {"Deskwright", "Agent", "Electron"}


def app_in_front(ctx, keys: bool = False) -> None:
    """Keys go to whatever app is in front. If another app has come up over the run's app (the user clicked
    something, a window popped up), bring the run's app back first. For keys, stop if that fails rather than type
    into the wrong app; a click brings its own window forward anyway."""
    if ctx.dry_run or config.fake_screen or not ctx.scope_app:
        return
    try:
        from AppKit import NSWorkspace
    except ImportError:
        return

    from ..screen import ax

    def front() -> str:
        # The topmost ordinary window's owner, read live. NSWorkspace's frontmostApplication goes stale in a
        # process without a running event loop (it kept naming an app the user had long since left).
        try:
            import Quartz as Q

            for w in Q.CGWindowListCopyWindowInfo(Q.kCGWindowListOptionOnScreenOnly | Q.kCGWindowListExcludeDesktopElements, 0) or []:
                b = w.get("kCGWindowBounds") or {}
                if w.get("kCGWindowLayer") == 0 and w.get("kCGWindowAlpha", 1) > 0 and b.get("Width", 0) > 80 \
                        and b.get("Height", 0) > 80 and w.get("kCGWindowOwnerName") not in OWN_APPS:
                    return str(w.get("kCGWindowOwnerName") or "")
        except Exception:  # noqa: BLE001
            pass
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        return str(app.localizedName() or "") if app is not None else ""

    now = front()
    if not now or now == ctx.scope_app or now in OWN_APPS:
        return
    from ..screen.windows import open_app

    ctx.log(f"{now} came in front of {ctx.scope_app}: bringing {ctx.scope_app} back")
    # Through Accessibility first: newer macOS won't let a background process bring an app forward with `open -a`.
    # An app with no window yet (TextEdit just launched) still takes keys like cmd+N once it's frontmost.
    raised = ax.bring_to_front(ctx.scope_app)
    if not raised:
        try:
            open_app(ctx.scope_app)
        except Exception:  # noqa: BLE001
            pass
    ctx.sleep(0.5)
    ctx.invalidate_window()
    if keys and not raised and front() not in (ctx.scope_app, *OWN_APPS):
        raise WindowLostError(f"{front()} is in front of {ctx.scope_app}, so keys and clicks would go to the wrong app.",
                              fix=f"Bring {ctx.scope_app} to the front (open_app) and retry.")


def keys_reach_app(ctx, *keys: str) -> None:
    """Raise instead of typing into the void when a system dialog (a Dictation prompt, a permission alert) holds
    the keyboard focus. Escape still goes through: it's how such a dialog is dismissed."""
    if ctx.dry_run or config.fake_screen or (keys and all(inp.norm_key(k) in ("escape", "esc") for k in keys)):
        return
    app_in_front(ctx, keys=True)
    from ..screen import ax

    thief = ax.focus_thief()
    if thief:
        raise WindowLostError(
            f"A system dialog has the keyboard focus, so keys would go to it, not the app ({thief}).",
            fix="Dismiss that dialog first (its Not Now / Cancel / OK button, or press('escape')), then retry.",
            detail={"dialog": thief})


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


def restore_typed(ctx, text: str) -> None:
    """Put back exactly what was typed when the app's auto-capitalisation/auto-correct changed it."""
    if ctx.dry_run or config.fake_screen or not any(c.isalpha() for c in text):
        return
    import re

    from ..screen import ax

    # Auto-capitalisation lands a moment after the word ends, so a sentence starting lowercase is watched for ~1 s.
    rounds = 4 if re.search(r"(?:^|[.!?]\s+)[a-z]", text) else 1
    for _ in range(rounds):
        ctx.sleep(0.25)
        if ax.restore_typed(ctx.cache_key(), text):
            ctx.log(f"auto-correct changed the typed text; restored {text[:40]!r} via accessibility")
            return


def type_text(text: str) -> None:
    """Type text at the current keyboard focus. No model call."""
    with ACTION_LOCK:
        text = str(text)
        _before_raw(commits=False)
        keys_reach_app(current())
        current().status(f"Typing: {text[:40]}")
        current().emit("keys", kind="type", text=text[:80])  # the overlay shows keyboard steps too
        for i in range(0, len(text), 40):
            run_input(inp.type_text, text[i : i + 40])
        restore_typed(current(), text)
        _after_raw(f"type_text({text[:40]!r})")


def press(key: str, times: int = 1) -> None:
    """Press a key, e.g. press("enter"), press("tab", times=3). Names: enter, tab, escape, backspace, delete,
    up, down, left, right, home, end, pageup, pagedown, space, f1-f12."""
    with ACTION_LOCK:
        _before_raw(f"Press {key}", sends=inp.norm_key(key) in ("enter", "return"))
        keys_reach_app(current(), key)
        current().status(f"Pressing: {key}")
        current().emit("keys", kind="press", keys=[key], times=times)
        _announce_escape(key)
        run_input(inp.press, key, times)
        _after_raw(f"press({key!r}, times={times})")


def hotkey(*keys: str) -> None:
    """Press a key combination, e.g. hotkey("cmd", "s"). "cmd" is Command on macOS and Ctrl elsewhere."""
    with ACTION_LOCK:
        _before_raw("Shortcut " + "+".join(keys), sends=any(inp.norm_key(k) in ("enter", "return") for k in keys))
        keys_reach_app(current(), *keys)
        current().status("Shortcut: " + "+".join(keys))
        current().emit("keys", kind="shortcut", keys=list(keys))
        _announce_escape(*keys)
        run_input(inp.hotkey, *keys)
        current().invalidate_window()
        _after_raw(f"hotkey{keys}")


def scroll(amount: int, pane: str = "") -> None:
    """Scroll by `amount` (negative = down, positive = up, about 3 lines per unit). `pane` names what to scroll when
    the app has several ("channel list", "messages"); otherwise the pane under the pointer, or the main content."""
    with ACTION_LOCK:
        _before_raw(commits=False)
        from .actions import point_at_content

        point_at_content(current(), only_if_outside=not pane, target=pane)
        current().status(f"Scrolling {'down' if amount < 0 else 'up'}")
        current().emit("keys", kind="scroll", text="down" if amount < 0 else "up")
        run_input(inp.scroll, int(amount))
        _after_raw(f"scroll({amount})")


def clear_focused_input() -> None:
    """Select everything in the focused text field and delete it."""
    with ACTION_LOCK:
        _before_raw(commits=False)
        run_input(inp.select_all)
        run_input(inp.press, "backspace")
        _after_raw("clear_focused_input()")
