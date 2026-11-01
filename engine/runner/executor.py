"""Runs a validated script one top-level statement at a time in a restricted namespace,
reporting each line as it starts and passes."""
from __future__ import annotations

import ast
import sys

from ..sdk.context import RunContext
from ..sdk.errors import AgentError, ScriptError

SCRIPT_FILE = "<agent-script>"


class LineTracer:
    """sys.settrace hook that only follows frames of the generated script."""

    def __init__(self, ctx: RunContext):
        self.ctx = ctx
        self.line: int | None = None

    def __call__(self, frame, event, arg):
        if frame.f_code.co_filename == SCRIPT_FILE:
            return self.local
        return None

    def local(self, frame, event, arg):
        if event == "line":
            self.ctx.check_stop()
            self.enter(frame.f_lineno)
        return self.local

    def enter(self, lineno: int):
        if lineno == self.line:
            return
        self.passed()
        self.line = lineno
        self.ctx.current_line = lineno
        self.ctx.emit("line_started", line=lineno, segment=self.ctx.segment)

    def passed(self):
        if self.line is not None:
            self.ctx.emit("line_passed", line=self.line, segment=self.ctx.segment)


def failing_line(exc: BaseException, ctx: RunContext) -> int | None:
    if isinstance(exc, AgentError) and exc.line:
        return exc.line
    line = None
    tb = exc.__traceback__
    while tb is not None:
        if tb.tb_frame.f_code.co_filename == SCRIPT_FILE:
            line = tb.tb_lineno
        tb = tb.tb_next
    return line or ctx.current_line


def to_agent_error(exc: BaseException) -> AgentError:
    if isinstance(exc, AgentError):
        return exc
    return ScriptError(f"{type(exc).__name__}: {exc}", detail={"python_error": type(exc).__name__})


def execute(script: str, namespace: dict, ctx: RunContext) -> None:
    """Execute statement by statement. Exceptions propagate to the healer; the namespace keeps
    every variable assigned so far, so a continuation can resume in it."""
    tree = ast.parse(script, filename=SCRIPT_FILE)
    tracer = LineTracer(ctx)
    previous = sys.gettrace()
    sys.settrace(tracer)
    try:
        for stmt in tree.body:
            ctx.check_stop()
            code = compile(ast.Module(body=[stmt], type_ignores=[]), SCRIPT_FILE, "exec")
            exec(code, namespace)  # noqa: S102 - validated script, restricted builtins
            tracer.passed()
            tracer.line = None
    finally:
        sys.settrace(previous)
