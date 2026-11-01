"""Task inputs/outputs: the INPUTS/OUTPUTS header, inp(), output(), header preservation on repair, and the CLI's
JSON contract."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from engine.runner.schema import coerce, header_problems, header_source, parse_header, same_schema, split_desc, with_header

ROOT = Path(__file__).resolve().parents[2]

GREET = '''INPUTS = {"customer": "str: customer name", "count": "int: how many times"}
OUTPUTS = {"greeting": "str: the greeting that was made"}

open_app("Invoices")
name = inp("customer")
n = inp("count")
output(greeting="hi " + name + " x" + str(n))
'''


def events(host, kind):
    return [d for t, d in host.events if t == kind]


# ---------------------------------------------------------------- header parsing
def test_header_parses_without_running_the_script():
    h = parse_header(GREET + '\nraise SystemExit("never executed")\n')
    assert h["problems"] == []
    assert h["inputs"] == {"customer": "str: customer name", "count": "int: how many times"}
    assert h["outputs"] == {"greeting": "str: the greeting that was made"}


@pytest.mark.parametrize("script, problem", [
    ('click("x")', "missing INPUTS"),
    ('INPUTS = {}\nclick("x")', "missing OUTPUTS"),
    ('INPUTS = ["a"]\nOUTPUTS = {}', "must map names"),
    ('INPUTS = {"a": 1}\nOUTPUTS = {}', "must map names"),
    ('INPUTS = dict(a="str")\nOUTPUTS = {}', "plain dict literal"),
    ('INPUTS = {}\nINPUTS = {}\nOUTPUTS = {}', "defined twice"),
    ('INPUTS = {"bad name": "str: x"}\nOUTPUTS = {}', "identifiers"),
    ('INPUTS = {', "doesn't parse"),
])
def test_malformed_or_missing_headers_are_reported(script, problem):
    assert any(problem in p for p in header_problems(script)), header_problems(script)


def test_empty_header_is_valid_and_restoring_a_header_keeps_the_body():
    assert header_problems("INPUTS = {}\nOUTPUTS = {}\nopen_app('A')") == []
    damaged = 'OUTPUTS = {"x": "str: renamed"}\nopen_app("Invoices")\nclick("Save")'
    fixed = with_header(damaged, header_source(GREET))
    assert same_schema(GREET, fixed) and fixed.rstrip().endswith('click("Save")')


def test_descriptions_and_coercion():
    assert split_desc("ios|android: target platform") == ("ios|android", "target platform")
    assert split_desc("list[str]: created ids") == ("list[str]", "created ids")
    assert split_desc("just words") == ("str", "just words")
    assert coerce("3", "int: n") == 3 and coerce("yes", "bool: b") is True
    assert coerce('["a", "b"]', "list[str]: x") == ["a", "b"] and coerce("a,b", "list[str]: x") == ["a", "b"]
    assert coerce("ios", "ios|android: p") == "ios"
    with pytest.raises(ValueError):
        coerce("web", "ios|android: p")


# ---------------------------------------------------------------- inp() / output()
def test_inp_uses_passed_values_and_output_returns_them(screen, agent_factory):
    agent, host = agent_factory()
    out = agent.run_task("greet", GREET, inputs={"customer": "Acme", "count": "2"})
    assert out["status"] == "succeeded", out
    assert out["outputs"] == {"greeting": "hi Acme x2"}  # count was coerced to int, then back into the text
    assert events(host, "run_finished")[0]["outputs"] == {"greeting": "hi Acme x2"}
    assert events(host, "result_ready")[-1]["result"]["title"] == "Output"  # shown like show()


def test_inp_falls_back_to_asking_like_a_manual_run(screen, agent_factory):
    agent, host = agent_factory(answers=["Globex", "5"])
    out = agent.run_task("greet", GREET)
    assert out["status"] == "succeeded"
    assert out["outputs"] == {"greeting": "hi Globex x5"}


def test_missing_input_with_no_ask_fails_without_healing(screen, agent_factory):
    agent, host = agent_factory()
    out = agent.run_task("greet", GREET, inputs={"customer": "Acme"}, no_ask=True)
    assert out["status"] == "failed" and out["error"]["code"] == "input_missing"
    assert "count" in out["error"]["message"]
    assert not events(host, "line_rewritten")  # the fixer was never asked


def test_output_rejects_values_that_are_not_json(screen, agent_factory):
    agent, host = agent_factory(answers=["stop"])
    agent.run_task("bad", 'INPUTS = {}\nOUTPUTS = {"x": "str: x"}\nopen_app("A")\noutput(x=open_app)')
    failed = events(host, "line_failed")
    assert failed and "not JSON-serializable" in failed[0]["error"]["message"]


# ---------------------------------------------------------------- header kept through repairs
def test_healing_keeps_the_header(screen, agent_factory):
    from engine.models.fake import DEMO_SCRIPT

    agent, _ = agent_factory(fail_on="Save button")
    out = agent.run_task("invoices", DEMO_SCRIPT)
    assert out["status"] == "succeeded" and "alternative" in out["final_script"]  # it was really repaired
    assert same_schema(DEMO_SCRIPT, out["final_script"])


def test_a_rewrite_that_drops_the_header_gets_it_restored(screen, agent_factory):
    agent, _ = agent_factory(fail_on="Save button")
    base = agent.models.planner

    class Careless:
        def __getattr__(self, n):
            return getattr(base, n)

        def fix_script(self, **kw):
            fix = base.fix_script(**kw)
            fix["full_script"] = "\n".join(l for l in fix["full_script"].splitlines() if not l.startswith(("INPUTS", "OUTPUTS")))
            return fix

    agent.models.planner = Careless()
    from engine.models.fake import DEMO_SCRIPT

    out = agent.run_task("invoices", DEMO_SCRIPT)
    assert out["status"] == "succeeded"
    assert same_schema(DEMO_SCRIPT, out["final_script"])


# ---------------------------------------------------------------- CLI contract
def _cli(args, data_dir, stdin=""):
    env = {**os.environ, "AGENT_FAKE_MODELS": "1", "AGENT_FAKE_SCREEN": "1", "AGENT_SHOW_DELAY": "0",
           "AGENT_DATA_DIR": str(data_dir), "AGENT_BROWSER": "0"}
    return subprocess.run([sys.executable, "-m", "engine.cli", *args], cwd=ROOT, env=env, input=stdin,
                          capture_output=True, text=True, timeout=120)


@pytest.fixture
def saved(tmp_path):
    from engine.store.db import DB

    db = DB(tmp_path / "agent.db")
    db.save_task("greet", GREET, "Greet a customer")
    db.save_task("broken", 'INPUTS = ["oops"]\nOUTPUTS = {}\nopen_app("A")')
    return tmp_path


def test_cli_tasks_json_lists_headers(saved):
    r = _cli(["tasks", "--json"], saved)
    assert r.returncode == 0
    rows = {t["name"]: t for t in json.loads(r.stdout)}
    assert rows["greet"]["inputs"] == {"customer": "str: customer name", "count": "int: how many times"}
    assert rows["greet"]["outputs"] == {"greeting": "str: the greeting that was made"}
    assert rows["greet"]["description"] == "Greet a customer" and rows["greet"]["updated"].endswith("+00:00")
    assert rows["broken"]["inputs"] == {}  # a malformed header lists as empty, the script is never run


def test_cli_run_json_prints_only_the_result_and_exits_0(saved):
    r = _cli(["run", "--saved", "greet", "--input", "customer=Acme", "--inputs-json", '{"count": 3}', "--json", "--yes"], saved)
    assert r.returncode == 0, r.stderr
    lines = [l for l in r.stdout.splitlines() if l.strip()]
    assert len(lines) == 1  # stdout carries exactly one JSON object
    result = json.loads(lines[0])
    assert result == {"status": "ok", "outputs": {"greeting": "hi Acme x3"}, "error": None, "run_id": result["run_id"]}
    assert isinstance(result["run_id"], int)
    assert "script" in r.stderr or "·" in r.stderr  # progress went to stderr


def test_cli_no_ask_fails_right_away_on_a_missing_input(saved):
    r = _cli(["run", "--saved", "greet", "--input", "customer=Acme", "--json", "--no-ask"], saved)
    assert r.returncode == 1
    result = json.loads(r.stdout)
    assert result["status"] == "failed" and result["run_id"] is None and "count" in result["error"]


def test_cli_asks_for_missing_inputs_without_no_ask(saved):
    r = _cli(["run", "--saved", "greet", "--input", "customer=Acme", "--json"], saved, stdin="7\n")
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["outputs"] == {"greeting": "hi Acme x7"}
    assert "how many times" in r.stderr.lower()  # the prompt used the input's description


def test_cli_rejects_unknown_inputs_and_unknown_tasks(saved):
    r = _cli(["run", "--saved", "greet", "--input", "colour=red", "--json"], saved)
    assert r.returncode == 1 and "unknown input" in json.loads(r.stdout)["error"]
    r = _cli(["run", "--saved", "nope", "--json"], saved)
    assert r.returncode == 1 and "no saved task" in json.loads(r.stdout)["error"]


def test_cli_older_forms_still_work(saved, tmp_path):
    script = tmp_path / "s.py"
    script.write_text(GREET)
    r = _cli(["--script", str(script), "--yes"], saved, stdin="Initech\n2\n")
    assert r.returncode == 0, r.stderr
    assert "hi Initech x2" in r.stdout
    r = _cli(["--saved", "greet", "--yes"], saved, stdin="Umbrella\n1\n")
    assert r.returncode == 0 and "hi Umbrella x1" in r.stdout


def test_a_default_written_into_the_script_fills_the_input():
    from engine.agent import literal_defaults

    script = 'INPUTS = {"message": "str: text"}\nOUTPUTS = {}\nmessage = inp("message") or "hi there"\nn = inp("n")'
    assert literal_defaults(script) == {"message": "hi there"}


def test_output_isnt_shown_again_when_the_script_showed_its_result(screen, agent_factory):
    agent, host = agent_factory()
    out = agent.run_task("greet", 'INPUTS = {}\nOUTPUTS = {"x": "str: x"}\nopen_app("A")\nshow("Done: 1")\noutput(x="1")')
    assert out["status"] == "succeeded" and out["outputs"] == {"x": "1"}
    assert len(events(host, "result_ready")) == 1  # just the show(), not a second "Output" card


def test_export_writes_a_runnable_script(screen, agent_factory):
    from engine.runner.schema import parse_header
    from engine.runner.validate import validate
    from engine.sdk import SDK_NAMES

    agent, host = agent_factory()
    tid = agent.db.save_task("greet someone", GREET, "Greet a customer")
    path = agent.export_task(tid)
    text = open(path).read()
    assert text.startswith("# Deskwright task: greet someone") and "deskwright.run_script(" in text
    assert parse_header(text)["inputs"] == parse_header(GREET)["inputs"] and validate(text, SDK_NAMES) == []
    assert agent.run_task("greet", text, inputs={"customer": "Acme", "count": 1})["outputs"] == {"greeting": "hi Acme x1"}
