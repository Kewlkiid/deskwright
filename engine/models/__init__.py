"""Model roles. `get_models()` returns real models (Meta API or OpenRouter) or offline fakes."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Models:
    planner: Any
    vision: Any
    grounder: Any
    voice: Any


_models: Models | None = None


def get_models() -> Models:
    global _models
    if _models is None:
        from ..config import config

        if config.fake_models:
            from .fake import FakeGrounder, FakePlanner, FakeVision, FakeVoice
            from .routing import GroundingRouter

            _models = Models(FakePlanner(), FakeVision(), GroundingRouter(sam=FakeGrounder()), FakeVoice())
        else:
            from .client import ModelClient
            from .grid import GridGrounder
            from .grounding import SamGrounder
            from .planner import Planner
            from .routing import GroundingRouter
            from .vision import Vision
            from .voice import Voice

            client = ModelClient(config)
            # SAM 3.1 first, the labelled grid as the backup (see routing.py).
            vision = Vision(client)
            # SAM proposes precise candidate boxes; the vision model picks the one the script means.
            sam = SamGrounder(client, picker=vision.pick_box) if config.grounding_model else None
            grid = GridGrounder(client) if config.grid_model else None
            _models = Models(Planner(client), vision, GroundingRouter(sam, grid), Voice(client))
    return _models


def set_models(models: Models | None):
    """Override the model bundle (tests)."""
    global _models
    _models = models
