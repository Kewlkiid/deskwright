"""Waiting: plain sleeps, and condition polling gated by frame diff so the model is only asked when the screen changes."""
from __future__ import annotations

import time

from ..screen.fingerprint import frame_diff
from .context import ACTION_LOCK, current
from .errors import AgentTimeoutError
from .questions import _check

CHANGE_GATE = 0.5
STILL_SECONDS = 8.0  # the screen sat unchanged this long after a "no": stop waiting


def wait(seconds: float) -> None:
    """Pause for a number of seconds (max 120)."""
    ctx = current()
    ctx.status(f"Waiting {seconds}s")
    ctx.sleep(max(0.0, min(float(seconds), 120.0)))


def wait_for(condition: str, timeout: float = 20) -> bool:
    """Wait until the condition is visibly true on screen (e.g. "search results are shown").
    Raises TimeoutError after `timeout` seconds."""
    ctx = current()
    deadline = time.time() + max(1.0, min(float(timeout), 300.0))
    last_checked, checked_at, reason = None, 0.0, ""
    with ACTION_LOCK:
        ctx.status(f"Waiting for: {condition}")
        while time.time() < deadline:
            shot = ctx.capture()
            if last_checked is None or frame_diff(last_checked, shot.image) > CHANGE_GATE:
                verdict = _check(ctx, condition, shot)
                if verdict["result"]:
                    ctx.emit("expect_met", line=ctx.current_line, segment=ctx.segment, expect=condition)
                    ctx.push_metrics()
                    return True
                last_checked, checked_at = shot.image, time.time()
                reason = str(verdict.get("reason") or verdict.get("observation") or "")
            elif time.time() - checked_at > STILL_SECONDS:
                # Nothing on screen has moved since the check said no (a welcome sheet, a dialog in the way):
                # waiting out the full timeout won't change that.
                raise AgentTimeoutError(
                    f'The screen stopped changing and "{condition}" still isn\'t true' +
                    (f": {reason}" if reason else ""),
                    screenshot=shot.image, detail={"condition": condition})
            ctx.sleep(0.7)
    raise AgentTimeoutError(
        f'Timed out after {timeout}s waiting for "{condition}"',
        screenshot=ctx.last_shot.image if ctx.last_shot else None,
        detail={"condition": condition},
    )
