"""One run on the screen at a time, across processes.

A task drives the real mouse, keyboard and browser, so two runs at once (the app's own engine and a CLI run started
by another program, or two CLI runs) would fight over them. Every run holds an OS file lock on DATA_DIR/run.lock;
the lock is released by the OS if the process dies. A small JSON file next to it says who holds it.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


class ScreenBusy(Exception):
    """Another run holds the screen."""

    def __init__(self, holder: dict | None):
        self.holder = holder or {}
        who = self.holder.get("task") or "another task"
        run = f" (run {self.holder['run_id']})" if self.holder.get("run_id") else ""
        super().__init__(f"another task is running: {who}{run}")


class ScreenLock:
    def __init__(self, data_dir: Path | str):
        self.path = Path(data_dir) / "run.lock"
        self.info_path = Path(data_dir) / "run.lock.json"
        self._fh = None

    def _try(self) -> bool:
        fh = open(self.path, "a+")
        try:
            if sys.platform == "win32":
                import msvcrt

                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            fh.close()
            return False
        self._fh = fh
        return True

    def acquire(self, task: str, wait: float = 0.0) -> None:
        """Take the screen, waiting up to `wait` seconds. Raises ScreenBusy if it stays taken."""
        end = time.time() + max(0.0, wait)
        while not self._try():
            if time.time() >= end:
                raise ScreenBusy(self.holder())
            time.sleep(0.25)
        self._write({"task": task, "pid": os.getpid(), "since": time.time()})

    def note_run(self, run_id: int) -> None:
        info = self.holder() or {}
        info["run_id"] = run_id
        self._write(info)

    def release(self) -> None:
        if not self._fh:
            return
        try:
            self.info_path.unlink(missing_ok=True)
        except OSError:
            pass
        try:
            if sys.platform == "win32":
                import msvcrt

                self._fh.seek(0)
                msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
        finally:
            self._fh.close()
            self._fh = None

    def holder(self) -> dict | None:
        try:
            return json.loads(self.info_path.read_text())
        except (OSError, ValueError):
            return None

    def _write(self, info: dict) -> None:
        try:
            self.info_path.write_text(json.dumps(info))
        except OSError:
            pass
