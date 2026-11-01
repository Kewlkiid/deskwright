"""Teach-mode recording: screen frames plus a pynput log of every click and keystroke.

pynput callbacks must return fast (macOS disables slow event taps), so they only enqueue raw
events; a worker thread adds the window title and the screenshot taken at the click.
"""
from __future__ import annotations

import json
import queue
import threading
import time
from pathlib import Path

from ..screen import capture as cap
from ..screen.windows import window_key

FRAME_INTERVAL = 0.4  # ~2.5 fps keyframes


class Recorder:
    def __init__(self, out_dir: Path, exclude=lambda x, y: False):
        self.dir = out_dir
        self.exclude = exclude  # (x, y) logical -> True if inside the agent's own window
        self.events: list[dict] = []
        self.frames: list[tuple[float, str]] = []
        self.scale = 1.0
        self._q: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        self._mods: set[str] = set()
        self._threads: list[threading.Thread] = []
        self._listeners = []
        self.started = 0.0

    # Lifecycle -------------------------------------------------------------
    def start(self):
        from pynput import keyboard, mouse

        (self.dir / "frames").mkdir(parents=True, exist_ok=True)
        (self.dir / "clicks").mkdir(parents=True, exist_ok=True)
        self.started = time.time()
        for target in (self._frame_loop, self._worker):
            t = threading.Thread(target=target, daemon=True)
            t.start()
            self._threads.append(t)
        ml = mouse.Listener(on_click=self._on_click, on_scroll=self._on_scroll)
        kl = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
        ml.start()
        kl.start()
        self._listeners = [ml, kl]

    def stop(self) -> dict:
        for l in self._listeners:
            l.stop()
        self._q.put(None)
        self._stop.set()
        for t in self._threads:
            t.join(timeout=3)
        # One last frame so the final step has an "after" image.
        self._save_frame()
        meta = {"scale": self.scale, "events": self.events, "frames": self.frames, "started": self.started}
        (self.dir / "recording.json").write_text(json.dumps(meta, indent=1))
        return meta

    # Threads ---------------------------------------------------------------
    def _save_frame(self):
        shot = cap.grab()
        self.scale = shot.scale
        path = self.dir / "frames" / f"{len(self.frames):05d}.jpg"
        shot.image.save(path, quality=80)
        self.frames.append((shot.ts, str(path)))

    def _frame_loop(self):
        while not self._stop.is_set():
            t0 = time.time()
            try:
                self._save_frame()
            except Exception:
                pass
            self._stop.wait(max(0.05, FRAME_INTERVAL - (time.time() - t0)))

    def _worker(self):
        while True:
            ev = self._q.get()
            if ev is None:
                return
            try:
                ev["window"] = window_key()
                if ev["type"] == "click":
                    shot = cap.grab()
                    path = self.dir / "clicks" / f"{len(self.events):04d}.jpg"
                    shot.image.save(path, quality=90)
                    ev["before"] = str(path)
                    ev["scale"] = shot.scale
            except Exception:
                pass
            self.events.append(ev)

    # pynput callbacks (keep them tiny) -------------------------------------
    def _on_click(self, x, y, button, pressed):
        if not pressed or self.exclude(x, y):
            return
        self._q.put({"type": "click", "t": time.time(), "x": x, "y": y, "button": getattr(button, "name", "left")})

    def _on_scroll(self, x, y, dx, dy):
        if self.exclude(x, y):
            return
        self._q.put({"type": "scroll", "t": time.time(), "x": x, "y": y, "dy": dy})

    @staticmethod
    def _key_name(key) -> tuple[str | None, str | None]:
        char = getattr(key, "char", None)
        if char is not None:
            return char, None
        name = getattr(key, "name", None) or str(key)
        return None, name

    def _on_press(self, key):
        char, name = self._key_name(key)
        mods = {"cmd": "cmd", "cmd_l": "cmd", "cmd_r": "cmd", "ctrl": "ctrl", "ctrl_l": "ctrl", "ctrl_r": "ctrl",
                "alt": "alt", "alt_l": "alt", "alt_r": "alt", "alt_gr": "alt", "shift": "shift", "shift_l": "shift",
                "shift_r": "shift"}
        if name in mods:
            self._mods.add(mods[name])
            return
        held = self._mods - {"shift"}
        if held:
            self._q.put({"type": "hotkey", "t": time.time(), "keys": sorted(held) + [(char or name or "").lower()]})
        elif char is not None:
            self._q.put({"type": "char", "t": time.time(), "char": char})
        else:
            self._q.put({"type": "key", "t": time.time(), "key": name})

    def _on_release(self, key):
        _, name = self._key_name(key)
        for m in ("cmd", "ctrl", "alt", "shift"):
            if name and name.startswith(m):
                self._mods.discard(m)
