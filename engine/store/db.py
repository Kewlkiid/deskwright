"""SQLite storage: saved tasks and their versions, run history, progress records, position cache."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    description TEXT DEFAULT '',
    script TEXT NOT NULL,
    source TEXT DEFAULT 'chat',
    created REAL,
    updated REAL
);
CREATE TABLE IF NOT EXISTS task_versions (
    id INTEGER PRIMARY KEY,
    task_id INTEGER NOT NULL,
    script TEXT NOT NULL,
    note TEXT DEFAULT '',
    created REAL
);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY,
    task_id INTEGER,
    task_text TEXT,
    status TEXT,
    started REAL,
    ended REAL,
    metrics TEXT
);
CREATE TABLE IF NOT EXISTS progress (
    run_id INTEGER,
    kind TEXT,
    key TEXT,
    payload TEXT,
    ts REAL,
    PRIMARY KEY (run_id, kind, key)
);
CREATE TABLE IF NOT EXISTS cache (
    id INTEGER PRIMARY KEY,
    window TEXT,
    target TEXT,
    screen_hash TEXT,
    box TEXT,
    patch_hash TEXT,
    patch_sig BLOB,
    expect TEXT,
    point TEXT,
    frame TEXT,
    hits INTEGER DEFAULT 0,
    updated REAL
);
CREATE INDEX IF NOT EXISTS cache_lookup ON cache(window, target);
CREATE TABLE IF NOT EXISTS detours (
    id INTEGER PRIMARY KEY,
    task_id INTEGER NOT NULL,
    step TEXT,
    source TEXT,
    when_text TEXT,
    screen TEXT,
    window TEXT,
    recover TEXT,
    uses INTEGER DEFAULT 0,
    created REAL
);
CREATE TABLE IF NOT EXISTS browser_cache (
    page TEXT,
    target TEXT,
    selector TEXT,
    name TEXT,
    hits INTEGER DEFAULT 0,
    updated REAL,
    PRIMARY KEY (page, target)
);
CREATE TABLE IF NOT EXISTS cache_stats (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    miss_count INTEGER DEFAULT 0,
    miss_seconds REAL DEFAULT 0,
    miss_cost REAL DEFAULT 0
);
"""


class DB:
    def __init__(self, path: Path | str):
        self.path = str(path)
        self._lock = threading.RLock()
        # Several processes share this file (the app's engine, CLI runs started by other programs): wait for a
        # lock instead of failing, and use WAL so readers never block the writer.
        self.conn = sqlite3.connect(self.path, check_same_thread=False, timeout=30)
        self.conn.row_factory = sqlite3.Row
        with self._lock:
            self.conn.execute("PRAGMA busy_timeout = 30000")
            try:
                self.conn.execute("PRAGMA journal_mode = WAL")
            except sqlite3.OperationalError:
                pass  # e.g. a read-only location; the default journal still works
            self.conn.executescript(SCHEMA)
            # Databases created before the cache remembered click points.
            cols = {r[1] for r in self.conn.execute("PRAGMA table_info(cache)")}
            if "point" not in cols:
                self.conn.execute("ALTER TABLE cache ADD COLUMN point TEXT")
            if "frame" not in cols:
                self.conn.execute("ALTER TABLE cache ADD COLUMN frame TEXT")
            # Which outside request (e.g. another program's task_request) a task was made for.
            task_cols = {r[1] for r in self.conn.execute("PRAGMA table_info(tasks)")}
            if "request_id" not in task_cols:
                self.conn.execute("ALTER TABLE tasks ADD COLUMN request_id TEXT")
            self.conn.execute("INSERT OR IGNORE INTO cache_stats (id) VALUES (1)")
            self.conn.commit()

    def execute(self, sql: str, params: tuple | list = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self.conn.execute(sql, params)
            self.conn.commit()
            return cur

    def query(self, sql: str, params: tuple | list = ()) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self.conn.execute(sql, params).fetchall()]

    # Tasks -----------------------------------------------------------------
    def save_task(self, name: str, script: str, description: str = "", source: str = "chat", note: str = "",
                  request_id: str | None = None) -> int:
        now = time.time()
        existing = self.query("SELECT id FROM tasks WHERE name = ?", (name,))
        if existing:
            task_id = existing[0]["id"]
            self.execute(
                "UPDATE tasks SET script = ?, description = COALESCE(NULLIF(?, ''), description), updated = ? WHERE id = ?",
                (script, description, now, task_id),
            )
        else:
            task_id = self.execute(
                "INSERT INTO tasks (name, description, script, source, created, updated) VALUES (?, ?, ?, ?, ?, ?)",
                (name, description, script, source, now, now),
            ).lastrowid
        self.execute(
            "INSERT INTO task_versions (task_id, script, note, created) VALUES (?, ?, ?, ?)",
            (task_id, script, note or ("created" if not existing else "updated"), now),
        )
        if request_id:
            self.execute("UPDATE tasks SET request_id = ? WHERE id = ?", (request_id, task_id))
        return task_id

    def rename_task(self, task_id: int, new_name: str):
        self.execute("UPDATE tasks SET name = ?, updated = ? WHERE id = ?", (new_name, time.time(), task_id))

    def task_stats(self, task_id: int) -> dict:
        """Run history in brief: how often it ran and succeeded, the last run, when it last healed itself."""
        runs = self.query("SELECT status, started, ended FROM runs WHERE task_id = ? AND status != 'running' ORDER BY id",
                          (task_id,))
        ok = sum(1 for r in runs if r["status"] == "succeeded")
        healed = self.query("SELECT MAX(created) AS t FROM task_versions WHERE task_id = ? AND note LIKE 'self-healed%'",
                            (task_id,))[0]["t"]
        versions = self.query("SELECT COUNT(*) AS n FROM task_versions WHERE task_id = ?", (task_id,))[0]["n"]
        return {"runs": len(runs), "success_rate": round(ok / len(runs), 3) if runs else None,
                "last_run": runs[-1] if runs else None, "last_healed": healed, "versions": versions}

    def get_task(self, task_id: int | None = None, name: str | None = None) -> dict | None:
        if task_id is not None:
            rows = self.query("SELECT * FROM tasks WHERE id = ?", (task_id,))
        else:
            rows = self.query("SELECT * FROM tasks WHERE lower(name) = lower(?)", (name or "",))
        return rows[0] if rows else None

    def list_tasks(self) -> list[dict]:
        tasks = self.query("SELECT * FROM tasks ORDER BY updated DESC")
        for t in tasks:
            t["runs"] = self.task_runs(t["id"])
            t["versions"] = self.query(
                "SELECT id, note, created FROM task_versions WHERE task_id = ? ORDER BY id", (t["id"],)
            )
            t["detours"] = self.query("SELECT COUNT(*) AS n FROM detours WHERE task_id = ?", (t["id"],))[0]["n"]
        return tasks

    def delete_task(self, task_id: int):
        self.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        self.execute("DELETE FROM task_versions WHERE task_id = ?", (task_id,))
        self.execute("DELETE FROM detours WHERE task_id = ?", (task_id,))

    # Runs ------------------------------------------------------------------
    def start_run(self, task_text: str, task_id: int | None) -> int:
        return self.execute(
            "INSERT INTO runs (task_id, task_text, status, started) VALUES (?, ?, 'running', ?)",
            (task_id, task_text, time.time()),
        ).lastrowid

    def finish_run(self, run_id: int, status: str, metrics: dict):
        self.execute(
            "UPDATE runs SET status = ?, ended = ?, metrics = ? WHERE id = ?",
            (status, time.time(), json.dumps(metrics), run_id),
        )

    # Learned detours (runner/detours.py) ---------------------------------------
    def task_detours(self, task_id: int) -> list[dict]:
        return self.query("SELECT * FROM detours WHERE task_id = ? ORDER BY id", (task_id,))

    def add_detour(self, task_id: int, d: dict) -> int:
        # The same way back for the same step and wrong state is one detour, not many.
        for r in self.query("SELECT id, screen FROM detours WHERE task_id = ? AND step = ? AND recover = ?",
                            (task_id, d["step"], d["recover"])):
            if r["screen"] == d["screen"]:
                return r["id"]
        cur = self.execute(
            "INSERT INTO detours (task_id, step, source, when_text, screen, window, recover, uses, created) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)",
            (task_id, d["step"], d.get("source", ""), d["when"], d["screen"], d.get("window", ""), d["recover"], time.time()),
        )
        return cur.lastrowid

    def detour_used(self, detour_id: int):
        self.execute("UPDATE detours SET uses = uses + 1 WHERE id = ?", (detour_id,))

    def task_runs(self, task_id: int) -> list[dict]:
        rows = self.query("SELECT * FROM runs WHERE task_id = ? ORDER BY id", (task_id,))
        for r in rows:
            r["metrics"] = json.loads(r["metrics"]) if r.get("metrics") else {}
        return rows

    def all_runs_summary(self) -> dict:
        rows = self.query("SELECT status, metrics FROM runs WHERE status != 'running'")
        total = len(rows)
        ok = sum(1 for r in rows if r["status"] == "succeeded")
        ms = [json.loads(r["metrics"]) for r in rows if r.get("metrics")]
        fixes = sum(m.get("fixes", 0) for m in ms)
        fixes_ok = sum(m.get("fixes_succeeded", 0) for m in ms)
        return {
            "runs": total,
            "success_rate": round(ok / total, 3) if total else 0,
            "fix_success_rate": round(fixes_ok / fixes, 3) if fixes else 0,
        }

    # Progress --------------------------------------------------------------
    def mark_progress(self, run_id: int, kind: str, key: str, payload: str = ""):
        self.execute(
            "INSERT OR REPLACE INTO progress (run_id, kind, key, payload, ts) VALUES (?, ?, ?, ?, ?)",
            (run_id, kind, key, payload, time.time()),
        )

    def progress_keys(self, run_id: int, kind: str) -> list[dict]:
        return self.query(
            "SELECT key, payload FROM progress WHERE run_id = ? AND kind = ? ORDER BY ts", (run_id, kind)
        )
