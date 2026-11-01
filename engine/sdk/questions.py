"""Screen questions: ask, check, expect, is_loaded, read_text, read_table.

In Chrome with the agent extension in front, check/expect first judge from the page's text (and recent network
calls), read_text reads the element's DOM text and read_table reads the table from the DOM; the screenshot path
is the fallback.
"""
from __future__ import annotations

import json
import re

from ..screen import capture as cap
from ..screen import input as inp
from ..screen.fingerprint import frame_diff, screen_hash
from .actions import browser_find, browser_for, find, settle_previous
from .context import ACTION_LOCK, RunContext, current
from .errors import ElementNotFoundError, ExpectationFailedError
from .raw import run_input


class Row(dict):
    """A table row. Column lookup is forgiving: row["name"] finds "Name" or "Customer Name"."""

    def __missing__(self, key):
        want = _key(key)
        for k in self:
            if _key(k) == want:
                return dict.__getitem__(self, k)
        for k in self:
            if want and want in _key(k):
                return dict.__getitem__(self, k)
        raise KeyError(key)


def _key(k) -> str:
    return re.sub(r"[^a-z0-9]", "", str(k).lower())


def _prev(ctx: RunContext) -> dict | None:
    return ctx.pending.as_prompt() if ctx.pending else None


def _check(ctx: RunContext, condition: str, shot: cap.Shot | None = None) -> dict:
    shot = shot or ctx.capture()
    key = (screen_hash(shot.image), condition.strip().lower())
    if ctx.pending is None and key in ctx.check_cache:
        ctx.metrics.record_cache(True, saved_calls=1)
        return ctx.check_cache[key]
    b = browser_for(ctx)
    if b:
        settle_previous(ctx, shot, b)
        ctx.status(f"Checking: {condition}")
        r = b.check(ctx, condition)
        if r is not None:
            ctx.check_cache[key] = r
            return r
    ctx.status(f"Checking: {condition}")
    r = ctx.models.vision.check(shot.image, condition, _prev(ctx))
    ctx.resolve_pending(shot, r.get("prev_expect_met"), r.get("observation", ""))
    ctx.check_cache[key] = r
    return r


def ask(question: str) -> str:
    """Ask a question about what is on the screen right now; returns the answer as text."""
    ctx = current()
    with ACTION_LOCK:
        shot = ctx.capture()
        ctx.status(f"Asking: {question}")
        r = ctx.models.vision.ask(shot.image, question, _prev(ctx))
        ctx.resolve_pending(shot, r.get("prev_expect_met"), r.get("observation", ""))
        ctx.push_metrics()
        return r["answer"]


def check(condition: str) -> bool:
    """Return True if the condition is visibly true on screen (e.g. "a Save dialog is open").
    Cached per screen fingerprint, so repeated checks of an unchanged screen are free."""
    ctx = current()
    with ACTION_LOCK:
        r = _check(ctx, condition)
        ctx.push_metrics()
        return bool(r["result"])


def expect(condition: str) -> None:
    """Raise ExpectationFailedError unless the condition is visibly true on screen."""
    ctx = current()
    with ACTION_LOCK:
        r = _check(ctx, condition)
        if not r["result"]:
            ctx.emit("expect_failed", line=ctx.current_line, segment=ctx.segment, expect=condition,
                     observation=r.get("reason", ""))
            raise ExpectationFailedError(
                f'Expected "{condition}", but: {r.get("reason") or "it is not visible"}',
                screenshot=ctx.last_shot.image if ctx.last_shot else None,
                detail={"expect": condition, "observation": r.get("reason", "")},
            )
        ctx.emit("expect_met", line=ctx.current_line, segment=ctx.segment, expect=condition)


def is_loaded() -> bool:
    """True when the frontmost app/page looks fully loaded (no spinners, progress bars or blank placeholders)."""
    return check("the app or page in front has finished loading: no spinners, progress bars or blank placeholder areas")


def _region(ctx: RunContext, target: str | None, verb: str) -> tuple[cap.Shot, list]:
    if not target or target.strip().lower() in ("screen", "the screen", "whole screen", "full screen"):
        shot = ctx.capture()
        ctx.resolve_pending(shot)
        return shot, [0, 0, shot.size[0], shot.size[1]]
    f = find(ctx, target, verb)
    return f.shot, cap.expand_box(f.box, f.shot.size, pad=10)


def _browser_read_text(ctx: RunContext, target: str | None) -> str | None:
    b = browser_for(ctx)
    if not b:
        return None
    if not target or target.strip().lower() in ("screen", "the screen", "whole screen", "full screen", "page", "the page"):
        settle_previous(ctx, ctx.capture(), b)
        return b.page("page_text", max=20000).get("text", "")
    found = browser_find(ctx, b, target, "read")
    if found is None:
        return None
    value = b.read(found[0]).get("value")
    return "" if value is None else str(value)


def read_text(target: str | None = None) -> str:
    """Read the text inside the described element (zoomed crop), or the whole screen when target is None.
    In Chrome the text comes straight from the page."""
    ctx = current()
    with ACTION_LOCK:
        text = _browser_read_text(ctx, target)
        if text is not None:
            ctx.log(f"read_text({target!r}) -> {len(text)} chars from the page DOM")
            ctx.push_metrics()
            return text
        shot, region = _region(ctx, target, "read")
        ctx.status(f"Reading: {target or 'screen'}")
        text = ctx.models.vision.read_text(cap.crop(shot.image, region))
        ctx.log(f"read_text({target!r}) -> {len(text)} chars")
        ctx.push_metrics()
        return text


def _num(v) -> float | None:
    s = re.sub(r"[,\s$€£%]", "", str(v))
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    try:
        return float(s)
    except ValueError:
        return None


def _numeric_columns(columns: list[str], rows: list[list]) -> list[str]:
    out = []
    for i, c in enumerate(columns):
        vals = [r[i] for r in rows if i < len(r) and str(r[i]).strip()]
        if vals and sum(_num(v) is not None for v in vals) / len(vals) >= 0.6:
            out.append(c)
    return out


def _pick(cols: list[str], row: list, want) -> str:
    """Value of column `want` in a DOM row, matching the header forgivingly (see Row)."""
    try:
        return Row({c: (row[i] if i < len(row) else "") for i, c in enumerate(cols)})[want]
    except KeyError:
        return ""


def read_table(target: str, columns: list | None = None, max_pages: int = 8) -> list:
    """Read the described table into a list of rows (dicts keyed by column name).
    Scrolls through long tables, captures in chunks, merges and de-duplicates rows, and re-reads
    numeric columns from a zoomed crop to double-check them. In Chrome the table is read from the page's DOM
    (all rows, no scrolling)."""
    ctx = current()
    with ACTION_LOCK:
        b = browser_for(ctx)
        if b:
            settle_previous(ctx, ctx.capture(), b)
            got = b.read_table(ctx, target, [str(c) for c in columns] if columns else None)
            if got is not None:
                cols, rows = got
                if columns:
                    # Keep the caller's column names; Row lookup maps them onto the page's headers.
                    out = [Row({str(c): _pick(cols, r, c) for c in columns}) for r in rows]
                    cols = [str(c) for c in columns]
                else:
                    out = [Row({c: (r[i] if i < len(r) else "") for i, c in enumerate(cols)}) for r in rows]
                ctx.log(f"read_table({target!r}) -> {len(out)} rows from the page DOM, columns {cols}")
                ctx.emit("table_read", target=target, columns=cols, count=len(out), line=ctx.current_line,
                         segment=ctx.segment)
                ctx.push_metrics()
                return out
        shot, region = _region(ctx, target, "read")
        cols: list[str] = [str(c) for c in columns] if columns else []
        seen: set[str] = set()
        out: list[Row] = []
        for page in range(max_pages):
            ctx.check_stop()
            ctx.status(f"Reading table: {target} (part {page + 1})")
            crop = cap.crop(shot.image, region)
            part = ctx.models.vision.read_table(crop, target, cols or None)
            if not cols:
                cols = part["columns"]
            rows = [list(r) if isinstance(r, (list, tuple)) else list(r.values()) for r in part["rows"]]
            num_cols = _numeric_columns(cols, rows)
            if num_cols and rows:
                zoomed = ctx.models.vision.reread_columns(crop, num_cols)
                if len(zoomed) == len(rows):
                    for r, z in zip(rows, zoomed):
                        for c in num_cols:
                            i = cols.index(c)
                            try:
                                zv = Row(z)[c]
                            except KeyError:
                                zv = None
                            if zv is not None and i < len(r) and _num(zv) != _num(r[i]):
                                ctx.log(f"read_table: corrected {c} {r[i]!r} -> {zv!r} after zoomed re-read")
                                r[i] = zv
            new = 0
            for r in rows:
                k = json.dumps([str(v).strip() for v in r])
                if k in seen:
                    continue
                seen.add(k)
                out.append(Row({c: (r[i] if i < len(r) else "") for i, c in enumerate(cols)}))
                new += 1
            if new == 0 and page > 0:
                break
            # Scroll inside the table and see whether the content moved.
            cx, cy = shot.to_logical(*cap.box_center(region))
            before = crop
            run_input(inp.scroll, -5, cx, cy)
            ctx.settle(1.0)
            shot = ctx.capture()
            if frame_diff(before, cap.crop(shot.image, region)) < 0.5:
                break
        if not out and not cols:
            raise ElementNotFoundError(f'Could not read any rows from "{target}"', detail={"target": target})
        ctx.log(f"read_table({target!r}) -> {len(out)} rows, columns {cols}")
        ctx.emit("table_read", target=target, columns=cols, count=len(out), line=ctx.current_line, segment=ctx.segment)
        ctx.push_metrics()
        return out
