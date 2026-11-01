"""Use Deskwright from other programs.

    import deskwright

    deskwright.tasks()                                        # saved tasks with their inputs and outputs
    out = deskwright.run("message someone on discord", {"recipient": "sam", "message": "hi"})
    out = deskwright.run_script("exports/send_invoice.py", {"customer": "Acme", "amount": 120})
    print(out)                                                # the task's OUTPUTS, e.g. {"posted": True}

Each call drives the screen like the app does (one run at a time) and returns the task's outputs as a dict, or raises
TaskFailed. Sensitive actions (send, post, delete...) are declined unless approve=True; inputs that aren't given make
the run fail instead of asking. Other languages: run the same command and read the one JSON line it prints:

    engine/.venv/bin/python -m engine.cli run --saved "<task name>" --inputs-json '{"k": "v"}' --json --no-ask
"""
from __future__ import annotations

import json
import subprocess
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


if __name__ == "__main__":
    for t in tasks():
        print(f"{t['name']}: inputs {list(t['inputs'])} -> outputs {list(t['outputs'])}")
