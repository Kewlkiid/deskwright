"""Chooses the grounding method per element: SAM 3.1 first, the labelled grid (Muse Spark, or Gemma on OpenRouter)
as the backup.

  auto (default): try SAM (with on-screen text and Accessibility candidates); if it can't find the element or
                  errors, retry the same step with the grid, which snaps to the exact boxes SAM saw.
  grid:           the grid first, then SAM; nothing is ever skipped.
  sam:            SAM only. Scripts switch with use_grounding(...).
sam_failures counts elements the grid found but SAM missed.

Each run starts back in auto with a clean failure count (reset() is called when a run starts).
"""
from __future__ import annotations

from PIL import Image

from ..sdk.errors import StoppedError
from .grounding import Grounded

SAM_STRIKES = 3
MODES = ("auto", "sam", "grid")


class GroundingRouter:
    accepts_extra = True  # passes Accessibility elements on to the grounders that use them
    def __init__(self, sam=None, grid=None):
        if sam is None and grid is None:
            raise ValueError("GroundingRouter needs at least one grounder")
        self.sam, self.grid = sam, grid
        self.reset()

    def reset(self):
        self.mode = "auto"
        self.last_label = ""
        self.sam_failures = 0

    def set_mode(self, mode: str):
        mode = (mode or "").strip().lower()
        if mode not in MODES:
            raise ValueError(f'grounding method must be one of {", ".join(MODES)}, not {mode!r}')
        if mode == "sam" and self.sam is None:
            raise ValueError("SAM 3.1 is not configured (set GROUNDING_MODEL)")
        if mode == "grid" and self.grid is None:
            raise ValueError("Grid grounding is not configured (set GRID_MODEL)")
        self.mode = mode

    def order(self) -> list:
        if self.mode == "sam":
            chain = [self.sam]
        elif self.mode == "grid":
            chain = [self.grid, self.sam]  # grid first, but SAM + text + Accessibility are never skipped
        else:
            chain = [self.sam, self.grid]
        return [g for g in chain if g is not None]

    def _snap_boxes(self, extra: list | None) -> list:
        """Exact boxes the grid can snap to: everything SAM and text found on this screenshot, plus Accessibility."""
        boxes = [b for b, _, _ in (extra or [])]
        sam = self.sam
        if sam is not None and getattr(sam, "pool", None):
            f = getattr(sam, "pool_scale", 1.0)
            boxes += [[v * f for v in b] for b in sam.pool]
        return boxes

    @property
    def label(self) -> str:
        """The method that will be tried first, for the overlay."""
        return getattr(self.order()[0], "label", "")

    def locate(self, img: Image.Image, phrase: str, extra: list | None = None) -> Grounded:
        """extra: the app's Accessibility elements [(box, role, label)] in `img` pixels."""
        tried = []
        result = None
        for g in self.order():
            label = getattr(g, "label", type(g).__name__)
            try:
                if getattr(g, "accepts_snap", False):
                    result = g.locate(img, phrase, snap_to=self._snap_boxes(extra))
                elif getattr(g, "accepts_extra", False):
                    result = g.locate(img, phrase, extra=extra)
                else:
                    result = g.locate(img, phrase)
            except StoppedError:
                raise
            except Exception as e:  # a grounder bug or API error must not end the step if a backup exists
                result = Grounded(box=[0, 0, 0, 0], point=(0, 0), found=False, reason=f"{label} failed: {e}")
            result.label = self.last_label = label
            if result.found:
                if g is self.grid and any(t.startswith(getattr(self.sam, "label", "SAM")) for t in tried):
                    self.sam_failures += 1  # the grid found what SAM missed
                return result
            tried.append(f"{label}: {result.reason}")
        result.reason = " / ".join(tried)
        return result
