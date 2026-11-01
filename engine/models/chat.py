"""Conversation: every message first goes to a quick chat turn (Muse Spark). It answers like a normal assistant, and
calls the run_task tool when the user wants something done on the computer; only then does the planner write a
script. The chat keeps the conversation (and short notes on finished runs) so follow-ups like "do that again" work."""
from __future__ import annotations

import json

from ..config import config
from .client import ModelClient, interruptible

CHAT_SYSTEM = """You are Agent, an assistant on the user's Mac that can also take control of the computer: it sees \
the screen, clicks, types, opens apps and websites, reads what's shown, and writes and runs small programs to do tasks.
Talk naturally and briefly, like a helpful chat assistant. Answer questions, chat, and explain things yourself.
Call run_task only when the user wants something done or looked up on the computer or in an app/website (open, \
send, click, find on screen, fill in, check their messages...). Write the task as one clear instruction that \
includes any details from the conversation. When you call it, also say in a few words what you're about to do.
Don't call it for greetings, small talk, or questions you can answer without the computer.
If one of the user's saved tasks below already does what they want, call run_saved_task with its exact name and the \
inputs it needs (taken from the conversation) instead of run_task: it is faster and already proven.
{saved}"""

RUN_TASK_TOOL = {
    "type": "function",
    "function": {
        "name": "run_task",
        "description": "Take control of the computer to do a task (apps, websites, clicking, typing, reading the screen).",
        "parameters": {
            "type": "object",
            "properties": {"task": {"type": "string", "description": "The task as one clear, complete instruction."}},
            "required": ["task"],
        },
    },
}

RUN_SAVED_TOOL = {
    "type": "function",
    "function": {
        "name": "run_saved_task",
        "description": "Run one of the user's saved tasks by its exact name.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "The saved task's exact name."},
                "inputs": {"type": "object", "description": "Values for the task's inputs, by input name."},
            },
            "required": ["name"],
        },
    },
}

MAX_TURNS = 24  # messages kept for context


class Chat:
    def __init__(self, client: ModelClient):
        self.client = client
        self.history: list[dict] = []

    def clear(self):
        self.history = []

    def note(self, text: str):
        """Something the user saw happen (a run finished), so later turns can refer to it."""
        self.history.append({"role": "assistant", "content": text})
        self.history[:] = self.history[-MAX_TURNS:]

    def respond(self, text: str, saved_tasks: list[dict] | None = None) -> tuple[str, tuple | None]:
        """(reply to show, what to do): None, ("task", instruction) or ("saved", name, inputs).
        saved_tasks: [{"name", "description", "inputs"}] the user can have run by name."""
        import time

        from .client import _debug_call, current_metrics

        self.history.append({"role": "user", "content": text})
        self.history[:] = self.history[-MAX_TURNS:]
        saved = ""
        if saved_tasks:
            lines = []
            for t in saved_tasks:
                ins = ", ".join(f"{k} ({v})" for k, v in (t.get("inputs") or {}).items())
                lines.append(f"- {t['name']}" + (f": {t['description']}" if t.get("description") else "") +
                             (f" [inputs: {ins}]" if ins else ""))
            saved = "SAVED TASKS:\n" + "\n".join(lines)
        messages = [{"role": "system", "content": CHAT_SYSTEM.format(saved=saved)}] + self.history
        t0 = time.time()
        kwargs = {"tools": [RUN_TASK_TOOL, RUN_SAVED_TOOL], "max_tokens": 600 + config.reasoning_headroom, "temperature": 0.4}
        if not self.client.openrouter:
            kwargs["reasoning_effort"] = "low"
        resp = interruptible(lambda: self.client.client.chat.completions.create(
            model=config.chat_model, messages=messages, **kwargs))
        tin, tout, cost = self.client._cost(getattr(resp, "usage", None))
        current_metrics().record_call("chat", time.time() - t0, tin, tout, cost)
        msg = resp.choices[0].message
        reply = (msg.content or "").strip()
        action = None
        for call in msg.tool_calls or []:
            try:
                args = json.loads(call.function.arguments or "{}")
            except ValueError:
                args = {}
            if call.function.name == "run_task":
                action = ("task", (args.get("task") or "").strip() or text)
                break
            if call.function.name == "run_saved_task" and args.get("name"):
                inputs = args.get("inputs") if isinstance(args.get("inputs"), dict) else {}
                action = ("saved", str(args["name"]), {k: str(v) for k, v in inputs.items()})
                break
        _debug_call("chat", config.chat_model, messages, reply + (f"\n[tool] {action}" if action else ""),
                    time.time() - t0, tokens=(tin, tout))
        what = f"Running saved task {action[1]}" if action and action[0] == "saved" else (
            f"Doing: {action[1]}" if action else "")
        self.history.append({"role": "assistant", "content": reply or what})
        return reply, action
