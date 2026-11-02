"""Keys aren't sent while a system dialog holds the keyboard focus."""
import pytest

from engine.screen import ax
from engine.sdk import raw
from engine.sdk.errors import WindowLostError


class Ctx:
    dry_run = False
    scope_app = None


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


def test_other_app_in_front_is_sent_back(monkeypatch):
    import sys
    import types

    calls = []
    front = ["Visual Studio Code"]

    class App:
        def localizedName(self):
            return front[0]

    class WS:
        @staticmethod
        def sharedWorkspace():
            return types.SimpleNamespace(frontmostApplication=lambda: App())

    monkeypatch.setitem(sys.modules, "AppKit", types.SimpleNamespace(NSWorkspace=WS))
    monkeypatch.setattr(raw.config, "fake_screen", False)
    import engine.screen.windows as windows

    def open_app(name):
        calls.append(name)
        front[0] = name

    monkeypatch.setattr(windows, "open_app", open_app)

    class C:
        dry_run = False
        scope_app = "Weather"

        def log(self, *a): pass
        def sleep(self, s): pass
        def invalidate_window(self): pass

    raw.app_in_front(C())
    assert calls == ["Weather"]  # brought back before typing

    def stuck(name):
        calls.append(name)  # but it doesn't come to the front

    monkeypatch.setattr(windows, "open_app", stuck)
    front[0] = "Visual Studio Code"
    with pytest.raises(WindowLostError):
        raw.app_in_front(C())
