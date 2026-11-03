"""The never-open list (config.never_open): no path opens, focuses or pre-starts those apps or their websites."""
import pytest

from engine import agent
from engine.screen import windows
from engine.sdk import apps, browser
from engine.sdk.errors import BlockedAppError


def test_slack_is_blocked_by_default_in_any_form():
    assert windows.blocked_app("Slack") and windows.blocked_app("slack") and windows.blocked_app("https://app.slack.com/client")
    assert not windows.blocked_app("Discord") and not windows.blocked_app("Google Chrome")


def test_open_app_refuses_before_launching(monkeypatch):
    launched = []
    monkeypatch.setattr(windows.subprocess, "run", lambda *a, **k: launched.append(a))
    with pytest.raises(PermissionError):
        windows.open_app("Slack")
    assert launched == []


def test_sdk_calls_raise_a_non_retryable_error(monkeypatch):
    class Ctx:
        dry_run = False

        def check_stop(self):
            pass

    monkeypatch.setattr(apps, "current", lambda: Ctx())
    monkeypatch.setattr(browser, "current", lambda: Ctx())
    for call in (lambda: apps.open_app("Slack"), lambda: apps.focus_window("Slack"),
                 lambda: browser.open_url("https://slack.com")):
        with pytest.raises(BlockedAppError) as e:
            call()
        assert e.value.retryable is False


def test_pre_start_skips_blocked_apps(monkeypatch):
    started = []
    monkeypatch.setattr(agent, "named_apps", lambda task: ["Slack", "Discord"])
    monkeypatch.setattr(agent, "running_apps", lambda: set())
    monkeypatch.setattr(agent.config, "fake_screen", False)
    import subprocess

    monkeypatch.setattr(subprocess, "Popen", lambda args, **k: started.append(args[-1]))
    agent.warm_up_apps("post it in Slack, Discord or Teams")
    assert started == ["Discord"]


def test_list_comes_from_config(monkeypatch):
    monkeypatch.setattr(windows, "blocked_app", windows.blocked_app)
    from engine.config import config

    monkeypatch.setattr(config, "never_open", "Slack, Messages")
    assert windows.blocked_app("Messages") and windows.blocked_app("Slack")
