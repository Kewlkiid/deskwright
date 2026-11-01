"""The CLI contract other programs rely on: one JSON result on stdout, a screen lock across processes, a DB
that waits instead of failing, and the --events protocol for questions and confirmations."""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

ECHO = '''INPUTS = {"query": "str: text", "times": "int: count"}
OUTPUTS = {"echo": "str: upper-cased", "count": "int: times"}
q = inp("query")
output(echo=q.upper(), count=inp("times"))
'''
ASKS = '''INPUTS = {}
OUTPUTS = {"a": "str: answer"}
output(a=ask_user("Which account?"))
'''
SLOW = '''INPUTS = {}
OUTPUTS = {"x": "int: x"}
wait(6)
output(x=1)
'''


@pytest.fixture
def data_dir():
    d = Path(tempfile.mkdtemp(prefix="agent-cli-"))
    env = {**os.environ, "AGENT_DATA_DIR": str(d)}
    code = (
        "from engine.config import config\nfrom engine.store.db import DB\ndb = DB(config.db_path)\n"
        f"db.save_task('echo', {ECHO!r}, description='echo')\n"
        f"db.save_task('asks', {ASKS!r}, description='asks')\n"
        f"db.save_task('slow', {SLOW!r}, description='slow')\n"
    )
    subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, check=True)
    return d


def cli(data_dir: Path, *args: str, stdin: str | None = None, timeout: float = 120) -> tuple[int, str, str]:
    env = {**os.environ, "AGENT_DATA_DIR": str(data_dir), "AGENT_FAKE_MODELS": "1", "AGENT_FAKE_SCREEN": "1",
           "AGENT_BROWSER": "0"}
    p = subprocess.run([sys.executable, "-m", "engine.cli", *args], cwd=ROOT, env=env, input=stdin or "",
                       capture_output=True, text=True, timeout=timeout)
    return p.returncode, p.stdout, p.stderr


def one_json(stdout: str) -> dict:
    lines = [ln for ln in stdout.splitlines() if ln.strip()]
    assert len(lines) == 1, stdout
    return json.loads(lines[0])


def test_tasks_json_lists_schemas(data_dir):
    code, out, _ = cli(data_dir, "tasks", "--json")
    rows = {r["name"]: r for r in json.loads(out)}
    assert code == 0 and rows["echo"]["inputs"] == {"query": "str: text", "times": "int: count"}
    assert set(rows["echo"]) >= {"name", "description", "inputs", "outputs", "updated"}


def test_run_ok_prints_exactly_one_json_object(data_dir):
    code, out, _ = cli(data_dir, "run", "--saved", "echo", "--input", "query=hi", "--input", "times=2", "--json", "--no-ask")
    r = one_json(out)
    assert code == 0 and r == {"status": "ok", "outputs": {"echo": "HI", "count": 2}, "error": None, "run_id": r["run_id"]}


def test_a_question_under_no_ask_fails_instead_of_answering_empty(data_dir):
    code, out, _ = cli(data_dir, "run", "--saved", "asks", "--json", "--no-ask")
    r = one_json(out)
    assert code == 1 and r["status"] == "failed" and "Which account?" in r["error"]


def test_events_mode_answers_questions_over_stdin(data_dir):
    env = {**os.environ, "AGENT_DATA_DIR": str(data_dir), "AGENT_FAKE_MODELS": "1", "AGENT_FAKE_SCREEN": "1", "AGENT_BROWSER": "0"}
    p = subprocess.Popen([sys.executable, "-m", "engine.cli", "run", "--saved", "asks", "--json", "--no-ask", "--events"],
                         cwd=ROOT, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    types = []
    for line in p.stderr:
        ev = json.loads(line)  # every stderr line is JSON in this mode
        types.append(ev["type"])
        if ev["type"] == "ask_request":
            p.stdin.write(json.dumps({"id": ev["id"], "answer": "acct 2"}) + "\n")
            p.stdin.flush()
    r = one_json(p.stdout.read())
    p.wait()
    assert "run_started" in types and "run_finished" in types
    assert r["status"] == "ok" and r["outputs"] == {"a": "acct 2"}


def test_second_run_is_busy_while_the_screen_is_taken(data_dir):
    first = {}
    t = threading.Thread(target=lambda: first.update(r=cli(data_dir, "run", "--saved", "slow", "--json", "--no-ask")))
    t.start()
    time.sleep(2.5)
    code, out, _ = cli(data_dir, "run", "--saved", "echo", "--input", "query=a", "--input", "times=1", "--json", "--no-ask")
    t.join()
    r = one_json(out)
    assert code == 1 and r["status"] == "busy" and "slow" in r["error"]
    assert one_json(first["r"][1])["status"] == "ok"


def test_a_locked_db_is_waited_for(data_dir):
    def hold():
        c = sqlite3.connect(data_dir / "agent.db", isolation_level=None)
        c.execute("BEGIN EXCLUSIVE")
        time.sleep(3)
        c.execute("COMMIT")

    t = threading.Thread(target=hold)
    t.start()
    time.sleep(0.5)
    code, out, _ = cli(data_dir, "tasks", "--json")
    t.join()
    assert code == 0 and isinstance(json.loads(out), list)


def test_stats_show_rename_delete_history(data_dir):
    cli(data_dir, "run", "--saved", "echo", "--input", "query=a", "--input", "times=1", "--json", "--no-ask")
    rows = {r["name"]: r for r in json.loads(cli(data_dir, "tasks", "--json", "--stats")[1])}
    assert rows["echo"]["runs"] == 1 and rows["echo"]["success_rate"] == 1.0 and rows["echo"]["last_run"]["status"] == "succeeded"
    shown = json.loads(cli(data_dir, "task", "show", "echo", "--json")[1])
    assert shown["script"].startswith("INPUTS") and shown["versions"][0]["note"] == "created"
    assert json.loads(cli(data_dir, "task", "rename", "echo", "asks", "--json")[1])["ok"] is False  # name taken
    assert json.loads(cli(data_dir, "task", "rename", "echo", "shout", "--json")[1])["ok"] is True
    assert json.loads(cli(data_dir, "task", "delete", "shout", "--json")[1])["ok"] is False  # needs --yes
    assert json.loads(cli(data_dir, "task", "delete", "shout", "--yes", "--json")[1])["ok"] is True
    names = [r["name"] for r in json.loads(cli(data_dir, "tasks", "--json")[1])]
    assert "shout" not in names and "echo" not in names
    hist = json.loads(cli(data_dir, "history", "--json", "--limit", "5")[1])
    assert hist and hist[0]["status"] == "succeeded"
