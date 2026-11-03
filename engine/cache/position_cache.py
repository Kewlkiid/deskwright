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
from ..screen.fingerprint import hamming, patch_hash, screen_hash, sig_changed_pixels, sig_diff, signature
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
# Checks: the whole screen at 96x60, and under 1% of it changed counts as the same screen.
CHECK_SIZE = (96, 60)
CHECK_SAME = 57
CHECK_KEEP = 4


def check_sig(img: Image.Image) -> bytes:
    return img.convert("L").resize(CHECK_SIZE, Image.BILINEAR).tobytes()


def norm_check(condition: str) -> str:
    return " ".join(condition.lower().split())


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
LOOKS = {"blue", "grey", "gray", "white", "black", "red", "green", "orange", "yellow", "purple", "pink", "dark",
         "light", "small", "large", "big", "little", "round", "rounded", "circular", "square", "bold", "highlighted",
         "labeled", "labelled", "titled", "named"}
WHERE = re.compile(r"[,(]|\b(?:in|at|on|under|below|above|near|next to|inside|from|within|to the|beside|that|which|"
                   r"showing|with|labeled|labelled|containing|called|named)\b")
SIMILAR_TARGET = 0.6
SIMILAR_QUOTED = 0.3  # the same quoted name ("'=' equals button") already says which element: the rest is where


def _target_terms(target: str, app: str = "") -> tuple[set, set]:
    t = norm_target(target)
    head = WHERE.split(t, maxsplit=1)[0]
    quoted = re.findall(r"['\"‘“]([^'\"’”]+)['\"’”]", t)
    in_quotes = {w for q in quoted for w in re.findall(r"[a-z0-9]+", q)}
    app_words = set(re.findall(r"[a-z0-9]+", app.lower()))  # "calculator number button" is the app's button
    name = set(re.findall(r"[a-z0-9]+", head)) - FILLER - LOOKS - in_quotes - app_words
    name |= {"«" + q + "»" for q in quoted}
    return set(re.findall(r"[a-z0-9]+", t)) - FILLER - app_words, name


def similar_target(a: str, b: str, app: str = "") -> float:
    """How alike two descriptions are (0-1); 0 unless they name the same element (same name words, same quoted text)."""
    wa, na = _target_terms(a, app)
    wb, nb = _target_terms(b, app)
    if na != nb or not na:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def same_target(a: str, b: str, app: str = "") -> bool:
    quoted = any(n.startswith("«") for n in _target_terms(a, app)[1])
    return similar_target(a, b, app) >= (SIMILAR_QUOTED if quoted else SIMILAR_TARGET)


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
            app = window.split("|")[0]
            near = [(similar_target(target, r["target"], app), r) for r in
                    self.db.query("SELECT * FROM cache WHERE window = ? ORDER BY updated DESC LIMIT 300", (window,))]
            near.sort(key=lambda x: -x[0])
            rows = [r for s, r in near if s > 0 and same_target(target, r["target"], app)][:5]
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
        self.db.execute("DELETE FROM check_cache")

    # Checks ("the page is loaded", "search results are shown"): a condition the models said was true is true again
    # when the screen looks the same as it did then, so a rerun doesn't ask again. Only yes answers are kept.
    def check_lookup(self, window: str, condition: str, img: Image.Image) -> bool:
        sig = check_sig(img)
        for r in self.db.query("SELECT rowid, sig FROM check_cache WHERE window = ? AND condition = ?",
                               (window, norm_check(condition))):
            if sig_changed_pixels(sig, r["sig"]) <= CHECK_SAME:
                self.db.execute("UPDATE check_cache SET hits = hits + 1, updated = ? WHERE rowid = ?",
                                (time.time(), r["rowid"]))
                return True
        return False

    def check_put(self, window: str, condition: str, img: Image.Image):
        key = (window, norm_check(condition))
        self.db.execute("INSERT INTO check_cache (window, condition, sig, hits, updated) VALUES (?, ?, ?, 0, ?)",
                        (*key, check_sig(img), time.time()))
        # A few looks per condition (light and dark, a window moved): drop the oldest beyond that.
        self.db.execute("DELETE FROM check_cache WHERE window = ? AND condition = ? AND rowid NOT IN (SELECT rowid "
                        "FROM check_cache WHERE window = ? AND condition = ? ORDER BY updated DESC LIMIT ?)",
                        (*key, *key, CHECK_KEEP))

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
