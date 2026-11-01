"""Position cache: remembers where described elements were, so replays skip model calls.

Entry key: window/app + coarse screen fingerprint + element description.
Entry value: bounding box + click point + fingerprint of the pixels inside it, in the coordinates of the app's window
(screenshots are cropped to it), so moving the window keeps entries valid. A resized window reflows its layout, so
entries remember the window's size and a different size is a miss.
A hit is only trusted after a fresh crop of the cached box matches the stored fingerprint.
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
SCREEN_HASH_MAX_DIST = 20
# The window may differ by a couple of pixels (rounding of its bounds) and still be the same size.
FRAME_TOLERANCE = 4
# Strict: the pixels at the cached spot must look like the element we saw before.
PATCH_SIG_MAX_DIFF = 12.0
PATCH_HASH_MAX_DIST = 10


def norm_target(target: str) -> str:
    return re.sub(r"\s+", " ", target.strip().lower())


@dataclass
class CacheEntry:
    id: int
    box: Box
    expect: str | None
    hits: int
    point: tuple[float, float] | None = None  # where the element was clicked; the box can be looser than the element


class PositionCache:
    def __init__(self, db: DB):
        self.db = db

    def lookup(self, window: str, img: Image.Image, target: str) -> CacheEntry | None:
        rows = self.db.query(
            "SELECT * FROM cache WHERE window = ? AND target = ? ORDER BY updated DESC LIMIT 20",
            (window, norm_target(target)),
        )
        if not rows:
            return None
        current = screen_hash(img)
        rows.sort(key=lambda r: hamming(current, r["screen_hash"]))
        for r in rows:
            if r["frame"]:
                fw, fh = json.loads(r["frame"])
                if abs(fw - img.width) > FRAME_TOLERANCE or abs(fh - img.height) > FRAME_TOLERANCE:
                    continue  # the window was resized: its layout may have moved
            if hamming(current, r["screen_hash"]) > SCREEN_HASH_MAX_DIST:
                break
            box = json.loads(r["box"])
            fresh_sig = signature(img, box)
            if sig_diff(fresh_sig, r["patch_sig"]) > PATCH_SIG_MAX_DIFF:
                continue
            if hamming(patch_hash(img, box), r["patch_hash"]) > PATCH_HASH_MAX_DIST:
                continue
            self.db.execute("UPDATE cache SET hits = hits + 1, updated = ? WHERE id = ?", (time.time(), r["id"]))
            point = tuple(json.loads(r["point"])) if r["point"] else None
            return CacheEntry(id=r["id"], box=box, expect=r["expect"], hits=r["hits"] + 1, point=point)
        return None

    def put(self, window: str, img: Image.Image, target: str, box: Box, expect: str | None = None,
            point: tuple[float, float] | None = None):
        key = norm_target(target)
        sh = screen_hash(img)
        # Replace an entry for the same view instead of piling up duplicates.
        for r in self.db.query("SELECT id, screen_hash FROM cache WHERE window = ? AND target = ?", (window, key)):
            if hamming(sh, r["screen_hash"]) <= SCREEN_HASH_MAX_DIST:
                self.db.execute("DELETE FROM cache WHERE id = ?", (r["id"],))
        self.db.execute(
            "INSERT INTO cache (window, target, screen_hash, box, patch_hash, patch_sig, expect, point, frame, hits, "
            "updated) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)",
            (window, key, sh, json.dumps(box), patch_hash(img, box), signature(img, box), expect,
             json.dumps(list(point)) if point else None, json.dumps(list(img.size)), time.time()),
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
