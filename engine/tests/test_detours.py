"""Learned detours: a repair that had to undo something leaves a way back for the corrected step; when that step
lands in the same wrong state again, the detour runs without asking the planner."""
import os

from engine.runner.detours import remainder_from, step_key, targets_in


def events(host, kind):
    return [d for t, d in host.events if t == kind]


def test_step_identity_and_retry_source():
    assert step_key('click( "Save" ,  expect="x")') == step_key('click( "Save" , expect="x")')
    assert step_key('click("Save")') != step_key('click("Cancel")')
    assert targets_in('click("Save button", expect="saved")') == ["Save button", "saved"]
    script = 'open_app("A")\nfor r in progress.pending(rows):\n    click("Go")\n    progress.done(r)\nshow("x")'
    assert remainder_from(script, 3).startswith("for r in progress.pending(rows):")  # re-enter the loop
    assert remainder_from(script, 5) == 'show("x")'


class CountingPlanner:
    """Fixes the first failure by closing a popup and clicking a corrected target; counts fixer calls."""

    def __init__(self, base):
        self.base = base
        self.fixes = 0

    def __getattr__(self, name):
        return getattr(self.base, name)

    def fix_script(self, **kw):
        self.fixes += 1
        return {
            "explanation": "Clicked the gift icon instead of the box; closing the popup and clicking the box.",
            "wrong_state": "Gift popup is open",
            "recovery": 'press("escape")',
            "continuation": 'click("Message box")',
            "full_script": 'open_app("Chat")\nclick("Message box")',
        }


def test_a_repair_teaches_a_way_back_that_replays_without_the_planner(screen, agent_factory):
    from engine.models.fake import FakeGrounder

    agent, host = agent_factory(fail_on="Message")
    planner = CountingPlanner(agent.models.planner)
    agent.models.planner = planner
    task_id = agent.db.save_task("message", 'open_app("Chat")\nclick("Message field")')

    # Run 1: the step fails, the fixer undoes the popup and corrects the step; the way back is learned and saved.
    out = agent.run_task("message", agent.db.get_task(task_id=task_id)["script"], task_id)
    assert out["status"] == "succeeded", out
    assert planner.fixes == 1
    learned = agent.db.task_detours(task_id)
    assert len(learned) == 1 and learned[0]["recover"] == 'press("escape")'
    assert learned[0]["step"] == step_key('click("Message box")')
    assert out["final_script"] == 'open_app("Chat")\nclick("Message box")'  # the saved script stays clean

    # Run 2 of the healed task: the corrected step goes wrong again on the same screen -> known detour, no fixer.
    agent.db.save_task("message", out["final_script"], note="self-healed")
    os.environ["AGENT_FAKE_FAIL"] = "Message box"
    agent.models.grounder.sam = FakeGrounder()  # fresh fail-once state for "Message box"
    agent.cache.clear()  # otherwise run 1's cached position makes the step succeed
    host.events.clear()
    out2 = agent.run_task("message", out["final_script"], task_id)
    assert out2["status"] == "succeeded", out2
    assert planner.fixes == 1  # no new model repair
    assert events(host, "detour")[0]["when"] == "Gift popup is open"
    assert agent.db.task_detours(task_id)[0]["uses"] == 1


def test_detours_learned_in_a_chat_run_are_kept_when_the_task_is_saved(screen, agent_factory):
    agent, host = agent_factory(fail_on="Message")
    agent.models.planner = CountingPlanner(agent.models.planner)
    out = agent.run_task("message", 'open_app("Chat")\nclick("Message field")')
    assert out["status"] == "succeeded"
    task_id = agent.save_task("message", out["final_script"])
    assert [d["when_text"] for d in agent.db.task_detours(task_id)] == ["Gift popup is open"]


def test_a_failed_step_drops_its_cached_position(screen, agent_factory, monkeypatch):
    from engine.models.fake import FakeVision

    agent, host = agent_factory(answers=["stop"])
    agent.run_task("warm", 'click("Reset button")')  # caches the position
    window = "TestApp|Orders"
    assert agent.cache.db.query("SELECT COUNT(*) AS n FROM cache WHERE target = ?", ("reset button",))[0]["n"] == 1
    # Next run: the cached click "works" but the expected result never shows (wrong spot).
    monkeypatch.setattr(FakeVision, "check", lambda self, img, cond, prev=None: {"result": False, "reason": "nothing happened"})
    agent.run_task("again", 'click("Reset button", expect="the form is reset")\nwait(1)')
    assert agent.cache.db.query("SELECT COUNT(*) AS n FROM cache WHERE window = ? AND target = ?",
                                (window, "reset button"))[0]["n"] == 0


def test_a_borderline_match_is_confirmed_before_running_the_detour(screen, agent_factory, monkeypatch):
    from engine.runner import detours, healer
    from engine.models.fake import FakeVision
    from engine.sdk.context import set_current

    agent, _ = agent_factory()
    ctx = agent._new_context("t")
    set_current(ctx)
    d = detours.Detour(step=detours.step_key('click("Box")'), when="Gift popup is open", screen="0" * 16,
                       window="", recover='press("escape")')
    ctx.detours = [d]
    asked = []
    try:
        monkeypatch.setattr(detours, "find", lambda *a: (d, detours.EXACT_DIST + 3))
        monkeypatch.setattr(FakeVision, "check", lambda self, img, cond, prev=None: asked.append(cond) or {"result": False})
        assert not healer.try_detour(ctx, {}, 'click("Box")', ctx.capture())  # resembles, but Spark says no
        assert asked == ["Gift popup is open"] and d.used_this_run == 0
        monkeypatch.setattr(detours, "find", lambda *a: (d, 2))
        asked.clear()
        assert healer.try_detour(ctx, {"press": lambda *a, **k: None}, 'click("Box")', ctx.capture())
        assert asked == []  # a near-exact match needs no model call
    finally:
        set_current(None)
