"""Position cache: remembers where described elements were, so replays skip model calls.

Entry key: the app + element description (not the window title: Discord's changes with every channel); up to
MAX_VIEWS entries per window size for the same target in different views, ordered by screen similarity.
Entry value: bounding box + click point + fingerprint of the pixels inside it, in the coordinates of the app's window
(screenshots are cropped to it), so moving the window keeps entries valid. A resized window reflows its layout, so
entries remember the window's size and a different size is a miss.
A hit is only trusted after a fresh crop of the cached box matches the stored fingerprint. A found box can hold more
than the element (a loose box around a button takes in the rows beside it), so the element's core, the area around
the click point, has its own fingerprint: when only the surroundings changed, the core still matches. Fields whose
text changes are confirmed through Accessibility instead (sdk/actions.py).
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass

from PIL import Image

from ..screen.capture import Box
from ..screen.fingerprint import hamming, patch_hash, screen_hash, sig_diff, signature
from ..store.db import DB

# Loose: the screen may differ a little (typed text, a new row) and still be the same view.
SCREEN_HASH_MAX_DIST = 20  # "the same view" when replacing an entry
MAX_VIEWS = 4  # entries kept per app, target and window size
# The window may differ by a couple of pixels (rounding of its bounds) and still be the same size.
FRAME_TOLERANCE = 4
# Strict: the pixels at the cached spot must look like the element we saw before.
PATCH_SIG_MAX_DIFF = 12.0
PATCH_HASH_MAX_DIST = 10
CORE_SIG_MAX_DIFF = 10.0  # the core alone is small: a bit stricter


def core_box(box: Box, point: tuple[float, float] | None) -> Box:
    """The element itself: the part of the box around the click point (at most 28x12 px each way past the point,
    and never more than a third of the box's size), where a loose box's neighbours don't reach."""
    x1, y1, x2, y2 = box
    px, py = point or ((x1 + x2) / 2, (y1 + y2) / 2)
    dx = min(28.0, max(8.0, (x2 - x1) / 3))
    dy = min(12.0, max(6.0, (y2 - y1) / 3))
    return [max(x1, px - dx), max(y1, py - dy), min(x2, px + dx), min(y2, py + dy)]


def norm_target(target: str) -> str:
    return re.sub(r"\s+", " ", target.strip().lower())


# Each fresh plan words its targets a little differently ("search field at the top of the weather sidebar" vs "...of
# the Weather app sidebar"), so a near-identical description shares the entry. The element's own name (the words
# before where it is: "search field", "'support' text channel") must be the same; the pixel checks still decide.
FILLER = {"the", "a", "an", "of", "in", "on", "at", "to", "with", "and", "or", "that", "this", "its", "it", "for",
          "app", "very", "just", "by", "from"}
LOOKS = {"blue", "grey", "gray", "white", "black", "red", "green", "dark", "light", "small", "large", "big", "little",
         "round", "rounded", "circular", "bold", "highlighted"}
WHERE = re.compile(r"[,(]|\b(?:in|at|on|under|below|above|near|next to|inside|from|within|to the|beside|that|which|"
                   r"showing|with|labeled|labelled|containing|called|named)\b")
SIMILAR_TARGET = 0.7


def _target_terms(target: str) -> tuple[set, set]:
    t = norm_target(target)
    head = WHERE.split(t, maxsplit=1)[0]
    quoted = re.findall(r"['\"‘“]([^'\"’”]+)['\"’”]", t)
    name = (set(re.findall(r"[a-z0-9]+", head)) - FILLER - LOOKS) | {"«" + q + "»" for q in quoted}
    return set(re.findall(r"[a-z0-9]+", t)) - FILLER, name


def similar_target(a: str, b: str) -> float:
    """How alike two descriptions are (0-1); 0 unless they name the same element (same name words, same quoted text)."""
    wa, na = _target_terms(a)
    wb, nb = _target_terms(b)
    if na != nb or not na:
        return 0.0
    return len(wa & wb) / len(wa | wb)


@dataclass
class CacheEntry:
    id: int
    box: Box
    expect: str | None
    hits: int
    point: tuple[float, float] | None = None  # where the element was clicked; the box can be looser than the element
    how: str = "pixels"  # what confirmed it: "pixels" (the whole box), "core" (the element itself), "accessibility"


class PositionCache:
    def __init__(self, db: DB):
        self.db = db

    def entries(self, window: str, img: Image.Image, target: str) -> list[dict]:
        """Entries for this target made at this window size, the most similar screen first."""
        rows = self.db.query(
            "SELECT * FROM cache WHERE window = ? AND target = ? ORDER BY updated DESC LIMIT 20",
            (window, norm_target(target)),
        )
        if not rows:
            near = [(similar_target(target, r["target"]), r) for r in
                    self.db.query("SELECT * FROM cache WHERE window = ? ORDER BY updated DESC LIMIT 300", (window,))]
            rows = [r for s, r in sorted(near, key=lambda x: -x[0]) if s >= SIMILAR_TARGET][:5]
        current = screen_hash(img)
        rows.sort(key=lambda r: hamming(current, r["screen_hash"]))
        out = []
        for r in rows:
            if r["frame"]:
                fw, fh = json.loads(r["frame"])
                if abs(fw - img.width) > FRAME_TOLERANCE or abs(fh - img.height) > FRAME_TOLERANCE:
                    continue  # the window was resized: its layout may have moved
            out.append(dict(r))
        return out

    def lookup(self, window: str, img: Image.Image, target: str) -> CacheEntry | None:
        for r in self.entries(window, img, target):
            # The whole-screen fingerprint only orders the entries: a different channel or page changes most of the
            # screen while the element stays put. Whether the element is really there is the patch checks' job.
            box = json.loads(r["box"])
            whole = (sig_diff(signature(img, box), r["patch_sig"]) <= PATCH_SIG_MAX_DIFF
                     and hamming(patch_hash(img, box), r["patch_hash"]) <= PATCH_HASH_MAX_DIST)
            core = (not whole and r.get("core_sig") and r.get("core_box")
                    and sig_diff(signature(img, json.loads(r["core_box"])), r["core_sig"]) <= CORE_SIG_MAX_DIFF)
            if whole or core:
                return self.hit(r, img, "pixels" if whole else "core")
        return None

    def hit(self, r: dict, img: Image.Image, how: str) -> CacheEntry:
        """Count a hit on entry `r`. Confirmed by less than its whole box: its fingerprint is updated to this screen,
        so the same view matches outright next time."""
        box = json.loads(r["box"])
        point = tuple(json.loads(r["point"])) if r["point"] else None
        if how == "pixels":
            self.db.execute("UPDATE cache SET hits = hits + 1, updated = ? WHERE id = ?", (time.time(), r["id"]))
        else:
            cb = core_box(box, point)
            self.db.execute(
                "UPDATE cache SET hits = hits + 1, updated = ?, patch_hash = ?, patch_sig = ?, core_box = ?, "
                "core_sig = ?, screen_hash = ? WHERE id = ?",
                (time.time(), patch_hash(img, box), signature(img, box), json.dumps(cb), signature(img, cb),
                 screen_hash(img), r["id"]),
            )
        return CacheEntry(id=r["id"], box=box, expect=r["expect"], hits=r["hits"] + 1, point=point, how=how)

    def put(self, window: str, img: Image.Image, target: str, box: Box, expect: str | None = None,
            point: tuple[float, float] | None = None):
        key = norm_target(target)
        sh = screen_hash(img)
        # Replace an entry for the same view (same window size, similar screen) instead of piling up duplicates.
        # A different window size is a different layout: its entry is kept alongside, so going back to that size
        # still hits.
        same_size = []
        for r in self.db.query("SELECT id, screen_hash, frame, updated FROM cache WHERE window = ? AND target = ?",
                               (window, key)):
            if r["frame"]:
                fw, fh = json.loads(r["frame"])
                if abs(fw - img.width) > FRAME_TOLERANCE or abs(fh - img.height) > FRAME_TOLERANCE:
                    continue
            if hamming(sh, r["screen_hash"]) <= SCREEN_HASH_MAX_DIST:
                self.db.execute("DELETE FROM cache WHERE id = ?", (r["id"],))
            else:
                same_size.append(r)
        # The same target can sit in different places in different views (two dialogs): keep a few, newest first.
        for r in sorted(same_size, key=lambda r: r["updated"], reverse=True)[MAX_VIEWS - 1:]:
            self.db.execute("DELETE FROM cache WHERE id = ?", (r["id"],))
        cb = core_box(box, point)
        self.db.execute(
            "INSERT INTO cache (window, target, screen_hash, box, patch_hash, patch_sig, expect, point, frame, "
            "core_box, core_sig, hits, updated) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)",
            (window, key, sh, json.dumps(box), patch_hash(img, box), signature(img, box), expect,
             json.dumps(list(point)) if point else None, json.dumps(list(img.size)), json.dumps(cb),
             signature(img, cb), time.time()),
        )

    def invalidate(self, window: str, target: str):
        self.db.execute("DELETE FROM cache WHERE window = ? AND target = ?", (window, norm_target(target)))

    # Running averages of what a miss costs, used to report time/cost saved by hits.
    def record_miss(self, seconds: float, cost: float):
        self.db.execute(
            "UPDATE cache_stats SET miss_count = miss_count + 1, miss_seconds = miss_seconds + ?, "
            "miss_cost = miss_cost + ? WHERE id = 1",
            (seconds, cost),
        )

    def avg_miss(self) -> tuple[float, float]:
        row = self.db.query("SELECT * FROM cache_stats WHERE id = 1")[0]
        n = row["miss_count"] or 0
        if not n:
            return 2.5, 0.003  # rough defaults before any data
        return row["miss_seconds"] / n, row["miss_cost"] / n

    def stats(self) -> dict:
        row = self.db.query("SELECT COUNT(*) AS entries, COALESCE(SUM(hits), 0) AS hits FROM cache")[0]
        b = self.db.query("SELECT COUNT(*) AS entries, COALESCE(SUM(hits), 0) AS hits FROM browser_cache")[0]
        return {"entries": row["entries"] + b["entries"], "hits": row["hits"] + b["hits"]}

    def clear(self):
        self.db.execute("DELETE FROM cache")
        self.db.execute("DELETE FROM browser_cache")

    # Browser steps: page + description -> CSS selector and the element's name, re-checked in the live DOM.
    def browser_lookup(self, page: str, target: str) -> dict | None:
        rows = self.db.query("SELECT * FROM browser_cache WHERE page = ? AND target = ?", (page, norm_target(target)))
        return dict(rows[0]) if rows else None

    def browser_put(self, page: str, target: str, selector: str, name: str | None):
        self.db.execute(
            "INSERT OR REPLACE INTO browser_cache (page, target, selector, name, hits, updated) VALUES (?, ?, ?, ?, 0, ?)",
            (page, norm_target(target), selector, name or "", time.time()),
        )

    def browser_hit(self, page: str, target: str):
        self.db.execute("UPDATE browser_cache SET hits = hits + 1, updated = ? WHERE page = ? AND target = ?",
                        (time.time(), page, norm_target(target)))

    def browser_invalidate(self, page: str, target: str):
        self.db.execute("DELETE FROM browser_cache WHERE page = ? AND target = ?", (page, norm_target(target)))
