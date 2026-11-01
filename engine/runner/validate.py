"""AST validation of generated scripts: only the SDK and safe built-ins may be used."""
from __future__ import annotations

import ast
import builtins

SAFE_BUILTINS = {
    "len", "range", "enumerate", "str", "int", "float", "bool", "round", "min", "max", "sum", "sorted",
    "reversed", "list", "dict", "set", "tuple", "zip", "abs", "any", "all", "map", "filter", "isinstance",
    "print", "True", "False", "None",
}

BANNED_NAMES = {
    "exec", "eval", "open", "compile", "__import__", "getattr", "setattr", "delattr", "globals", "locals",
    "vars", "input", "breakpoint", "help", "dir", "type", "object", "memoryview", "super", "classmethod",
    "staticmethod", "property", "exit", "quit", "id", "hash", "iter", "next", "callable", "issubclass",
}

# str.format/format_map can walk attributes through "{0.__class__}" style fields.
BANNED_ATTRS = {"format", "format_map", "mro", "gi_frame", "gi_code", "f_globals", "f_locals", "f_back", "cr_frame"}

FORBIDDEN_NODES = {
    ast.Import: "imports are not allowed",
    ast.ImportFrom: "imports are not allowed",
    ast.Global: "global is not allowed",
    ast.Nonlocal: "nonlocal is not allowed",
    ast.ClassDef: "classes are not allowed",
    ast.AsyncFunctionDef: "async code is not allowed",
    ast.Await: "async code is not allowed",
    ast.AsyncFor: "async code is not allowed",
    ast.AsyncWith: "async code is not allowed",
    ast.With: "with-blocks are not allowed",
    ast.Try: "try/except is not allowed: the runtime handles errors",
    ast.Raise: "raise is not allowed",
    ast.Delete: "del is not allowed",
    ast.Yield: "generators are not allowed",
    ast.YieldFrom: "generators are not allowed",
}
if hasattr(ast, "TryStar"):
    FORBIDDEN_NODES[ast.TryStar] = "try/except is not allowed: the runtime handles errors"


def _assigned_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names.add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.Lambda)):
            if isinstance(node, ast.FunctionDef):
                names.add(node.name)
            args = node.args
            for a in args.posonlyargs + args.args + args.kwonlyargs:
                names.add(a.arg)
            if args.vararg:
                names.add(args.vararg.arg)
            if args.kwarg:
                names.add(args.kwarg.arg)
    return names


def validate(script: str, sdk_names: set[str], extra_names: set[str] | None = None) -> list[str]:
    """Return a list of problems (empty = valid). extra_names: variables already defined (continuations)."""
    try:
        tree = ast.parse(script, filename="<agent-script>")
    except SyntaxError as e:
        return [f"syntax error on line {e.lineno}: {e.msg}"]
    problems: list[str] = []
    assigned = _assigned_names(tree)
    allowed = SAFE_BUILTINS | set(sdk_names) | assigned | set(extra_names or ())
    for node in ast.walk(tree):
        line = getattr(node, "lineno", "?")
        for bad, why in FORBIDDEN_NODES.items():
            if isinstance(node, bad):
                problems.append(f"line {line}: {why}")
        if isinstance(node, ast.FunctionDef) and node.decorator_list:
            problems.append(f"line {line}: decorators are not allowed")
        if isinstance(node, ast.Name):
            if node.id.startswith("_"):
                problems.append(f"line {line}: names starting with '_' are not allowed ({node.id})")
            elif node.id in BANNED_NAMES:
                problems.append(f"line {line}: {node.id} is not allowed")
            elif isinstance(node.ctx, ast.Load) and node.id not in allowed:
                problems.append(f"line {line}: unknown name {node.id!r} (only SDK functions and safe built-ins)")
            elif isinstance(node.ctx, ast.Store) and node.id in sdk_names:
                problems.append(f"line {line}: don't overwrite the SDK name {node.id!r}")
        elif isinstance(node, ast.Attribute):
            if node.attr.startswith("_"):
                problems.append(f"line {line}: attributes starting with '_' are not allowed ({node.attr})")
            elif node.attr in BANNED_ATTRS:
                problems.append(f"line {line}: .{node.attr} is not allowed (use f-strings)")
        elif isinstance(node, ast.arg) and node.arg.startswith("_"):
            problems.append(f"line {line}: names starting with '_' are not allowed ({node.arg})")
    # De-duplicate, keep order.
    return list(dict.fromkeys(problems))


def safe_builtins(show_fn=None) -> dict:
    b = {n: getattr(builtins, n) for n in SAFE_BUILTINS if n not in ("True", "False", "None", "print")}
    b["print"] = show_fn or (lambda *a, **k: None)
    return b


# Calls that look at or act on the screen, and the calls that say which app the agent is looking at.
SCREEN_CALLS = {"click", "double_click", "right_click", "move_mouse", "type_into", "drag", "scroll_until", "ask",
                "check", "expect", "is_loaded", "read_text", "read_table", "wait_for", "type_text", "press", "hotkey",
                "scroll", "page_js", "network_response"}
SCOPE_CALLS = {"open_app", "focus_window", "open_url"}


def scope_problems(script: str) -> list[str]:
    """The agent sees one app at a time: a script must say which app before its first screen action."""
    try:
        tree = ast.parse(script)
    except SyntaxError:
        return []
    calls = sorted(
        ((n.lineno, n.col_offset, n.func.id) for n in ast.walk(tree)
         if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in SCREEN_CALLS | SCOPE_CALLS),
    )
    for line, _, name in calls:
        if name in SCOPE_CALLS:
            return []
        return [f'line {line}: {name}() runs before the script says which app it works in. The agent only sees one '
                f'app at a time: start with open_app("App name") (or focus_window(...), or open_url(...) for a web '
                f'page), and call it again whenever the task moves to another app.']
    return []
