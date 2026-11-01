"""Chooses the grounding method per element: SAM 3.1 first, the labelled grid (Muse Spark, or Gemma on OpenRouter)
as the backup.

  auto (default): try SAM; if it can't find the element or errors, retry the same step with the grid. After
                  SAM_STRIKES failures in one run, the grid goes first for the rest of that run.
  sam / grid:     use only that method. Scripts and the repair module switch with use_grounding("grid").

Each run starts back in auto with a clean failure count (reset() is called when a run starts).
"""
from __future__ import annotations

from PIL import Image

from .grounding import Grounded

SAM_STRIKES = 3
MODES = ("auto", "sam", "grid")


class GroundingRouter:
    def __init__(self, sam=None, grid=None):
        if sam is None and grid is None:
            raise ValueError("GroundingRouter needs at least one grounder")
        self.sam, self.grid = sam, grid
        self.reset()

    def reset(self):
        self.mode = "auto"
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
            chain = [self.grid]
        elif self.sam_failures >= SAM_STRIKES:
            chain = [self.grid, self.sam]
        else:
            chain = [self.sam, self.grid]
        return [g for g in chain if g is not None]

    @property
    def label(self) -> str:
        """The method that will be tried first, for the overlay."""
        return getattr(self.order()[0], "label", "")

    def locate(self, img: Image.Image, phrase: str) -> Grounded:
        tried = []
        result = None
        for g in self.order():
            label = getattr(g, "label", type(g).__name__)
            try:
                result = g.locate(img, phrase)
            except Exception as e:  # a grounder bug or API error must not end the step if a backup exists
                result = Grounded(box=[0, 0, 0, 0], point=(0, 0), found=False, reason=f"{label} failed: {e}")
            result.label = label
            if g is self.sam:
                self.sam_failures += 0 if result.found else 1
            if result.found:
                return result
            tried.append(f"{label}: {result.reason}")
        result.reason = " / ".join(tried)
        return result
