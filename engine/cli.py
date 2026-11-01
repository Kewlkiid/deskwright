"""Run a task from the terminal without the UI.

    python -m engine.cli "open TextEdit and type hello world"
    python -m engine.cli --script my_script.py
    AGENT_FAKE_MODELS=1 python -m engine.cli "demo"     # offline, dry-run mouse
"""
from __future__ import annotations

import argparse
import json
import sys
import threading


class TerminalHost:
    COLORS = {"line_failed": "\033[31m", "line_rewritten": "\033[33m", "cache_hit": "\033[36m",
              "result_ready": "\033[32m", "run_finished": "\033[1m"}

    def __init__(self, yes: bool = False, verbose: bool = False):
        self.yes = yes
        self.verbose = verbose

    def emit(self, type, **data):
        c = self.COLORS.get(type, "")
        reset = "\033[0m" if c else ""
        if type == "script_generated":
            print(f"\n--- script ---\n{data['script']}\n--------------")
        elif type == "line_rewritten":
            print(f"{c}↻ rewrote from line {data['failed_line']}: {data['explanation']}\n{data['script']}{reset}")
        elif type == "line_failed":
            print(f"{c}✗ line {data['line']} [{data['error']['code']}] {data['error']['message']}{reset}")
        elif type == "status":
            print(f"  · {data['text']}")
        elif type == "cache_hit":
            print(f"{c}  ⚡ cache hit: {data['target']}{reset}")
        elif type == "result_ready":
            r = data["result"]
            print(f"{c}=== result ===\n{r.get('text') or json.dumps(r.get('rows'), indent=1)}{reset}")
        elif type == "run_finished":
            m = data["metrics"]
            print(f"{c}\nRun {data['status']}: {m['steps']} steps, {m['elapsed']}s, {m['model_calls']} model calls, "
                  f"${m['cost']:.4f}, cache hit rate {m['cache_hit_rate']:.0%}, fixes {m['fixes']}{reset}")
            if data.get("error"):
                print(f"  error: {data['error'].get('message')}")
        elif self.verbose and type not in ("element_found",):
            print(f"  [{type}] {json.dumps(data, default=str)[:200]}")

    def ask_user(self, question, stop):
        return input(f"\n? {question}\n> ")

    def confirm(self, summary, stop):
        if self.yes:
            print(f"  (auto-confirmed) {summary}")
            return True
        return input(f"\n! Confirm: {summary} [y/N] ").strip().lower() in ("y", "yes")

    def before_capture(self):
        pass

    def after_capture(self):
        pass


def main():
    p = argparse.ArgumentParser()
    p.add_argument("task", nargs="?", default="")
    p.add_argument("--script", help="run this script file instead of asking the planner")
    p.add_argument("--saved", help="run a saved task by name")
    p.add_argument("--yes", action="store_true", help="auto-confirm sensitive actions")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()

    from .agent import Agent

    host = TerminalHost(args.yes, args.verbose)
    agent = Agent(host)
    from .browser.bridge import start_bridge

    start_bridge()  # lets SDK scripts drive Chrome through the extension
    try:
        import signal

        signal.signal(signal.SIGINT, lambda *_: agent.stop())
    except Exception:
        pass
    if args.saved:
        agent.run_saved(name=args.saved)
    elif args.script:
        with open(args.script, encoding="utf-8") as fh:
            agent.run_task(args.task or args.script, fh.read())
    elif args.task:
        agent.run_task(args.task)
    else:
        p.print_help()
        sys.exit(1)


if __name__ == "__main__":
    threading.current_thread().name = "agent-cli"
    main()
