"""Results: summaries, tables, showing them in the chat, and exporting."""
from __future__ import annotations

import csv
import io
import json
import re
import time

from ..config import config
from .context import current


def make_table(rows, columns: list | None = None) -> dict:
    """Build a table from a list of dicts (or lists, with `columns`). Pass it to show() or export()."""
    rows = list(rows or [])
    if rows and isinstance(rows[0], dict):
        cols = [str(c) for c in (columns or list(dict.fromkeys(k for r in rows for k in r)))]
        data = [[_cell(r.get(c, "")) for c in cols] for r in rows]
    else:
        cols = [str(c) for c in (columns or [f"col{i + 1}" for i in range(max((len(r) for r in rows), default=0))])]
        data = [[_cell(v) for v in (r if isinstance(r, (list, tuple)) else [r])] for r in rows]
    return {"kind": "table", "columns": cols, "rows": data}


def _cell(v):
    if isinstance(v, (int, float, str)) or v is None:
        return "" if v is None else v
    return str(v)


def _as_text(data) -> str:
    if data is None:
        return ""
    if isinstance(data, str):
        return data
    try:
        return json.dumps(data, default=str, indent=1)[:12000]
    except Exception:
        return str(data)[:12000]


def summarize(instruction: str, data=None) -> str:
    """Write a short Markdown summary. With `data` (rows, text, dicts) it summarizes that data;
    without it, it summarizes what's on screen plus results shown so far this run."""
    ctx = current()
    ctx.status(f"Summarizing: {instruction}")
    img = None
    if data is None:
        img = ctx.capture().image
        payload = _as_text([r.get("text") or r.get("rows") for r in ctx.results]) + "\nRecent actions:\n" + "\n".join(
            ctx.action_log[-20:]
        )
    else:
        payload = _as_text(data)
    text = ctx.models.vision.summarize(instruction, payload, img)
    ctx.push_metrics()
    return text


def show(result, title: str | None = None) -> None:
    """Show a result in the chat window: a string (Markdown), a table from make_table(), or rows (list of dicts)."""
    ctx = current()
    if isinstance(result, dict) and result.get("kind") == "table":
        item = dict(result)
    elif isinstance(result, list) and result and isinstance(result[0], (dict, list, tuple)):
        item = make_table(result)
    else:
        item = {"kind": "markdown", "text": _as_text(result)}
    item["title"] = title or ""
    item["id"] = f"r{len(ctx.results) + 1}"
    ctx.results.append(item)
    ctx.emit("result_ready", result=item)


def _rows_for_export(data) -> tuple[list[str], list[list]]:
    if isinstance(data, dict) and data.get("kind") == "table":
        return data["columns"], data["rows"]
    if isinstance(data, list):
        t = make_table(data)
        return t["columns"], t["rows"]
    return ["value"], [[_as_text(data)]]


def to_markdown(columns: list[str], rows: list[list]) -> str:
    esc = lambda v: str(v).replace("|", "\\|").replace("\n", " ")  # noqa: E731
    lines = ["| " + " | ".join(esc(c) for c in columns) + " |", "|" + "---|" * len(columns)]
    lines += ["| " + " | ".join(esc(v) for v in r) + " |" for r in rows]
    return "\n".join(lines)


def export_data(data, fmt: str = "csv", name: str | None = None) -> str:
    fmt = fmt.lower().strip(".")
    if fmt == "excel":
        fmt = "xlsx"
    if fmt == "markdown":
        fmt = "md"
    columns, rows = _rows_for_export(data)
    if fmt == "clipboard":
        import pyperclip

        buf = io.StringIO()
        csv.writer(buf, delimiter="\t").writerows([columns] + rows)
        pyperclip.copy(buf.getvalue() if not isinstance(data, str) else data)
        return "clipboard"
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", name or "export").strip("_")[:60] or "export"
    path = config.exports_dir / f"{safe}_{time.strftime('%Y%m%d_%H%M%S')}.{fmt}"
    if fmt == "csv":
        with open(path, "w", newline="", encoding="utf-8") as fh:
            csv.writer(fh).writerows([columns] + rows)
    elif fmt == "json":
        path.write_text(json.dumps([dict(zip(columns, r)) for r in rows], indent=2, default=str), encoding="utf-8")
    elif fmt == "md":
        body = data if isinstance(data, str) else to_markdown(columns, rows)
        path.write_text(body, encoding="utf-8")
    elif fmt == "xlsx":
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.append(columns)
        for r in rows:
            ws.append([str(v) if not isinstance(v, (int, float)) else v for v in r])
        wb.save(path)
    else:
        raise ValueError(f"Unknown export format {fmt!r}; use csv, xlsx, json, md or clipboard")
    return str(path)


def export(data, fmt: str = "csv", name: str | None = None) -> str:
    """Export rows/a table/text. fmt: "csv", "xlsx", "json", "md" or "clipboard". Returns the file path."""
    ctx = current()
    where = export_data(data, fmt, name)
    ctx.log(f"export({fmt}) -> {where}")
    ctx.emit("exported", path=where, fmt=fmt)
    return where
