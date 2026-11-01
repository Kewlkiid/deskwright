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

    def respond(self, text: str, saved_tasks: list[str] | None = None) -> tuple[str, str | None]:
        """(reply to show, task to run or None)."""
        import time

        from .client import _debug_call, current_metrics

        self.history.append({"role": "user", "content": text})
        self.history[:] = self.history[-MAX_TURNS:]
        saved = ("The user has these saved tasks, which you can run by name: " + ", ".join(saved_tasks) + "."
                 if saved_tasks else "")
        messages = [{"role": "system", "content": CHAT_SYSTEM.format(saved=saved)}] + self.history
        t0 = time.time()
        kwargs = {"tools": [RUN_TASK_TOOL], "max_tokens": 600 + config.reasoning_headroom, "temperature": 0.4}
        if not self.client.openrouter:
            kwargs["reasoning_effort"] = "low"
        resp = interruptible(lambda: self.client.client.chat.completions.create(
            model=config.chat_model, messages=messages, **kwargs))
        tin, tout, cost = self.client._cost(getattr(resp, "usage", None))
        current_metrics().record_call("chat", time.time() - t0, tin, tout, cost)
        msg = resp.choices[0].message
        reply = (msg.content or "").strip()
        task = None
        for call in msg.tool_calls or []:
            if call.function.name == "run_task":
                try:
                    task = (json.loads(call.function.arguments or "{}").get("task") or "").strip() or text
                except ValueError:
                    task = text
                break
        _debug_call("chat", config.chat_model, messages, reply + (f"\n[run_task] {task}" if task else ""),
                    time.time() - t0, tokens=(tin, tout))
        self.history.append({"role": "assistant", "content": reply or (f"Doing: {task}" if task else "")})
        return reply, task
