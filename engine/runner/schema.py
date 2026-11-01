"""Task script schema header: what a task takes and what it returns.

Every task script starts with two plain literals the planner writes:

    INPUTS  = {"app_name": "str: name of the app", "platform": "ios|android: target platform"}
    OUTPUTS = {"app_id": "str: ID of the created app", "ad_unit_ids": "list[str]: created ad unit IDs"}

Each value is "type: description". Types: str, int, float, bool, list[...], dict, or choices like "ios|android".
The header is read with `ast` only; a script is never executed to learn its schema.
"""
from __future__ import annotations

import ast
import json
import re

HEADER_NAMES = ("INPUTS", "OUTPUTS")
SIMPLE_TYPES = {"str", "int", "float", "bool", "dict", "list"}


def parse_header(script: str) -> dict:
    """{"inputs": {...}, "outputs": {...}, "problems": [...]}. Missing or malformed parts are reported, not raised."""
    out = {"inputs": {}, "outputs": {}, "problems": []}
    try:
        tree = ast.parse(script or "")
    except SyntaxError as e:
        out["problems"].append(f"the script doesn't parse: {e.msg} (line {e.lineno})")
        return out
    seen: dict[str, int] = {}
    for stmt in tree.body:
        if not (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name)
                and stmt.targets[0].id in HEADER_NAMES):
            continue
        name = stmt.targets[0].id
        if name in seen:
            out["problems"].append(f"{name} is defined twice (lines {seen[name]} and {stmt.lineno})")
            continue
        seen[name] = stmt.lineno
        try:
            value = ast.literal_eval(stmt.value)
        except (ValueError, SyntaxError):
            out["problems"].append(f"{name} must be a plain dict literal (line {stmt.lineno})")
            continue
        if not isinstance(value, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in value.items()):
            out["problems"].append(f'{name} must map names to "type: description" strings (line {stmt.lineno})')
            continue
        bad = [k for k in value if not k.isidentifier()]
        if bad:
            out["problems"].append(f"{name} names must be identifiers: {', '.join(bad)}")
            continue
        out[name.lower()] = value
    for name in HEADER_NAMES:
        if name not in seen:
            out["problems"].append(f"missing {name} = {{...}} at the top of the script (use {{}} when there are none)")
    return out


def header_problems(script: str) -> list[str]:
    return parse_header(script)["problems"]


def schema_of(script: str) -> tuple[dict, dict]:
    h = parse_header(script)
    return h["inputs"], h["outputs"]


def header_source(script: str) -> str:
    """The header's own source lines (INPUTS and OUTPUTS assignments), exactly as written."""
    try:
        tree = ast.parse(script)
    except SyntaxError:
        return ""
    lines = script.splitlines()
    parts = []
    for stmt in tree.body:
        if (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name)
                and stmt.targets[0].id in HEADER_NAMES):
            parts.append("\n".join(lines[stmt.lineno - 1 : (stmt.end_lineno or stmt.lineno)]))
    return "\n".join(parts)


def with_header(script: str, header: str) -> str:
    """`script` with its INPUTS/OUTPUTS replaced by `header` (placed at the top)."""
    try:
        tree = ast.parse(script)
    except SyntaxError:
        return script
    lines = script.splitlines()
    drop: set[int] = set()
    for stmt in tree.body:
        if (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name)
                and stmt.targets[0].id in HEADER_NAMES):
            drop.update(range(stmt.lineno - 1, stmt.end_lineno or stmt.lineno))
    body = [line for i, line in enumerate(lines) if i not in drop]
    while body and not body[0].strip():
        body.pop(0)
    return header.rstrip() + "\n\n" + "\n".join(body)


def same_schema(a: str, b: str) -> bool:
    return schema_of(a) == schema_of(b) and not header_problems(b)


def split_desc(desc: str) -> tuple[str, str]:
    """ "str: name of the app" -> ("str", "name of the app"). No type prefix means str."""
    m = re.match(r"\s*([A-Za-z_][\w\[\], |]*|[\w-]+(?:\|[\w-]+)+)\s*:\s*(.*)$", desc or "", re.S)
    if not m:
        return "str", (desc or "").strip()
    return m.group(1).strip(), m.group(2).strip()


def coerce(value, desc: str):
    """Convert a passed-in value (often a string from the command line) to the input's declared type."""
    typ, _ = split_desc(desc)
    base = typ.split("[", 1)[0].strip()
    if "|" in typ and base not in SIMPLE_TYPES:
        choices = [c.strip() for c in typ.split("|")]
        if str(value) not in choices:
            raise ValueError(f"must be one of {', '.join(choices)} (got {value!r})")
        return str(value)
    if base == "str":
        return value if isinstance(value, str) else json.dumps(value) if isinstance(value, (list, dict)) else str(value)
    if base == "int":
        return int(value)
    if base == "float":
        return float(value)
    if base == "bool":
        if isinstance(value, bool):
            return value
        if str(value).strip().lower() in ("1", "true", "yes", "y", "on"):
            return True
        if str(value).strip().lower() in ("0", "false", "no", "n", "off"):
            return False
        raise ValueError(f"must be true or false (got {value!r})")
    if base in ("list", "dict"):
        if isinstance(value, (list, dict)):
            return value
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            if base == "list":
                return [v.strip() for v in str(value).split(",") if v.strip()]  # a,b,c from the command line
            raise ValueError(f"must be JSON for a {base} (got {value!r})")
        return parsed
    return value
