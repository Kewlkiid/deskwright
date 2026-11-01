"""Learned detours: ways back to a step after it went wrong.

When healing fixes a step, the fixer also says what wrong state the failure left behind ("Nitro gift popup is open",
"on the Settings page") and how to get back from it (`press("escape")`). That pair is a detour, attached to the
corrected step. The saved script stays clean; detours only run when that step fails again and the screen looks like
the remembered wrong state: undo, drop the step's stale cache entries, retry the step. No model call.
Each fix can add another detour, so a task learns several ways back over time.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field

from PIL import Image

from ..screen.fingerprint import hamming, screen_hash  # noqa: F401 - screen_hash used by the healer

# How close the current screen must look to the remembered wrong state (the coarse screen hash, as in the cache).
# Up to EXACT_DIST it's taken as the same screen; between that and MATCH_DIST the vision model confirms first.
EXACT_DIST = 6
MATCH_DIST = 14
MAX_USES_PER_RUN = 2  # a detour that doesn't get the step through twice is not the answer this time


def step_key(src: str) -> str:
    """A step's identity across line shifts: its exact code, spacing ignored (the strings name the element, so they
    count: click("Save") and click("Cancel") are different steps)."""
    return re.sub(r"\s+", " ", src or "").strip()


def targets_in(src: str) -> list[str]:
    """String literals in a line: the element descriptions whose cache entries a retry should drop."""
    return [m[1:-1] for m in re.findall(r"\"[^\"]*\"|'[^']*'", src or "")]


def remainder_from(script: str, line: int) -> str:
    """Source from the top-level statement containing `line` to the end: re-running it retries the step.
    Loops over progress.pending() skip records already done, so re-entering a loop is safe."""
    tree = ast.parse(script)
    lines = script.splitlines()
    for stmt in tree.body:
        if stmt.lineno <= line <= (stmt.end_lineno or stmt.lineno):
            return "\n".join(lines[stmt.lineno - 1 :])
    return "\n".join(lines[line - 1 :])


@dataclass
class Detour:
    step: str  # step_key of the step it belongs to
    when: str  # the wrong state, in words
    screen: str  # screen hash of the wrong state
    window: str  # app|window it happened in
    recover: str  # code that gets back to where the step should start
    source: str = ""  # the step's code, for display
    id: int | None = None
    uses: int = 0
    used_this_run: int = field(default=0, compare=False)

    def to_dict(self) -> dict:
        return {"step": self.step, "when": self.when, "screen": self.screen, "window": self.window,
                "recover": self.recover, "source": self.source}


def find(detours: list[Detour], src: str, window: str, img: Image.Image) -> tuple[Detour, int] | None:
    """The learned detour for this step whose wrong state looks most like the current screen, with the distance."""
    key = step_key(src)
    current = screen_hash(img)
    best, best_dist = None, MATCH_DIST + 1
    for d in detours:
        if d.step != key or d.used_this_run >= MAX_USES_PER_RUN:
            continue
        if d.window and window and d.window.split("|")[0] != window.split("|")[0]:
            continue
        dist = hamming(current, d.screen)
        if dist < best_dist:
            best, best_dist = d, dist
    return (best, best_dist) if best else None
