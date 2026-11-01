"""Pausing the run to ask the user something in the chat window."""
from __future__ import annotations

from .context import current


def ask_user(question: str) -> str:
    """Pause and ask the user a question in the chat; returns their answer."""
    ctx = current()
    ctx.status(f"Waiting for your answer: {question}")
    answer = ctx.host.ask_user(question, ctx.stop_event)
    ctx.check_stop()
    ctx.log(f"ask_user({question!r}) -> {answer!r}")
    return answer


def confirm_with_user(summary: str) -> bool:
    """Pause and ask the user to approve something; returns True if they said yes."""
    ctx = current()
    ctx.status("Waiting for confirmation")
    ok = ctx.host.confirm(summary, ctx.stop_event)
    ctx.check_stop()
    ctx.log(f"confirm_with_user -> {ok}")
    if ok:
        ctx.owed_confirm = None
        ctx.typed_target = None
    return ok
