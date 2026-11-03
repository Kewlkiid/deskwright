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


def test_input_values_dont_count_as_extra_details():
    # Rerunning a taught task with new values must not be treated as "the request adds details": those are inputs.
    task = {"name": "calendar event", "description": "Team standup tomorrow at 10am",
            "script": 'INPUTS = {"event_title": "str: title", "day": "str: day", "start_time": "str: time"}\nOUTPUTS = {}\n'}
    req = "add record the voice over tomorrow at 2 PM to my calendar"
    assert len(agent._uncovered_words(req, task)) >= 2  # without the parsed inputs: looks like extra details
    extra = agent._uncovered_words(req, task, {"event_title": "record the voice over", "day": "tomorrow",
                                               "start_time": "2 PM"})
    assert len(extra) < 2  # the saved task runs (a fresh program is written only from 2 extra words up)


def test_taught_tasks_get_a_description_from_their_steps():
    script = ('INPUTS = {"day": "str: day", "start_time": "str: time", "event_title": "str: title"}\nOUTPUTS = {}\n'
              'open_app("Calendar")\n# Step 1: create a new calendar event at that time\ndouble_click("slot")\n'
              '# Step 2: type the event title\ntype_text("x")\n')
    d = agent.describe_script("calendar event", script)
    assert "create a new calendar event" in d and "day, start_time, event_title" in d


def test_relative_days_become_calendar_labels():
    import datetime

    from engine.sdk.task_io import _calendar_day

    t = datetime.date.today() + datetime.timedelta(days=1)
    assert _calendar_day("tomorrow", "str: the day, e.g. Mon 2") == f"{t:%a} {t.day}"
    assert _calendar_day("Mon 2", "str: the day, e.g. Mon 2") == "Mon 2"
    assert _calendar_day("tomorrow", "str: a note") == "tomorrow"  # only when the input looks like a calendar day
