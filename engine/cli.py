"""Run tasks from the terminal or from other programs, without the UI.

Public, backward-compatible interface:

    python -m engine.cli tasks --json
        -> [{"name", "description", "inputs", "outputs", "updated"}, ...]   (headers parsed with ast, never executed)

    python -m engine.cli run --saved NAME [--input key=value ...] [--inputs-json '{...}'] [--json] [--yes] [--no-ask]
        With --json, progress goes to stderr and stdout carries exactly one JSON object:
        {"status": "ok" | "failed" | "stopped", "outputs": {...}, "error": str | null, "run_id": int | null}
        Exit code 0 only when status is "ok". Inputs not passed are asked for on the terminal, unless --no-ask:
        then a missing input fails right away.

Older forms keep working:

    python -m engine.cli "open TextEdit and type hello world"
    python -m engine.cli --script my_script.py
    python -m engine.cli --saved "create invoices" --yes
    AGENT_FAKE_MODELS=1 python -m engine.cli "demo"     # offline, dry-run mouse
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from datetime import datetime, timezone


class TerminalHost:
    COLORS = {"line_failed": "\033[31m", "line_rewritten": "\033[33m", "cache_hit": "\033[36m",
              "result_ready": "\033[32m", "run_finished": "\033[1m"}

    def __init__(self, yes: bool = False, verbose: bool = False, stream=None):
        self.yes = yes
        self.verbose = verbose
        self.stream = stream  # where progress goes (stderr in --json mode); None = stdout

    def _print(self, *args):
        print(*args, file=self.stream or sys.stdout, flush=True)

    def _ask(self, prompt: str) -> str:
        if self.stream is None:
            return input(prompt)
        self._print(prompt.rstrip("\n"))
        return sys.stdin.readline().rstrip("\n")

    def emit(self, type, **data):
        c = self.COLORS.get(type, "")
        reset = "\033[0m" if c else ""
        if type == "script_generated":
            self._print(f"\n--- script ---\n{data['script']}\n--------------")
        elif type == "line_rewritten":
            self._print(f"{c}↻ rewrote from line {data['failed_line']}: {data['explanation']}\n{data['script']}{reset}")
        elif type == "line_failed":
            self._print(f"{c}✗ line {data['line']} [{data['error']['code']}] {data['error']['message']}{reset}")
        elif type == "status":
            self._print(f"  · {data['text']}")
        elif type == "cache_hit":
            self._print(f"{c}  ⚡ cache hit: {data['target']}{reset}")
        elif type == "result_ready":
            r = data["result"]
            self._print(f"{c}=== result ===\n{r.get('text') or json.dumps(r.get('rows'), indent=1)}{reset}")
        elif type == "run_finished":
            m = data["metrics"]
            self._print(f"{c}\nRun {data['status']}: {m['steps']} steps, {m['elapsed']}s, {m['model_calls']} model calls, "
                  f"${m['cost']:.4f}, cache hit rate {m['cache_hit_rate']:.0%}, fixes {m['fixes']}{reset}")
            if data.get("error"):
                self._print(f"  error: {data['error'].get('message')}")
        elif self.verbose and type not in ("element_found",):
            self._print(f"  [{type}] {json.dumps(data, default=str)[:200]}")

    def ask_user(self, question, stop):
        return self._ask(f"\n? {question}\n> ")

    def confirm(self, summary, stop):
        if self.yes:
            self._print(f"  (auto-confirmed) {summary}")
            return True
        return self._ask(f"\n! Confirm: {summary} [y/N] ").strip().lower() in ("y", "yes")

    def before_capture(self):
        pass

    def after_capture(self):
        pass


STATUS = {"succeeded": "ok", "stopped": "stopped", "declined": "stopped", "busy": "busy"}


def _task_row(t: dict) -> dict:
    from .runner.schema import schema_of

    inputs, outputs = schema_of(t["script"])
    updated = datetime.fromtimestamp(t["updated"] or 0, tz=timezone.utc).isoformat(timespec="seconds")
    return {"name": t["name"], "description": t.get("description") or "", "inputs": inputs, "outputs": outputs,
            "updated": updated}


def cmd_tasks(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="engine.cli tasks", description="List saved tasks with their inputs and outputs.")
    p.add_argument("--json", action="store_true", help="print the list as JSON")
    args = p.parse_args(argv)
    from .config import config
    from .store.db import DB

    try:
        rows = [_task_row(t) for t in DB(config.db_path).query("SELECT * FROM tasks ORDER BY updated DESC")]
    except Exception as e:  # noqa: BLE001  (callers parse stdout: give them an error object, never a traceback)
        if args.json:
            print(json.dumps({"error": f"{type(e).__name__}: {e}"}))
        else:
            print(f"error: {e}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(rows, ensure_ascii=False))
    else:
        for r in rows:
            print(f"{r['name']}  inputs: {', '.join(r['inputs']) or '-'}  outputs: {', '.join(r['outputs']) or '-'}")
    return 0


def _parse_inputs(pairs: list[str], inputs_json: str | None) -> dict:
    values: dict = {}
    if inputs_json:
        data = json.loads(inputs_json)
        if not isinstance(data, dict):
            raise ValueError("--inputs-json must be a JSON object")
        values.update(data)
    for pair in pairs or []:
        if "=" not in pair:
            raise ValueError(f"--input expects key=value, got {pair!r}")
        k, v = pair.split("=", 1)
        values[k.strip()] = v
    return values


def cmd_run(argv: list[str], prog: str = "engine.cli run") -> int:
    p = argparse.ArgumentParser(prog=prog, description="Run a task: a saved one, a script file, or a request.")
    p.add_argument("task", nargs="?", default="", help="what to do (the planner writes the script)")
    p.add_argument("--script", help="run this script file instead of asking the planner")
    p.add_argument("--saved", help="run a saved task by name")
    p.add_argument("--input", action="append", default=[], metavar="KEY=VALUE", help="a task input (repeatable)")
    p.add_argument("--inputs-json", help="task inputs as a JSON object")
    p.add_argument("--json", action="store_true", help="progress to stderr, one JSON result on stdout")
    p.add_argument("--yes", action="store_true", help="auto-confirm sensitive actions")
    p.add_argument("--no-ask", action="store_true", help="fail on a missing input instead of asking")
    p.add_argument("--wait-lock", type=float, default=0.0, metavar="SECONDS",
                   help="wait this long for another run to free the screen (default 0: answer \"busy\" at once)")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    real_stdout = sys.stdout
    if args.json:
        sys.stdout = sys.stderr  # stdout carries only the final JSON object

    def finish(status: str, outputs: dict | None = None, error: str | None = None, run_id=None) -> int:
        if args.json:
            real_stdout.write(json.dumps({"status": status, "outputs": outputs or {}, "error": error,
                                          "run_id": run_id}, ensure_ascii=False, default=str) + "\n")
            real_stdout.flush()
        elif error:
            print(f"error: {error}", file=sys.stderr)
        return 0 if status == "ok" else 1

    try:
        inputs = _parse_inputs(args.input, args.inputs_json)
    except ValueError as e:
        return finish("failed", error=str(e))
    if not (args.saved or args.script or args.task):
        p.print_help(sys.stderr)
        return finish("failed", error="nothing to run: pass --saved NAME, --script FILE or a task")

    # Anything that goes wrong from here on (a locked or broken DB, a crash) still ends in the one JSON result.
    def go() -> int:
        from .agent import Agent
        from .runner.schema import schema_of

        host = TerminalHost(args.yes, args.verbose, stream=sys.stderr if args.json else None)
        agent = Agent(host)
        agent.lock_wait = args.wait_lock
        task_text, script, task_id = args.task, None, None
        if args.saved:
            t = agent.db.get_task(name=args.saved)
            if not t:
                return finish("failed", error=f"no saved task named {args.saved!r}")
            task_text, script, task_id = t["description"] or t["name"], t["script"], t["id"]
        elif args.script:
            with open(args.script, encoding="utf-8") as fh:
                script = fh.read()
            task_text = args.task or args.script
        if script is not None:
            declared, _ = schema_of(script)
            unknown = [k for k in inputs if k not in declared]
            if unknown:
                return finish("failed", error=f"unknown input(s) {', '.join(unknown)}; the task takes: "
                                             f"{', '.join(declared) or 'no inputs'}")
            missing = [k for k in declared if k not in inputs]
            if args.no_ask and missing:
                return finish("failed", error=f"missing input(s) {', '.join(missing)} (--no-ask): "
                                             + "; ".join(f"{k}: {declared[k]}" for k in missing))

        from .browser.bridge import start_bridge

        bridge = start_bridge()  # lets SDK scripts drive Chrome through the extension
        wait = float(os.environ.get("AGENT_BROWSER_WAIT", "0") or 0)  # seconds to wait for the extension to connect
        if bridge is not None and wait > 0:
            import time

            end = time.time() + wait
            while not bridge.connected and time.time() < end:
                time.sleep(0.2)
        try:
            import signal

            signal.signal(signal.SIGINT, lambda *_: agent.stop())
        except Exception:
            pass
        try:
            out = agent.run_task(task_text, script, task_id, inputs=inputs, no_ask=args.no_ask)
        except Exception as e:  # noqa: BLE001
            return finish("failed", error=f"{type(e).__name__}: {e}")
        err = out.get("error")
        message = (err.get("message") if isinstance(err, dict) else err) or None
        return finish(STATUS.get(out.get("status"), "failed"), out.get("outputs"), message, out.get("run_id"))


    try:
        return go()
    except Exception as e:  # noqa: BLE001
        return finish("failed", error=f"{type(e).__name__}: {e}")

def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["tasks"]:
        return cmd_tasks(argv[1:])
    if argv[:1] == ["run"]:
        return cmd_run(argv[1:])
    return cmd_run(argv, prog="engine.cli")  # older forms: "task text", --script FILE, --saved NAME


if __name__ == "__main__":
    threading.current_thread().name = "agent-cli"
    sys.exit(main())
