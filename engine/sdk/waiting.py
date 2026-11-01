"""Waiting: plain sleeps, and condition polling gated by frame diff so the model is only asked when the screen changes."""
from __future__ import annotations

import time

from ..screen.fingerprint import frame_diff
from .context import ACTION_LOCK, current
from .errors import AgentTimeoutError
from .questions import _check

CHANGE_GATE = 0.5


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
    last_checked = None
    with ACTION_LOCK:
        ctx.status(f"Waiting for: {condition}")
        while time.time() < deadline:
            shot = ctx.capture()
            if last_checked is None or frame_diff(last_checked, shot.image) > CHANGE_GATE:
                if _check(ctx, condition, shot)["result"]:
                    ctx.emit("expect_met", line=ctx.current_line, segment=ctx.segment, expect=condition)
                    ctx.push_metrics()
                    return True
                last_checked = shot.image
            ctx.sleep(0.7)
    raise AgentTimeoutError(
        f'Timed out after {timeout}s waiting for "{condition}"',
        screenshot=ctx.last_shot.image if ctx.last_shot else None,
        detail={"condition": condition},
    )
