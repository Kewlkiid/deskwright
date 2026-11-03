"""Use Deskwright from other programs.

    import deskwright

    out = deskwright.do("what's the temperature in new york? use the weather app")   # any request, in words
    deskwright.tasks()                                        # saved tasks with their inputs and outputs
    out = deskwright.run("message someone on discord", {"recipient": "sam", "message": "hi"})
    out = deskwright.run_script("exports/send_invoice.py", {"customer": "Acme", "amount": 120})
    print(out)                                                # the task's OUTPUTS, e.g. {"posted": True}

A file can also be a Deskwright script itself, the same code the app shows: start it with `from deskwright import *`
and run it with plain Python. The whole file then runs in Deskwright (self-healing, approvals), with inputs given as
key=value arguments and --yes to approve sends and posts:

    python3 city_temps.py cities="Paris, Sydney"

Each call drives the screen like the app does (one run at a time) and returns the task's outputs as a dict, or raises
TaskFailed. Sensitive actions (send, post, delete...) are declined unless approve=True; inputs that aren't given make
the run fail instead of asking. Other languages: run the same command and read the one JSON line it prints:

    engine/.venv/bin/python -m engine.cli run --saved "<task name>" --inputs-json '{"k": "v"}' --json --no-ask
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PYTHON = ROOT / "engine" / ".venv" / "bin" / "python"


class TaskFailed(Exception):
    def __init__(self, message: str, result: dict):
        super().__init__(message)
        self.result = result  # {"status", "outputs", "error", "run_id"}


def _cli(args: list[str], timeout: float | None) -> str:
    """The command's stdout (its JSON result)."""
    p = subprocess.run([str(PYTHON), "-m", "engine.cli", *args], cwd=ROOT, capture_output=True, text=True,
                       timeout=timeout)
    if not p.stdout.strip():
        raise TaskFailed(p.stderr.strip()[-500:] or "no result", {"status": "failed", "error": p.stderr[-500:]})
    return p.stdout


def _run(target: list[str], inputs: dict | None, approve: bool, timeout: float | None) -> dict:
    args = ["run", *target, "--inputs-json", json.dumps(inputs or {}), "--json", "--no-ask"]
    if approve:
        args.append("--yes")
    result = json.loads(_cli(args, timeout).strip().splitlines()[-1])  # run --json prints exactly one line
    if result.get("status") != "ok":
        raise TaskFailed(str(result.get("error") or result.get("status")), result)
    return result.get("outputs") or {}


def do(request: str, inputs: dict | None = None, *, approve: bool = False, timeout: float | None = None) -> dict:
    """Do anything described in words: the planner writes the program and runs it; returns what it found."""
    return _run([request], inputs, approve, timeout)


def run(task: str, inputs: dict | None = None, *, approve: bool = False, timeout: float | None = None) -> dict:
    """Run a saved task by name; returns its outputs."""
    return _run(["--saved", task], inputs, approve, timeout)


def run_script(path: str | Path, inputs: dict | None = None, *, approve: bool = False,
               timeout: float | None = None) -> dict:
    """Run an exported task file (or any Deskwright script); returns its outputs."""
    return _run(["--script", str(Path(path).resolve())], inputs, approve, timeout)


def tasks() -> list[dict]:
    """Saved tasks: [{"name", "description", "inputs", "outputs", "updated"}]."""
    return json.loads(_cli(["tasks", "--json"], 60))


# The script calls, so editors know the names in a `from deskwright import *` file. Run the file with Python and the
# whole file runs inside Deskwright, where they work; called any other way they only explain that.
def _inside_deskwright(*args, **kwargs):
    raise RuntimeError("Deskwright script calls run inside Deskwright: run the whole file with python")


active_window = _inside_deskwright
ask = _inside_deskwright
ask_user = _inside_deskwright
check = _inside_deskwright
checkpoint = _inside_deskwright
clear_focused_input = _inside_deskwright
click = _inside_deskwright
confirm_with_user = _inside_deskwright
double_click = _inside_deskwright
drag = _inside_deskwright
expect = _inside_deskwright
export = _inside_deskwright
focus_window = _inside_deskwright
hotkey = _inside_deskwright
inp = _inside_deskwright
is_loaded = _inside_deskwright
make_table = _inside_deskwright
menu = _inside_deskwright
move_mouse = _inside_deskwright
network_response = _inside_deskwright
open_app = _inside_deskwright
open_url = _inside_deskwright
output = _inside_deskwright
page_js = _inside_deskwright
press = _inside_deskwright
read_table = _inside_deskwright
read_text = _inside_deskwright
right_click = _inside_deskwright
scroll = _inside_deskwright
scroll_until = _inside_deskwright
show = _inside_deskwright
summarize = _inside_deskwright
type_into = _inside_deskwright
type_text = _inside_deskwright
use_grounding = _inside_deskwright
wait = _inside_deskwright
wait_for = _inside_deskwright
progress = None  # a script's resume helper, set inside Deskwright


def _run_importing_file() -> None:
    """`from deskwright import *` at the top of the file being run: hand that whole file to Deskwright instead of
    letting Python run it line by line (its calls only work inside Deskwright), print the outputs and exit."""
    main = sys.modules.get("__main__")
    path = getattr(main, "__file__", None)
    if not path or os.environ.get("DESKWRIGHT_NO_HANDOFF") or Path(path).resolve() == Path(__file__).resolve():
        return
    try:
        source = Path(path).read_text(encoding="utf-8")
    except OSError:
        return
    if not re.search(r"(?m)^[ \t]*from deskwright import \*[ \t]*$", source):
        return
    args = sys.argv[1:]
    inputs = dict(a.split("=", 1) for a in args if "=" in a and not a.startswith("-"))
    try:
        outputs = run_script(path, inputs, approve="--yes" in args)
    except TaskFailed as e:
        print(f"Failed: {e}", file=sys.stderr)
        sys.exit(1)
    for key, value in outputs.items():
        print(f"{key}: {value}")
    sys.exit(0)


_run_importing_file()

if __name__ == "__main__":
    for t in tasks():
        print(f"{t['name']}: inputs {list(t['inputs'])} -> outputs {list(t['outputs'])}")
