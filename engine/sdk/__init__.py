"""The Agent SDK exposed to generated scripts. SDK_FUNCTIONS is the allowlist's source of truth."""
from __future__ import annotations

import inspect

from . import actions, apps, browser, questions, raw, results, user, waiting
from .errors import SCRIPT_ERRORS
from .progress import Progress, checkpoint

SDK_FUNCTIONS = {
    # Prompt-driven actions
    "click": actions.click,
    "double_click": actions.double_click,
    "right_click": actions.right_click,
    "move_mouse": actions.move_mouse,
    "type_into": actions.type_into,
    "drag": actions.drag,
    "scroll_until": actions.scroll_until,
    "use_grounding": actions.use_grounding,
    # Raw input
    "type_text": raw.type_text,
    "press": raw.press,
    "hotkey": raw.hotkey,
    "scroll": raw.scroll,
    "clear_focused_input": raw.clear_focused_input,
    # Screen questions
    "ask": questions.ask,
    "check": questions.check,
    "expect": questions.expect,
    "is_loaded": questions.is_loaded,
    "read_text": questions.read_text,
    "read_table": questions.read_table,
    # Waiting
    "wait": waiting.wait,
    "wait_for": waiting.wait_for,
    # Apps and windows
    "open_app": apps.open_app,
    "focus_window": apps.focus_window,
    "active_window": apps.active_window,
    # Browser (Chrome with the agent extension)
    "open_url": browser.open_url,
    "network_response": browser.network_response,
    "page_js": browser.page_js,
    # Results
    "summarize": results.summarize,
    "make_table": results.make_table,
    "show": results.show,
    "export": results.export,
    # Progress
    "checkpoint": checkpoint,
    # User
    "ask_user": user.ask_user,
    "confirm_with_user": user.confirm_with_user,
}

SDK_NAMES = set(SDK_FUNCTIONS) | {"progress"} | set(SCRIPT_ERRORS)

FAMILIES = [
    ("Prompt-driven actions (target = visual description; all accept expect= and confirm=)",
     ["click", "double_click", "right_click", "move_mouse", "type_into", "drag", "scroll_until"]),
    ("How elements are found", ["use_grounding"]),
    ("Raw input (no model call)", ["type_text", "press", "hotkey", "scroll", "clear_focused_input"]),
    ("Screen questions", ["ask", "check", "expect", "is_loaded", "read_text", "read_table"]),
    ("Waiting", ["wait", "wait_for"]),
    ("Apps and windows", ["open_app", "focus_window", "active_window"]),
    ("Browser (Google Chrome with the agent extension; the actions above also work there)",
     ["open_url", "network_response", "page_js"]),
    ("Results", ["summarize", "make_table", "show", "export"]),
    ("User", ["ask_user", "confirm_with_user"]),
]


def build_namespace(progress: Progress) -> dict:
    ns = dict(SDK_FUNCTIONS)
    ns["progress"] = progress
    ns.update(SCRIPT_ERRORS)
    return ns


def sdk_reference() -> str:
    """Method signatures and docstrings only, for the planner prompt."""
    out = []
    for title, names in FAMILIES:
        out.append(f"## {title}")
        for n in names:
            fn = SDK_FUNCTIONS[n]
            doc = inspect.getdoc(fn) or ""
            out.append(f"{n}{inspect.signature(fn, eval_str=True)}\n    " + doc.replace("\n", "\n    "))
        out.append("")
    out.append("## Progress")
    for n in ("pending", "done", "reached"):
        fn = getattr(Progress, n)
        sig = str(inspect.signature(fn, eval_str=True)).replace("(self, ", "(").replace("(self)", "()")
        out.append(f"progress.{n}{sig}\n    {inspect.getdoc(fn)}")
    out.append(f"checkpoint{inspect.signature(checkpoint, eval_str=True)}\n    {inspect.getdoc(checkpoint)}")
    out.append(
        "\n## Notes\n"
        "- read_table returns a list of dict rows; row[\"name\"] matches columns case-insensitively.\n"
        "- In Google Chrome the actions use the page's DOM (element names, labels, text) before the screenshot, so "
        "describe web targets by their visible label or text, e.g. 'Save button', 'Customer field'.\n"
        "- Errors (ElementNotFoundError, ExpectationFailedError, NoChangeError, FieldChangedError, WindowLostError, "
        "TimeoutError, ...) are handled by the runtime, which repairs the script. Don't catch them."
    )
    return "\n".join(out)
