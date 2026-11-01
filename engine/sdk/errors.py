"""Typed errors. Each carries a code, a short fix hint for the fixer, retryability and a screenshot."""
from __future__ import annotations

from typing import Any


class AgentError(Exception):
    code = "agent_error"
    default_fix = "Look at the screenshot and adjust the failing step."
    default_retryable = True

    def __init__(
        self,
        message: str,
        *,
        fix: str | None = None,
        retryable: bool | None = None,
        screenshot: Any = None,
        line: int | None = None,
        detail: dict | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.fix = fix or self.default_fix
        self.retryable = self.default_retryable if retryable is None else retryable
        self.screenshot = screenshot
        # Script line the error belongs to. Set when the failure is detected on a later
        # line (an unmet expectation is noticed on the next screenshot).
        self.line = line
        self.detail = detail or {}

    def to_dict(self) -> dict:
        return {
            "type": type(self).__name__,
            "code": self.code,
            "message": self.message,
            "fix": self.fix,
            "retryable": self.retryable,
            "line": self.line,
            **({"detail": self.detail} if self.detail else {}),
        }


class ElementNotFoundError(AgentError):
    code = "element_not_found"
    default_fix = "The target wasn't visible. Describe it differently, scroll, open the right view, or wait for it."


class ExpectationFailedError(AgentError):
    code = "expectation_failed"
    default_fix = "The action ran but the expected result didn't appear. Check the screen and pick a different action."


class NoChangeError(AgentError):
    code = "no_change"
    default_fix = "Nothing changed after the action. The click may have missed or the app ignored it."


class FieldChangedError(AgentError):
    code = "field_changed"
    default_fix = "The text field changed while typing. Re-find the field and check what was already typed."


class WindowLostError(AgentError):
    code = "window_lost"
    default_fix = "The target window closed or lost focus. Re-open or focus it before continuing."


class AgentTimeoutError(AgentError):
    code = "timeout"
    default_fix = "Timed out. The action may already have happened: check the screen before retrying, never repeat blindly."


class UserDeclinedError(AgentError):
    code = "user_declined"
    default_fix = "The user declined. Do not retry."
    default_retryable = False


class StoppedError(AgentError):
    code = "stopped"
    default_fix = "The user stopped the run."
    default_retryable = False


class ModelError(AgentError):
    code = "model_error"
    default_fix = "A model API call failed."


class ScriptError(AgentError):
    """A plain Python error raised by the generated script itself (KeyError, NameError, ...)."""

    code = "script_error"
    default_fix = "The script has a bug. Fix the code at this line."


class InputMissingError(AgentError):
    """A declared input had no value and asking was not allowed (CLI --no-ask), or the value didn't fit its type."""

    code = "input_missing"
    default_fix = "Pass the input when starting the task."
    default_retryable = False


# Errors that end the run and are never sent to the fixer.
TERMINAL_ERRORS = (StoppedError, UserDeclinedError, InputMissingError)

# Names exposed to generated scripts. TimeoutError is the SDK name for AgentTimeoutError.
SCRIPT_ERRORS = {
    "AgentError": AgentError,
    "ElementNotFoundError": ElementNotFoundError,
    "ExpectationFailedError": ExpectationFailedError,
    "NoChangeError": NoChangeError,
    "FieldChangedError": FieldChangedError,
    "WindowLostError": WindowLostError,
    "TimeoutError": AgentTimeoutError,
    "UserDeclinedError": UserDeclinedError,
    "StoppedError": StoppedError,
    "ModelError": ModelError,
}
