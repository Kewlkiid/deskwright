"""Self-healing: when a line fails, first try a learned detour (a known way back to that step, no model call), else
ask the planner for a continuation and resume in the same namespace. Each repair that had to undo something leaves
a new detour behind (runner/detours.py)."""
from __future__ import annotations

import ast
import re

from ..config import config
from ..sdk import SDK_NAMES, build_namespace
from ..sdk.context import RunContext
from ..sdk.errors import TERMINAL_ERRORS, StoppedError
from ..sdk.results import show
from . import detours, schema
from .executor import execute, failing_line, to_agent_error
from .validate import safe_builtins, validate

STOP_WORDS = {"", "stop", "cancel", "quit", "no", "abort", "end"}


def describe_vars(ns: dict) -> dict:
    out = {}
    for k, v in ns.items():
        if k.startswith("_") or k in SDK_NAMES:
            continue
        if isinstance(v, (list, tuple)):
            sample = repr(v[0])[:120] if v else ""
            out[k] = f"{type(v).__name__} of {len(v)} items" + (f", first: {sample}" if sample else "")
        elif isinstance(v, dict):
            out[k] = f"dict: {repr(v)[:160]}"
        else:
            out[k] = f"{type(v).__name__}: {repr(v)[:160]}"
    return out


def _shape(src: str) -> str:
    return re.sub(r"(\"[^\"]*\"|'[^']*')", "S", src or "")


def user_vars(ns: dict) -> set[str]:
    return {k for k in ns if not k.startswith("_") and k not in SDK_NAMES}


def flush_pending(ctx: RunContext):
    """At the end of a script, check the last action's expectation."""
    p = ctx.pending
    if p is None:
        return
    shot = ctx.capture()
    if p.explicit:
        r = ctx.models.vision.check(shot.image, p.expect)
        ctx.resolve_pending(shot, r["result"], r.get("reason", ""))
    else:
        ctx.resolve_pending(shot)


ACTION_CALLS = {"click", "double_click", "right_click", "move_mouse", "type_into", "drag", "scroll_until", "type_text",
                "press", "hotkey", "scroll", "open_app", "focus_window", "open_url", "read_table", "read_text"}


def corrected_step(continuation: str) -> str:
    """The first action line of a continuation: the corrected version of the step that failed."""
    try:
        tree = ast.parse(continuation)
    except SyntaxError:
        return ""
    lines = continuation.splitlines()
    calls = sorted((n.lineno, n.col_offset) for n in ast.walk(tree)
                   if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ACTION_CALLS)
    if calls:
        return lines[calls[0][0] - 1].strip()
    return lines[tree.body[0].lineno - 1].strip() if tree.body else ""


def try_detour(ctx: RunContext, ns: dict, src: str, shot) -> bool:
    """Run a learned way back for this step if the screen looks like its remembered wrong state."""
    found = detours.find(ctx.detours + ctx.new_detours, src, ctx.window(), shot.image)
    if found is None:
        return False
    d, dist = found
    if dist > detours.EXACT_DIST:
        # Only roughly alike: screens can look similar at this resolution, so confirm the wrong state first.
        ctx.status(f"Checking: {d.when}")
        if not ctx.models.vision.check(shot.image, d.when).get("result"):
            ctx.log(f"detour skipped: the screen resembles but isn't '{d.when}'")
            return False
    d.used_this_run += 1
    ctx.status(f"Known way back: {d.when}")
    ctx.log(f"detour for `{src}`: {d.when} -> {d.recover!r}")
    ctx.emit("detour", line=ctx.current_line, segment=ctx.segment, when=d.when, recover=d.recover)
    ctx.pending = None
    try:
        execute(d.recover, ns, ctx)
    except TERMINAL_ERRORS:
        raise
    except Exception as e:  # noqa: BLE001 - the way back didn't work this time: heal normally
        ctx.log(f"detour failed: {e}")
        return False
    if d.id is not None:
        ctx.db.detour_used(d.id)
    return True


def run_with_healing(ctx: RunContext, script: str, sdk_ref: str) -> dict:
    ns = build_namespace(ctx.progress)
    ns["__builtins__"] = safe_builtins(lambda *a, **k: show(" ".join(str(x) for x in a)))
    current = script
    full_script = script
    segment = 0
    # Fixes in a row for the same step: same line (ignoring string literals) or no action succeeded since the last fix.
    chain = 0
    steps_at_fix = -1
    budget = config.max_fixes_per_run
    asked_user = False
    user_hint = ""
    last_fixed_key: str | None = None

    while True:
        ctx.segment = segment
        try:
            execute(current, ns, ctx)
            flush_pending(ctx)
            if last_fixed_key is not None:
                ctx.metrics.fixes_succeeded += 1
            return {"status": "succeeded", "final_script": full_script}
        except TERMINAL_ERRORS:
            raise
        except Exception as raw:  # noqa: BLE001 - every other failure goes to the fixer
            err = to_agent_error(raw)
            line = failing_line(raw, ctx) or 1
            lines = current.splitlines()
            src = lines[line - 1].strip() if 0 < line <= len(lines) else ""
            ctx.emit(
                "line_failed",
                segment=segment,
                line=line,
                source=src,
                error=err.to_dict(),
                expect=err.detail.get("expect"),
                observation=err.detail.get("observation") or err.detail.get("seen"),
            )
            ctx.log(f"FAILED line {line} ({src}): {err.code}: {err.message}")
            # Whatever went wrong, don't trust this step's cached positions again: the retry, the rewrite and the
            # next run all find its elements fresh (a wrong cached spot would otherwise repeat the same mistake).
            window = ctx.window()
            for t in detours.targets_in(src):
                ctx.cache.invalidate(window, t)
            shot = ctx.capture()
            if try_detour(ctx, ns, src, shot):
                # Back where the step should start: retry it (and everything after it) as written.
                segment += 1
                retry = detours.remainder_from(current, line)
                ctx.emit("line_rewritten", segment=segment, from_segment=segment - 1, failed_line=line, script=retry,
                         explanation="Took a learned way back, no model call. Retrying the step.", full_script=full_script,
                         detour=True)
                current = retry
                continue
            same_step = last_fixed_key is not None and (
                ctx.metrics.steps == steps_at_fix or _shape(src) == _shape(last_fixed_key)
            )
            if same_step:
                chain += 1
            else:
                if last_fixed_key is not None:
                    ctx.metrics.fixes_succeeded += 1  # the previous fix got past its step
                chain = 1
            if chain > config.max_fixes_per_line or ctx.metrics.fixes >= budget:
                if asked_user:
                    return {"status": "failed", "final_script": full_script, "error": err.to_dict()}
                hint = ctx.host.ask_user(
                    f"I'm stuck on line {line}: `{src}`\n{err.message}\n\nHow should I continue? (say \"stop\" to end the run)",
                    ctx.stop_event,
                )
                ctx.check_stop()
                if hint.strip().lower() in STOP_WORDS:
                    raise StoppedError("Run ended after repeated failures")
                asked_user = True
                user_hint = hint
                chain = 1
                budget = ctx.metrics.fixes + config.max_fixes_per_line

            ctx.metrics.fixes += 1
            ctx.push_metrics()
            ctx.status(f"Fixing line {line}…")
            fix = None
            rejection = ""
            for _ in range(2):
                candidate = ctx.models.planner.fix_script(
                    task=ctx.task,
                    script=current,
                    failing_line=line,
                    error=err.to_dict(),
                    screenshot=shot.image,
                    progress_log=ctx.progress.log(),
                    variables=describe_vars(ns),
                    action_log=ctx.action_log,
                    user_hint=(user_hint + ("\n" + rejection if rejection else "")).strip(),
                    sdk_reference=sdk_ref,
                )
                problems = validate(candidate["continuation"], SDK_NAMES, extra_names=user_vars(ns))
                if not problems and candidate["continuation"].strip():
                    fix = candidate
                    break
                rejection = "Your previous rewrite was rejected by the validator: " + "; ".join(problems or ["empty"])
            if fix is None:
                return {"status": "failed", "final_script": full_script, "error": {"message": rejection}}

            if fix["full_script"] and not validate(fix["full_script"], SDK_NAMES):
                candidate_full = fix["full_script"]
                if not schema.header_problems(script) and not schema.same_schema(script, candidate_full):
                    # The header is the task's contract with its callers: a repair never drops or renames it.
                    ctx.log("the rewrite changed the INPUTS/OUTPUTS header; restored the original")
                    candidate_full = schema.with_header(candidate_full, schema.header_source(script))
                full_script = candidate_full
            recovery = fix.get("recovery", "").strip()
            if recovery and validate(recovery, SDK_NAMES, extra_names=user_vars(ns)):
                recovery = ""  # an invalid way back is dropped, not run
            if recovery:
                # Remember the way back for the corrected step, keyed to how the wrong screen looked.
                step_src = corrected_step(fix["continuation"])
                if step_src:
                    learned = detours.Detour(step=detours.step_key(step_src), when=fix.get("wrong_state") or err.message[:100],
                                             screen=detours.screen_hash(shot.image), window=ctx.window(),
                                             recover=recovery, source=step_src)
                    ctx.new_detours.append(learned)
                    ctx.emit("detour_learned", when=learned.when, recover=recovery, step=step_src)
                    ctx.log(f"learned a way back for `{step_src}`: {learned.when} -> {recovery!r}")
                fix["continuation"] = recovery + "\n" + fix["continuation"]
            segment += 1
            ctx.emit(
                "line_rewritten",
                segment=segment,
                from_segment=segment - 1,
                failed_line=line,
                script=fix["continuation"],
                explanation=fix["explanation"],
                full_script=full_script,
            )
            ctx.log(f"rewrote from line {line}: {fix['explanation']}")
            ctx.pending = None
            current = fix["continuation"]
            last_fixed_key = src
            steps_at_fix = ctx.metrics.steps
