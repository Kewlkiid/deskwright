"""Progress records, so a repaired script resumes instead of redoing finished work."""
from __future__ import annotations

import hashlib
import json

from .context import current


def item_key(item) -> str:
    return hashlib.sha1(json.dumps(item, sort_keys=True, default=str).encode()).hexdigest()[:16]


class Progress:
    """progress.pending(items) yields only items not yet marked done; progress.done(item) marks one finished;
    progress.reached("stage") tells whether checkpoint("stage") already ran this run."""

    def __init__(self, run_id: int, db):
        self._run_id = run_id
        self._db = db
        self._done = {r["key"] for r in db.progress_keys(run_id, "item")} if db else set()
        self._checkpoints = [r["key"] for r in db.progress_keys(run_id, "checkpoint")] if db else []
        self._labels: list[str] = []

    def pending(self, items):
        """Iterate over the items that are not done yet."""
        items = list(items or [])
        left = [i for i in items if item_key(i) not in self._done]
        current().emit("progress", done=len(items) - len(left), total=len(items))
        for item in left:
            if item_key(item) in self._done:
                continue
            yield item

    def done(self, item) -> None:
        """Mark an item as finished."""
        k = item_key(item)
        if k in self._done:
            return
        self._done.add(k)
        label = json.dumps(item, default=str)[:80]
        self._labels.append(label)
        if self._db:
            self._db.mark_progress(self._run_id, "item", k, label)
        ctx = current()
        ctx.log(f"done: {label}")
        ctx.emit("progress_item", item=label, done=len(self._done))

    def reached(self, name: str) -> bool:
        """True if checkpoint(name) already ran during this run."""
        return name in self._checkpoints

    def checkpoint(self, name: str) -> None:
        if name not in self._checkpoints:
            self._checkpoints.append(name)
            if self._db:
                self._db.mark_progress(self._run_id, "checkpoint", name)
        current().emit("checkpoint", name=name)

    def log(self) -> dict:
        return {"items_done": len(self._done), "recent_items_done": self._labels[-10:], "checkpoints": self._checkpoints}


def checkpoint(name: str) -> None:
    """Mark a finished stage of the task, e.g. checkpoint("data collected")."""
    current().progress.checkpoint(name)
