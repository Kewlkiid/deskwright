import os
import sys
import tempfile
from pathlib import Path

os.environ["AGENT_FAKE_MODELS"] = "1"
os.environ["AGENT_DRY_RUN"] = "1"
os.environ["AGENT_SHOW_DELAY"] = "0"
os.environ.setdefault("AGENT_DATA_DIR", tempfile.mkdtemp(prefix="agent-test-"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import random  # noqa: E402

import pytest  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402


class FakeScreen:
    """Synthetic 1440x900 screen at 2x scale. Every input action bumps `version`, which redraws a noise
    block in the top-left corner, so 'did the screen change' checks behave like a real UI."""

    def __init__(self):
        self.version = 0
        self.inputs: list[tuple] = []

    def bump(self, name, *args):
        self.version += 1
        self.inputs.append((name, args))

    def grab(self):
        from engine.screen.capture import Shot

        img = Image.new("RGB", (2880, 1800), (240, 240, 245))
        d = ImageDraw.Draw(img)
        for i in range(12):  # static "UI" so element patches have texture
            d.rectangle([600 + i * 150, 400 + (i % 4) * 250, 700 + i * 150, 450 + (i % 4) * 250], fill=(40 + i * 15, 90, 200))
            d.text((610 + i * 150, 415 + (i % 4) * 250), f"Btn{i}", fill=(255, 255, 255))
        rnd = random.Random(self.version)
        for y in range(0, 300, 10):
            for x in range(0, 300, 10):
                g = rnd.randint(0, 255)
                d.rectangle([x, y, x + 9, y + 9], fill=(g, g, g))
        return Shot(image=img, scale=2.0)


@pytest.fixture
def screen(monkeypatch, tmp_path):
    from engine.screen import capture, input as inp, windows
    from engine.sdk import context

    fs = FakeScreen()
    monkeypatch.setattr(capture, "grab", fs.grab)
    for name in ("move", "click", "drag", "scroll", "type_text", "press", "hotkey", "select_all", "caret_to_end"):
        monkeypatch.setattr(inp, name, (lambda n: lambda *a, **k: fs.bump(n, *a))(name))
    monkeypatch.setattr(inp, "failsafe_exception", lambda: type("NeverRaised", (Exception,), {}))
    monkeypatch.setattr(windows, "window_key", lambda: "TestApp|Orders")
    monkeypatch.setattr(windows, "app_window_bounds", lambda app: None)  # no real windows in tests
    monkeypatch.setattr(windows, "active_window", lambda: {"app": "TestApp", "title": "Orders"})
    monkeypatch.setattr(context.RunContext, "settle", lambda self, max_wait=2.0: None)
    return fs


@pytest.fixture
def agent_factory(tmp_path):
    from engine.agent import Agent
    from engine.models import Models, set_models
    from engine.models.fake import FakeGrounder, FakePlanner, FakeVision, FakeVoice
    from engine.models.routing import GroundingRouter
    from engine.sdk.context import NullHost
    from engine.store.db import DB

    def make(fail_on: str = "", confirm: bool = True, answers=None):
        os.environ["AGENT_FAKE_FAIL"] = fail_on
        set_models(Models(FakePlanner(), FakeVision(), GroundingRouter(sam=FakeGrounder()), FakeVoice()))
        host = NullHost(answers=answers, confirm=confirm)
        return Agent(host, db=DB(tmp_path / "agent.db")), host

    yield make
    set_models(None)
    os.environ["AGENT_FAKE_FAIL"] = ""
