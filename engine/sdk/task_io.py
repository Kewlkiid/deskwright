"""Task inputs and outputs: inp() reads a declared input, output() records a result value for the caller."""
from __future__ import annotations

import json

from ..runner.schema import coerce, split_desc
from .context import current
from .errors import InputMissingError, ScriptError
from .results import show


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
        question = f"{text or name}" + (f" ({typ})" if typ != "str" else "")
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
