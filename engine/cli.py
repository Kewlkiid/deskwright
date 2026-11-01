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
import queue
import sys
import threading
import time
import uuid
from datetime import datetime, timezone

# Events left out of --events: UI plumbing, or too large and internal to be useful to another program.
QUIET_EVENTS = {"pointer", "vision_scan", "vision_miss", "scope", "request_show", "request_hide", "suppress_esc",
                "cache", "pong", "metrics", "browser", "element_found"}
BULKY_FIELDS = {"script", "final_script", "history", "totals", "image", "screenshot", "trace"}


class TerminalHost:
    COLORS = {"line_failed": "\033[31m", "line_rewritten": "\033[33m", "cache_hit": "\033[36m",
              "result_ready": "\033[32m", "run_finished": "\033[1m"}

    def __init__(self, yes: bool = False, verbose: bool = False, stream=None, no_ask: bool = False,
                 events: bool = False):
        self.yes = yes
        self.verbose = verbose
        self.stream = stream  # where progress goes (stderr in --json mode); None = stdout
        self.no_ask = no_ask
        # --events: every event is one JSON line on stderr, and questions/confirmations are answered with JSON
        # lines on stdin ({"id": ..., "answer": ...}), so another program can show them to its user.
        self.events = events
        self._answers: queue.Queue = queue.Queue()
        if events:
            threading.Thread(target=self._read_answers, name="cli-answers", daemon=True).start()

    def _print(self, *args):
        if self.events:
            return  # only JSON events on stderr in this mode
        print(*args, file=self.stream or sys.stdout, flush=True)

    def _event(self, type: str, **data):
        line = json.dumps({"type": type, "t": round(time.time(), 3), **data}, ensure_ascii=False, default=str)
        sys.stderr.write(line + "\n")
        sys.stderr.flush()

    def _read_answers(self):
        for line in sys.stdin:
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if isinstance(msg, dict) and "id" in msg:
                self._answers.put((str(msg["id"]), msg.get("answer")))
        self._answers.put((None, None))  # stdin closed: nobody will answer

    def _await(self, kind: str, stop, **data):
        """Send a request event and wait for its answer. Returns (answered, answer)."""
        rid = uuid.uuid4().hex[:12]
        self._event(kind, id=rid, **data)
        while True:
            if stop is not None and stop.is_set():
                return False, None
            try:
                got, answer = self._answers.get(timeout=0.25)
            except queue.Empty:
                continue
            if got is None:
                self._answers.put((None, None))  # keep "closed" visible to later requests
                return False, None
            if got == rid:
                return True, answer

    def _ask(self, prompt: str) -> str:
        if self.stream is None:
            return input(prompt)
        self._print(prompt.rstrip("\n"))
        return sys.stdin.readline().rstrip("\n")

    def emit(self, type, **data):
        if self.events:
            if type not in QUIET_EVENTS:
                self._event(type, **{k: v for k, v in data.items() if k not in BULKY_FIELDS})
            return
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
        from .sdk.errors import InputMissingError

        if self.events:
            answered, answer = self._await("ask_request", stop, question=question)
            if not answered:
                raise InputMissingError(f"Nobody answered: {question}")
            return "" if answer is None else str(answer)
        if self.no_ask:
            # Never carry on with an empty answer the user didn't give.
            raise InputMissingError(f"The task asked a question and --no-ask is set: {question}")
        return self._ask(f"\n? {question}\n> ")

    def confirm(self, summary, stop):
        if self.yes:
            if self.events:
                self._event("confirm_auto", summary=summary)
            self._print(f"  (auto-confirmed) {summary}")
            return True
        if self.events:
            answered, answer = self._await("confirm_request", stop, summary=summary)
            return bool(answered and answer is True)
        if self.no_ask:
            self._print(f"  (declined: --no-ask) {summary}")
            return False
        return self._ask(f"\n! Confirm: {summary} [y/N] ").strip().lower() in ("y", "yes")

    def before_capture(self):
        pass

    def after_capture(self):
        pass


STATUS = {"succeeded": "ok", "stopped": "stopped", "declined": "stopped", "busy": "busy"}


def _iso(ts) -> str | None:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="seconds") if ts else None


def _task_row(t: dict, db=None) -> dict:
    from .runner.schema import schema_of

    inputs, outputs = schema_of(t["script"])
    row = {"name": t["name"], "description": t.get("description") or "", "inputs": inputs, "outputs": outputs,
           "updated": _iso(t["updated"] or 0) or _iso(0.0001)}
    if db is not None:  # --stats
        st = db.task_stats(t["id"])
        last = st["last_run"]
        row.update({
            "id": t["id"], "source": t.get("source") or "", "request_id": t.get("request_id"),
            "runs": st["runs"], "success_rate": st["success_rate"],
            "last_run": {"status": last["status"], "started": _iso(last["started"]), "ended": _iso(last["ended"])} if last else None,
            "last_healed": _iso(st["last_healed"]), "versions": st["versions"],
        })
    return row


def _json_or_text(as_json: bool, obj: dict, text: str = "") -> int:
    if as_json:
        print(json.dumps(obj, ensure_ascii=False, default=str))
    else:
        print(obj.get("error") or text, file=sys.stderr if obj.get("error") else sys.stdout)
    return 0 if not obj.get("error") else 1


def cmd_task(argv: list[str]) -> int:
    """task show NAME | task rename OLD NEW | task delete NAME --yes   (all take --json)"""
    p = argparse.ArgumentParser(prog="engine.cli task", description="Show, rename or delete a saved task.")
    p.add_argument("action", choices=["show", "rename", "delete"])
    p.add_argument("name")
    p.add_argument("new_name", nargs="?")
    p.add_argument("--json", action="store_true")
    p.add_argument("--yes", action="store_true", help="required to delete")
    args = p.parse_args(argv)
    try:
        from .config import config
        from .runner.schema import schema_of
        from .store.db import DB

        db = DB(config.db_path)
        t = db.get_task(name=args.name)
        if not t:
            return _json_or_text(args.json, {"ok": False, "error": f"no saved task named {args.name!r}"})
        if args.action == "show":
            inputs, outputs = schema_of(t["script"])
            versions = [{"id": v["id"], "note": v["note"], "created": _iso(v["created"])}
                        for v in db.query("SELECT id, note, created FROM task_versions WHERE task_id = ? ORDER BY id", (t["id"],))]
            return _json_or_text(args.json, {"name": t["name"], "description": t.get("description") or "", "inputs": inputs,
                                             "outputs": outputs, "script": t["script"], "versions": versions}, t["script"])
        if args.action == "rename":
            new = (args.new_name or "").strip()
            if not new:
                return _json_or_text(args.json, {"ok": False, "error": "rename needs a new name"})
            other = db.get_task(name=new)
            if other and other["id"] != t["id"]:
                return _json_or_text(args.json, {"ok": False, "error": f"a task named {new!r} already exists"})
            db.rename_task(t["id"], new)
            return _json_or_text(args.json, {"ok": True, "error": None}, f"renamed to {new}")
        if not args.yes:
            return _json_or_text(args.json, {"ok": False, "error": "delete needs --yes"})
        db.delete_task(t["id"])
        return _json_or_text(args.json, {"ok": True, "error": None}, "deleted")
    except Exception as e:  # noqa: BLE001
        return _json_or_text(args.json, {"ok": False, "error": f"{type(e).__name__}: {e}"})


def cmd_history(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="engine.cli history", description="Latest runs, newest first.")
    p.add_argument("--task", help="only this task's runs")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    try:
        from .config import config
        from .store.db import DB

        db = DB(config.db_path)
        where, params = "", []
        if args.task:
            t = db.get_task(name=args.task)
            if not t:
                return _json_or_text(args.json, {"error": f"no saved task named {args.task!r}"})
            where, params = "WHERE r.task_id = ?", [t["id"]]
        rows = db.query(f"SELECT r.id, r.status, r.started, r.ended, r.metrics, t.name FROM runs r LEFT JOIN tasks t "
                        f"ON t.id = r.task_id {where} ORDER BY r.id DESC LIMIT ?", [*params, args.limit])
        out = [{"run_id": r["id"], "task": r["name"], "status": r["status"], "started": _iso(r["started"]),
                "ended": _iso(r["ended"]), "metrics": json.loads(r["metrics"]) if r["metrics"] else {}} for r in rows]
    except Exception as e:  # noqa: BLE001
        return _json_or_text(args.json, {"error": f"{type(e).__name__}: {e}"})
    if args.json:
        print(json.dumps(out, ensure_ascii=False))
    else:
        for r in out:
            print(f"{r['run_id']}  {r['task'] or '-'}  {r['status']}  {r['started']}")
    return 0


def cmd_tasks(argv: list[str]) -> int:
    p = argparse.ArgumentParser(prog="engine.cli tasks", description="List saved tasks with their inputs and outputs.")
    p.add_argument("--json", action="store_true", help="print the list as JSON")
    p.add_argument("--stats", action="store_true",
                   help="also id, source, request_id, runs, success_rate, last_run, last_healed, versions")
    args = p.parse_args(argv)
    from .config import config
    from .store.db import DB

    try:
        db = DB(config.db_path)
        rows = [_task_row(t, db if args.stats else None) for t in db.query("SELECT * FROM tasks ORDER BY updated DESC")]
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
    p.add_argument("--no-ask", action="store_true",
                   help="never prompt on the terminal: a missing input or a question fails the run, a confirmation is declined")
    p.add_argument("--events", action="store_true",
                   help="with --json: JSON event lines on stderr; answer ask_request/confirm_request on stdin as "
                        "{\"id\": ..., \"answer\": ...}")
    p.add_argument("--wait-lock", type=float, default=0.0, metavar="SECONDS",
                   help="wait this long for another run to free the screen (default 0: answer \"busy\" at once)")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    real_stdout = sys.stdout
    if args.json:
        # stdout carries only the final JSON object. Keep a private copy of it, then point file descriptor 1 (and
        # sys.stdout) at stderr, so nothing else, not even native libraries, can write a stray line into it.
        try:
            real_stdout = os.fdopen(os.dup(1), "w", encoding="utf-8")
            os.dup2(2, 1)
        except OSError:
            pass
        sys.stdout = sys.stderr

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

        host = TerminalHost(args.yes, args.verbose, stream=sys.stderr if args.json else None, no_ask=args.no_ask,
                            events=args.json and args.events)
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

def cmd_create(argv: list[str]) -> int:
    """create --describe TEXT: write and save a task without a demonstration."""
    p = argparse.ArgumentParser(prog="engine.cli create", description="Write and save a task from a description.")
    p.add_argument("--describe", required=True, help="what the task should do")
    p.add_argument("--name", default="", help="task name (default: from the description)")
    p.add_argument("--inputs-json", help='expected INPUTS, e.g. {"query": "str: what to search"}')
    p.add_argument("--outputs-json", help="expected OUTPUTS, same form")
    p.add_argument("--test-inputs-json", help="values for a test run before saving (the run uses the screen)")
    p.add_argument("--request-id", help="the outside request this task answers (recorded on the task)")
    p.add_argument("--dry-run", action="store_true", help="test run moves the mouse but never clicks or types")
    p.add_argument("--yes", action="store_true", help="auto-confirm sensitive steps in the test run")
    p.add_argument("--json", action="store_true")
    p.add_argument("--events", action="store_true", help="with --json: JSON event lines on stderr")
    args = p.parse_args(argv)
    real_stdout = sys.stdout
    if args.json:
        try:
            real_stdout = os.fdopen(os.dup(1), "w", encoding="utf-8")
            os.dup2(2, 1)
        except OSError:
            pass
        sys.stdout = sys.stderr

    def finish(obj: dict) -> int:
        if args.json:
            real_stdout.write(json.dumps(obj, ensure_ascii=False, default=str) + "\n")
            real_stdout.flush()
        else:
            print(obj.get("error") or f"saved {obj.get('name')!r}", file=sys.stderr if obj.get("error") else sys.stdout)
        return 0 if obj.get("status") == "ok" else 1

    try:
        parse = lambda s: json.loads(s) if s else None  # noqa: E731
        inputs, outputs, test_inputs = parse(args.inputs_json), parse(args.outputs_json), parse(args.test_inputs_json)
        from .agent import Agent
        from .config import config

        if args.dry_run:
            config.dry_run = True
        host = TerminalHost(args.yes, False, stream=sys.stderr if args.json else None, no_ask=True,
                            events=args.json and args.events)
        result = Agent(host).create_from_description(args.describe, args.name, inputs, outputs, test_inputs,
                                                     args.request_id)
    except Exception as e:  # noqa: BLE001
        result = {"status": "failed", "name": args.name, "inputs": {}, "outputs": {}, "error": f"{type(e).__name__}: {e}",
                  "tested": False}
    return finish(result)


def cmd_teach(argv: list[str]) -> int:
    """teach --describe TEXT: open the app in teach mode with this request filled in."""
    p = argparse.ArgumentParser(prog="engine.cli teach", description="Ask the user to show a task once in the app.")
    p.add_argument("--describe", required=True)
    p.add_argument("--name", default="")
    p.add_argument("--request-id")
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)
    try:
        import subprocess
        from pathlib import Path

        from .config import ROOT
        from .teach.requests import put_request

        put_request(args.describe, args.name, args.request_id)
        status = "queued"  # the request waits until the app's window is open
        if sys.platform == "darwin" and not os.environ.get("AGENT_NO_OPEN"):  # AGENT_NO_OPEN: tests
            candidates = [os.environ.get("AGENT_APP", ""), "/Applications/Agent.app",
                          str(ROOT / "app" / "release" / "mac-arm64" / "Agent.app")]
            app = next((c for c in candidates if c and Path(c).exists()), None)
            if app and subprocess.run(["open", "-a", app], capture_output=True).returncode == 0:
                status = "opened"
        obj = {"status": status, "error": None if status == "opened" else "the request is saved; open the Agent app to see it"}
    except Exception as e:  # noqa: BLE001
        obj = {"status": "failed", "error": f"{type(e).__name__}: {e}"}
    return _json_or_text(args.json, obj if obj["status"] != "queued" else {**obj, "error": None}, obj["status"])


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["tasks"]:
        return cmd_tasks(argv[1:])
    if argv[:1] == ["run"]:
        return cmd_run(argv[1:])
    if argv[:1] == ["task"]:
        return cmd_task(argv[1:])
    if argv[:1] == ["history"]:
        return cmd_history(argv[1:])
    if argv[:1] == ["create"]:
        return cmd_create(argv[1:])
    if argv[:1] == ["teach"]:
        return cmd_teach(argv[1:])
    return cmd_run(argv, prog="engine.cli")  # older forms: "task text", --script FILE, --saved NAME


if __name__ == "__main__":
    threading.current_thread().name = "agent-cli"
    sys.exit(main())
