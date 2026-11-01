"""End-to-end runs with fake models and a synthetic screen."""
from engine.models.fake import DEMO_SCRIPT
from engine.sdk.safety import is_sensitive


def events(host, kind):
    return [d for t, d in host.events if t == kind]


def test_clean_run_succeeds(screen, agent_factory):
    agent, host = agent_factory()
    out = agent.run_task("create invoices", DEMO_SCRIPT)
    assert out["status"] == "succeeded", out
    shown = events(host, "result_ready")
    assert len(shown) == 2 and shown[1]["result"]["title"] == "Output"  # the summary, then the task's outputs
    assert out["outputs"] == {"invoices_created": 3}
    # 3 rows x (New Invoice, Customer, Amount, Save) = 12 grounded actions
    assert out["metrics"]["steps"] == 12
    assert events(host, "line_failed") == []


def test_heals_and_resumes_without_redoing_finished_rows(screen, agent_factory):
    agent, host = agent_factory(fail_on="Save button")
    out = agent.run_task("create invoices", DEMO_SCRIPT)
    assert out["status"] == "succeeded", out
    failed = events(host, "line_failed")
    assert len(failed) == 1 and failed[0]["error"]["code"] == "element_not_found"
    assert failed[0]["line"] == 10  # the Save click (lines 1-3 are the header, 4 is open_app)
    rewritten = events(host, "line_rewritten")
    assert len(rewritten) == 1 and "Save button (alternative)" in rewritten[0]["script"]
    # Every row is marked done exactly once.
    assert len(events(host, "progress_item")) == 3
    assert out["metrics"]["fixes"] == 1 and out["metrics"]["fixes_succeeded"] == 1
    assert "Save button (alternative)" in out["final_script"]


def test_resume_skips_rows_done_before_failure(screen, agent_factory):
    script = '''rows = read_table("orders table")
for row in progress.pending(rows):
    type_into("Customer field", row["name"])
    if row["name"] == "Globex":
        click("Missing button", expect="nothing")
    progress.done(row)
'''
    agent, host = agent_factory(fail_on="Missing button")
    out = agent.run_task("partial", script)
    assert out["status"] == "succeeded", out
    typed = [d["target"] for d in events(host, "element_found") if d["target"] == "Customer field"]
    # Acme typed once, Globex typed twice (failed mid-record, redone), Initech once. Acme is NOT redone.
    assert len(typed) == 4
    assert len(events(host, "progress_item")) == 3


def test_cache_makes_second_run_cheaper(screen, agent_factory):
    agent, host = agent_factory()
    first = agent.run_task("create invoices", DEMO_SCRIPT)["metrics"]
    second = agent.run_task("create invoices", DEMO_SCRIPT)["metrics"]
    assert second["cache_hits"] > 0
    assert second["model_calls"] < first["model_calls"] or first["model_calls"] == 0
    assert second["calls_saved"] >= 2 * second["cache_hits"] - 2


def test_sensitive_action_requires_confirmation_even_without_confirm_flag(screen, agent_factory):
    agent, host = agent_factory(confirm=False)
    out = agent.run_task("send", 'click("Send email button")')
    assert out["status"] == "declined"


def test_stop_ends_run(screen, agent_factory):
    agent, host = agent_factory()
    script = 'while True:\n    wait(0.01)'
    # run_task clears the flag at start, so press STOP from a host hook once the script is running.
    original = host.emit

    def emit(t, **d):
        original(t, **d)
        if t == "line_started":
            agent.stop_event.set()

    host.emit = emit
    out = agent.run_task("loop", script)
    assert out["status"] == "stopped"


def test_stuck_line_asks_user_then_stops(screen, agent_factory):
    # A planner that never fixes anything: same failing target forever.
    agent, host = agent_factory(answers=["stop"])
    from engine.models.fake import FakeGrounder
    from engine.models.grounding import Grounded

    class AlwaysMissing(FakeGrounder):
        def locate(self, img, phrase):
            return Grounded(box=[0, 0, 0, 0], point=(0, 0), found=False, reason="nope")

    agent.models.grounder = AlwaysMissing()
    out = agent.run_task("stuck", 'click("Ghost button")')
    assert out["status"] == "stopped"
    assert len(events(host, "line_failed")) == 4  # 1 + 3 fixes, then ask the user


def test_sensitive_detector():
    assert is_sensitive("Send button")
    assert is_sensitive("Save", "invoice deleted")
    assert not is_sensitive("Search field", "results shown")


def test_never_clicks_behind_own_panel(screen, agent_factory):
    agent, host = agent_factory(answers=["stop"])
    agent.ui_bounds = [0, 0, 1440, 900]  # panel covers the whole (logical) screen
    out = agent.run_task("click", 'click("New Invoice button")')
    assert out["status"] == "stopped"
    assert not [i for i in screen.inputs if i[0] in ("click", "move")]
    assert "behind the agent" in events(host, "line_failed")[0]["error"]["message"]
