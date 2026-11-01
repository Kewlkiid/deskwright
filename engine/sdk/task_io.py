"""Task inputs and outputs: inp() reads a declared input, output() records a result value for the caller."""
from __future__ import annotations

import json
import re

from ..runner.schema import coerce, split_desc
from .context import current
from .errors import InputMissingError, ScriptError
from .results import show


QUESTION_START = re.compile(r"^(how|what|which|who|whom|whose|when|where|why|is|are|do|does|did|should|can|could|"
                            r"would|will)\b", re.I)
# Words that keep their capital in the middle of a question ("What is the Wikipedia article...").
PROPER = {"wikipedia", "discord", "google", "chrome", "slack", "notion", "mac", "apple", "app", "github", "youtube",
          "gmail", "safari", "finder", "excel", "word", "i"}


def as_question(text: str, typ: str = "str") -> str:
    """An input's description as a question to ask out loud: "Wikipedia article to look up" ->
    "What is the Wikipedia article to look up?"."""
    t = text.strip().rstrip(".:")
    whether = re.match(r"^whether\s+(?:to\s+)?(.+)$", t, re.I)
    if whether:
        return f"Should I {whether.group(1).rstrip('?')}?"
    if t.endswith("?") or QUESTION_START.match(t):
        q = t if t.endswith("?") else t + "?"
    else:
        t = re.sub(r"^(the|a|an)\s+", "", t, flags=re.I)
        first = t.split(" ", 1)[0]
        if first.lower() not in PROPER and not first.isupper():
            t = t[:1].lower() + t[1:]
        q = f"What is the {t}?"
    q = q[:1].upper() + q[1:]
    if typ == "bool":
        q += " (yes or no)"
    elif "|" in typ:
        q += " (" + " or ".join(typ.split("|")) + ")"
    elif typ in ("int", "float"):
        q += " (a number)"
    return q


def inp(name: str):
    """Value of the task input `name` (declared in INPUTS). It comes from whoever started the task (the CLI's
    --input, another program); if nothing was passed, the user is asked, using the input's description."""
    ctx = current()
    desc = ctx.input_schema.get(name, "")
    if name in ctx.inputs:
        value = ctx.inputs[name]
    else:
        typ, text = split_desc(desc)
        if ctx.no_ask:
            raise InputMissingError(f'Missing input "{name}"' + (f" ({text})" if text else "") + "; pass it with --input")
        question = as_question(text or name.replace("_", " "), typ)
        value = ctx.host.ask_user(question, ctx.stop_event)
        ctx.check_stop()
    if desc:
        try:
            value = coerce(value, desc)
        except ValueError as e:
            raise InputMissingError(f'Input "{name}" {e}') from None
    ctx.inputs[name] = value
    ctx.log(f"inp({name!r}) -> {str(value)[:60]!r}")
    return value


def output(**values) -> None:
    """Record result values for this run, e.g. output(app_id=app_id, ad_unit_ids=ids). They are returned to whoever
    started the task (the CLI's --json result); in the window they appear at the end only if the script showed
    nothing itself (no show() of the same thing twice). Values must be JSON-serializable."""
    ctx = current()
    for k, v in values.items():
        try:
            json.dumps(v)
        except (TypeError, ValueError):
            raise ScriptError(f'output {k}={v!r} is not JSON-serializable (use str, numbers, lists or dicts)') from None
    ctx.outputs.update(values)
    ctx.log(f"output({', '.join(values)})")


def show_unshown_outputs(ctx) -> None:
    """At the end of a successful run: a script that recorded outputs but showed nothing gets them shown."""
    if not ctx.outputs or ctx.results:
        return
    lines = [f"- **{k}**: {v if isinstance(v, (str, int, float, bool)) or v is None else json.dumps(v)}"
             for k, v in ctx.outputs.items()]
    show("\n".join(lines), title="Output")
