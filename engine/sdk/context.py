"""RunContext: the state shared by every SDK call during a run.

Holds the single action lock (one mouse, one keyboard), the stop flag, the pending expectation
from the previous action, metrics, and the host that talks to the UI (or the terminal in CLI mode).
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from PIL import Image

from ..config import config
from ..metrics import GLOBAL_METRICS, Metrics
from ..screen import capture as cap
from ..screen.fingerprint import changed_pixels, frame_diff, sig_changed_pixels, signature
from .errors import ExpectationFailedError, NoChangeError, StoppedError

# One mouse and one keyboard: every UI action in the process goes through this lock.
ACTION_LOCK = threading.RLock()

# Erring towards "changed" is safe (it only skips a NoChangeError), so these are low.
SCREEN_CHANGE_MIN = 4  # changed pixels in the 160x100 frame thumbnail
REGION_CHANGE_MIN = 3  # changed pixels in the 24x24 signature of the target's surroundings


class Host(Protocol):
    def emit(self, type: str, **data: Any) -> None: ...
    def ask_user(self, question: str, stop: threading.Event) -> str: ...
    def confirm(self, summary: str, stop: threading.Event) -> bool: ...
    def before_capture(self) -> None: ...
    def after_capture(self) -> None: ...


class NullHost:
    """Host for tests: records events, auto-confirms."""

    def __init__(self, answers: list[str] | None = None, confirm: bool = True):
        self.events: list[tuple[str, dict]] = []
        self.answers = list(answers or [])
        self._confirm = confirm
        self.confirms: list[str] = []  # every approval asked for

    def emit(self, type, **data):
        self.events.append((type, data))

    def ask_user(self, question, stop):
        return self.answers.pop(0) if self.answers else ""

    def confirm(self, summary, stop):
        self.confirms.append(summary)
        return self._confirm

    def before_capture(self):
        pass

    def after_capture(self):
        pass


@dataclass
class Pending:
    """What the previous action was supposed to cause, checked on the next screenshot."""

    expect: str
    action: str
    line: int | None
    explicit: bool  # written by the script (hard) vs. suggested by Spark (soft)
    require_change: bool
    before_small: Image.Image
    region: list | None
    before_region: bytes | None
    target_box: list | None = None  # logical box of the acted-on element, for the overlay verdict chip

    def as_prompt(self) -> dict:
        return {"expect": self.expect, "action": self.action}


@dataclass
class RunContext:
    host: Host
    models: Any
    db: Any
    cache: Any
    task: str = ""
    run_id: int = 0
    task_id: int | None = None
    stop_event: threading.Event = field(default_factory=threading.Event)
    capture_paused: threading.Event = field(default_factory=threading.Event)
    metrics: Metrics = field(default_factory=Metrics)
    progress: Any = None
    pending: Pending | None = None
    current_line: int | None = None
    segment: int = 0
    action_log: list = field(default_factory=list)
    results: list = field(default_factory=list)
    check_cache: dict = field(default_factory=dict)
    last_shot: cap.Shot | None = None
    # Logical [x, y, w, h] of the agent's always-on-top panel; it covers that part of the screen.
    panel_bounds: Any = None
    # Chrome backend: network position before the last browser action, and whether capture/the browser is in use.
    # The app the run is working in (open_app/focus_window/open_url). Screenshots are cropped to its front window, so
    # the models only ever see that app.
    scope_app: str | None = None
    detours: list = field(default_factory=list)  # known ways back to steps (runner/detours.py)
    # Task I/O (runner/schema.py): declared INPUTS/OUTPUTS, values passed in, results recorded with output().
    input_schema: dict = field(default_factory=dict)
    output_schema: dict = field(default_factory=dict)
    inputs: dict = field(default_factory=dict)
    outputs: dict = field(default_factory=dict)
    no_ask: bool = False  # a missing input fails instead of asking (CLI --no-ask)
    new_detours: list = field(default_factory=list)  # learned during this run
    browser_mark: int = 0
    browser_capture: bool = False
    browser_used: bool = False
    debug: Any = None  # runner/debug.py RunDebug when debug folders are on
    # Approval safety (sdk/safety.py): a failed step that needed approval leaves it owed to whatever replaces it;
    # typed_target is the field text was just typed into (Enter there may send it).
    owed_confirm: str | None = None
    typed_target: str | None = None
    _window: tuple[str, float] = ("", 0.0)

    # Control ---------------------------------------------------------------
    def check_stop(self):
        if self.stop_event.is_set():
            raise StoppedError("Stopped by user")

    def sleep(self, seconds: float):
        end = time.time() + seconds
        while time.time() < end:
            self.check_stop()
            time.sleep(min(0.05, max(0.0, end - time.time())))

    @property
    def dry_run(self) -> bool:
        return config.dry_run

    # UI --------------------------------------------------------------------
    def emit(self, type: str, **data):
        try:
            self.host.emit(type, **data)
        except Exception:
            pass
        if self.debug is not None:
            try:
                self.debug.event(type, **data)
                if type == "line_failed" and self.last_shot is not None:
                    self.debug.annotate(self.last_shot.image, "failed", caption="last screenshot before the failure")
            except Exception:  # noqa: BLE001 - debugging must never break a run
                pass

    def status(self, text: str):
        self.emit("status", text=text, line=self.current_line, segment=self.segment)

    def log(self, text: str):
        entry = f"line {self.current_line}: {text}" if self.current_line else text
        self.action_log.append(entry)
        self.action_log[:] = self.action_log[-60:]
        if self.debug is not None:
            self.debug.note(text)

    def push_metrics(self):
        self.emit("metrics", metrics=self.metrics.snapshot())

    # Screen ----------------------------------------------------------------
    def capture(self) -> cap.Shot:
        self.check_stop()
        while self.capture_paused.is_set():
            self.status("Capture paused")
            self.sleep(0.3)
        self.host.before_capture()
        try:
            shot = cap.grab()
        finally:
            self.host.after_capture()
        panel = self.panel_box(shot)
        if panel:
            # The panel is invisible to screenshots but still covers this area for clicks: hide what's behind it.
            shot = cap.Shot(image=cap.paint_box(shot.image, panel), scale=shot.scale, ts=shot.ts)
        if not config.fake_screen:
            self.ensure_scope()
            if self.scope_app:
                from ..screen.windows import app_window_bounds

                bounds = app_window_bounds(self.scope_app)
                if bounds:
                    shot = cap.crop_to_window(shot, bounds)
        self.last_shot = shot
        return shot

    def ensure_scope(self):
        """A run always looks at one app. If the script hasn't named one yet, use the app in front."""
        if self.scope_app:
            return
        app = (self.window() or "").split("|")[0]
        if app and app not in ("Agent", "Electron"):
            self.scope_app = app
            self.log(f"looking at {app} (the app in front)")

    def set_scope(self, app: str | None):
        if app and app != self.scope_app:
            self.scope_app = app
            self.status(f"Looking at {app}")
            self.emit("scope", app=app)

    def panel_box(self, shot: cap.Shot) -> list | None:
        b = self.panel_bounds() if callable(self.panel_bounds) else self.panel_bounds
        if not b or len(b) != 4:
            return None
        return [int(v) for v in shot.logical_to_image([b[0], b[1], b[0] + b[2], b[1] + b[3]])]

    def in_panel(self, shot: cap.Shot, point: tuple[float, float]) -> bool:
        box = self.panel_box(shot)
        return bool(box) and box[0] <= point[0] <= box[2] and box[1] <= point[1] <= box[3]

    def settle(self, max_wait: float = 2.0):
        """Wait for the screen to stop changing after an action (no model calls)."""
        self.sleep(0.25)
        prev = cap.grab().image
        end = time.time() + max_wait
        while time.time() < end:
            self.sleep(0.15)
            cur = cap.grab().image
            if frame_diff(prev, cur) < 0.4:
                return
            prev = cur

    def window(self) -> str:
        if config.fake_screen:
            return "FakeApp|Demo"
        title, ts = self._window
        if time.time() - ts > 1.0:
            from ..screen.windows import window_key

            title = window_key()
            self._window = (title, time.time())
        return title

    def invalidate_window(self):
        self._window = ("", 0.0)

    # Verification -----------------------------------------------------------
    def set_pending(self, shot: cap.Shot, expect: str | None, action: str, region: list | None,
                    explicit: bool, require_change: bool = True):
        if not expect and not require_change:
            self.pending = None
            return
        small = shot.image.convert("L").resize((160, 100))
        reg = None
        if region:
            reg = cap.expand_box(region, shot.size, pad=80, factor=3)
        self.pending = Pending(
            expect=expect or "",
            action=action,
            line=self.current_line,
            explicit=explicit,
            require_change=require_change,
            before_small=small,
            region=reg,
            before_region=signature(shot.image, reg) if reg else None,
            target_box=shot.box_to_logical(region) if region else None,
        )

    @staticmethod
    def screen_changed(p: Pending, shot: cap.Shot) -> bool:
        if changed_pixels(p.before_small, shot.image) >= SCREEN_CHANGE_MIN:
            return True
        if p.region and p.before_region is not None:
            return sig_changed_pixels(signature(shot.image, p.region), p.before_region) >= REGION_CHANGE_MIN
        return False

    def resolve_pending(self, shot: cap.Shot, verdict: bool | None = None, observation: str = ""):
        """Check the previous action's expectation against this screenshot.

        verdict: what Spark said about the expectation in the call it was already making
        (None when no model looked, e.g. a cache hit). Raises ExpectationFailedError / NoChangeError
        attributed to the line of the previous action.
        """
        p = self.pending
        if p is None:
            return
        self.pending = None
        changed = self.screen_changed(p, shot)
        if verdict is True:
            self.emit("expect_met", line=p.line, segment=self.segment, expect=p.expect, box=p.target_box)
            return
        if verdict is False:
            if p.explicit or not changed:
                self.emit("expect_failed", line=p.line, segment=self.segment, expect=p.expect,
                          observation=observation, box=p.target_box)
                raise ExpectationFailedError(
                    f'Expected "{p.expect}" after {p.action}, but the screen shows: {observation or "something else"}',
                    line=p.line,
                    screenshot=shot.image,
                    detail={"expect": p.expect, "observation": observation, "screen_changed": changed},
                )
            self.log(f'soft expectation "{p.expect}" not confirmed ({observation}); screen did change, continuing')
            return
        if p.require_change and not changed:
            self.emit("expect_failed", line=p.line, segment=self.segment, expect=p.expect,
                      observation="nothing changed on screen", box=p.target_box)
            raise NoChangeError(
                f"Nothing changed on screen after {p.action}",
                line=p.line,
                screenshot=shot.image,
                detail={"expect": p.expect},
            )


_current: RunContext | None = None


def set_current(ctx: RunContext | None):
    global _current
    _current = ctx


def current() -> RunContext:
    if _current is None:
        raise RuntimeError("No active run")
    return _current


def current_metrics() -> Metrics:
    return _current.metrics if _current is not None else GLOBAL_METRICS
