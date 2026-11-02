"""Keys aren't sent while a system dialog holds the keyboard focus."""
import pytest

from engine.screen import ax
from engine.sdk import raw
from engine.sdk.errors import WindowLostError


class Ctx:
    dry_run = False


def test_dialog_with_focus_blocks_keys(monkeypatch):
    monkeypatch.setattr(raw.config, "fake_screen", False)
    monkeypatch.setattr(ax, "focus_thief", lambda: "DictationIM: Do you want to enable Dictation?")
    with pytest.raises(WindowLostError) as e:
        raw.keys_reach_app(Ctx(), "cmd", "o")
    assert "Dictation" in str(e.value)
    raw.keys_reach_app(Ctx(), "escape")  # Esc dismisses it, so it still goes through


def test_no_dialog_lets_keys_through(monkeypatch):
    monkeypatch.setattr(raw.config, "fake_screen", False)
    monkeypatch.setattr(ax, "focus_thief", lambda: None)
    raw.keys_reach_app(Ctx(), "a")
