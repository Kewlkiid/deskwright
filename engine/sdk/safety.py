"""Actions that must be confirmed by the user, whatever the script says."""
from __future__ import annotations

import re

SENSITIVE = re.compile(
    r"\b(send\w*|sent|submit\w*|purchas\w*|buy\w*|pay|paid|payment\w*|checkout|check out|place order|order now|"
    r"delet\w*|remov\w*|eras\w*|trash\w*|discard\w*|transfer\w*|wire|publish\w*|post|posted|tweet\w*|"
    r"reply all|unsubscrib\w*|uninstall\w*|empty trash|book now|reserv\w*|leave site|leave page|don'?t save|"
    r"close without saving)\b",
    re.I,
)


# Fields where pressing Enter sends what was typed to other people.
MESSAGE_FIELD = re.compile(r"\b(message\w*|chat|comment\w*|repl\w*|compose|post|tweet|dm|e-?mail|mail|caption)\b", re.I)


def is_sensitive(*texts: str | None) -> bool:
    return any(t and SENSITIVE.search(t) for t in texts)


def needs_approval(src: str) -> bool:
    """A script line whose action had to be approved: if it fails, whatever replaces it must ask too."""
    return bool(re.search(r"confirm\s*=\s*True", src)) or (
        bool(re.match(r"\s*(click|double_click|right_click|type_into|press|hotkey)\(", src)) and is_sensitive(src))


def ask_approval(ctx, summary: str):
    """Ask the user; a yes settles any approval still owed from a failed step."""
    from .errors import UserDeclinedError

    ctx.status("Waiting for confirmation")
    if not ctx.host.confirm(summary, ctx.stop_event):
        raise UserDeclinedError(f"User declined: {summary.splitlines()[0]}")
    ctx.check_stop()
    ctx.owed_confirm = None
    ctx.typed_target = None


def owed_summary(ctx, action: str) -> str | None:
    if ctx.owed_confirm:
        return f"{action}\nThis replaces a step that needed your approval: {ctx.owed_confirm}"
    return None
