"""Per-run debug folder: everything needed to see why a run went the way it did, without rerunning it.

engine/data/debug/<date>-run<id>/
  timeline.md     readable run log: statuses, actions, checks, failures, rewrites, model calls, with image links
  events.jsonl    the same as data, one JSON object per line (t = seconds since the run started)
  calls/NNN-role.txt   each model call: model, every message's text, the reply, timing
  img/NNN-*.jpg        images the models saw, and annotated screenshots (candidate boxes, the chosen box, the click)

On by default (AGENT_DEBUG=0 turns it off); only the newest AGENT_DEBUG_KEEP runs (default 40) are kept.
"""
from __future__ import annotations

import base64
import io
import json
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw

from ..config import config

# Event fields that are images or bulky blobs: never copied into the log.
HEAVY = {"thumb", "png", "mask", "image", "screenshot", "history", "totals", "results", "script", "final_script"}
# UI events that only mirror something already logged (or carry nothing useful for debugging).
QUIET = {"metrics", "pointer", "scope", "cache", "line_passed"}


def _clean(value, depth=0):
    if isinstance(value, dict):
        return {k: _clean(v, depth + 1) for k, v in value.items() if k not in HEAVY}
    if isinstance(value, (list, tuple)):
        return [_clean(v, depth + 1) for v in value[:40]]
    if isinstance(value, str) and len(value) > 2000:
        return value[:2000] + "…"
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)[:300]


class RunDebug:
    def __init__(self, run_id: int, task: str, root: Path | None = None):
        root = root or config.debug_dir
        self.dir = root / f"{datetime.now():%Y%m%d-%H%M%S}-run{run_id}"
        (self.dir / "img").mkdir(parents=True, exist_ok=True)
        (self.dir / "calls").mkdir(exist_ok=True)
        self.t0 = time.time()
        self.n = 0
        self.lock = threading.Lock()
        self.md = open(self.dir / "timeline.md", "w")
        self.jl = open(self.dir / "events.jsonl", "w")
        self.md.write(f"# Run {run_id}\n\nTask: {task}\n\nStarted {datetime.now():%Y-%m-%d %H:%M:%S}\n\n")
        self.line: int | None = None
        _prune(root, keep=config.debug_keep)

    # Low level ---------------------------------------------------------------
    def _next(self) -> int:
        with self.lock:
            self.n += 1
            return self.n

    def _write(self, kind: str, text: str, data: dict | None = None):
        t = time.time() - self.t0
        with self.lock:
            self.jl.write(json.dumps({"t": round(t, 2), "line": self.line, "kind": kind, **(data or {})}, default=str) + "\n")
            where = f"L{self.line} " if self.line else ""
            self.md.write(f"- `{t:7.1f}s` {where}**{kind}** {text}\n")
            self.md.flush()
            self.jl.flush()

    def save_image(self, img, name: str) -> str:
        """Save a PIL image or a data URL; returns the path relative to the run folder."""
        n = self._next()
        if isinstance(img, str):  # data URL
            try:
                img = Image.open(io.BytesIO(base64.b64decode(img.split(",", 1)[1])))
            except Exception:  # noqa: BLE001
                return ""
        rel = f"img/{n:03d}-{name}.jpg"
        im = img.convert("RGB")
        if max(im.size) > 1600:
            im.thumbnail((1600, 1600))
        im.save(self.dir / rel, quality=82)
        return rel

    # What the run reports ------------------------------------------------------
    def event(self, kind: str, **data):
        if kind in QUIET:
            return
        if kind in ("line_started",):
            self.line = data.get("line")
            return
        if isinstance(data.get("script"), str) and kind in ("script_generated", "line_rewritten"):
            rel = f"calls/{self._next():03d}-{kind}.py"
            (self.dir / rel).write_text(data["script"])
            data = {**data, "script_file": rel}
        data = _clean(data)
        brief = {k: v for k, v in data.items() if k not in ("segment",)}
        self._write(kind, json.dumps(brief, default=str)[:600], data)

    def note(self, text: str, kind: str = "log"):
        self._write(kind, text.replace("\n", " ")[:600], {"text": text})

    def annotate(self, img: Image.Image, name: str, *, box=None, point=None, boxes=None, caption: str = "") -> str:
        """Screenshot with candidate boxes (numbered, grey), the chosen box (red) and the click point."""
        im = img.convert("RGB").copy()
        d = ImageDraw.Draw(im)
        w = max(2, round(max(im.size) / 700))
        for i, b in enumerate(boxes or []):
            d.rectangle(list(b), outline=(120, 120, 255), width=w)
            d.text((b[0] + 3, b[1] + 2), str(i), fill=(80, 80, 255))
        if box:
            d.rectangle(list(box), outline=(255, 0, 0), width=w + 1)
        if point:
            x, y = point
            r = 4 * w
            d.ellipse([x - r, y - r, x + r, y + r], outline=(255, 0, 0), width=w)
            d.line([x - 2 * r, y, x + 2 * r, y], fill=(255, 0, 0), width=w)
            d.line([x, y - 2 * r, x, y + 2 * r], fill=(255, 0, 0), width=w)
        rel = self.save_image(im, name)
        self._write("image", f"{caption} ![]({rel})", {"image": rel, "caption": caption})
        return rel

    def model_call(self, role: str, model: str, messages: list, reply: str | None, seconds: float,
                   error: str | None = None, tokens: tuple[int, int] = (0, 0)):
        n = self._next()
        texts, images = [], []
        for m in messages:
            content = m.get("content")
            parts = content if isinstance(content, list) else [{"type": "text", "text": content or ""}]
            for p in parts:
                if p.get("type") in ("text", "input_text"):
                    texts.append(f"[{m.get('role', 'user')}]\n{p.get('text', '')}")
                elif p.get("type") in ("image_url", "input_image"):
                    url = p["image_url"]["url"] if isinstance(p.get("image_url"), dict) else p.get("image_url", "")
                    images.append(self.save_image(url, f"{role}-in"))
                elif p.get("type") == "input_audio":
                    texts.append(f"[{m.get('role', 'user')}] <audio>")
        rel = f"calls/{n:03d}-{role}.txt"
        with open(self.dir / rel, "w") as f:
            f.write(f"model: {model}\nrole: {role}\nseconds: {seconds:.2f}\ntokens in/out: {tokens[0]}/{tokens[1]}\n")
            f.write(f"images: {', '.join(images) or '-'}\n\n")
            f.write("\n\n".join(texts))
            f.write(f"\n\n===== reply =====\n{reply if error is None else 'ERROR: ' + error}\n")
        last = texts[-1].split("\n", 1)[-1] if texts else ""
        answer = (reply or error or "").strip().replace("\n", " ")
        pics = " ".join(f"![]({i})" for i in images)
        self._write("model", f"{role} ({model}, {seconds:.1f}s) [{rel}]({rel}) ask: “{last[:160]}” → “{answer[:240]}” {pics}",
                    {"role": role, "model": model, "seconds": round(seconds, 2), "file": rel, "images": images,
                     "error": error})

    def finish(self, status: str, metrics: dict, error: dict | None = None):
        self._write("finished", f"{status} · {metrics.get('elapsed', 0):.1f}s · {metrics.get('model_calls', 0)} model calls · "
                                f"{metrics.get('cache_hits', 0)} cache hits" + (f" · {error.get('message')}" if error else ""),
                    {"status": status, "metrics": _clean(metrics), "error": _clean(error)})
        self.md.close()
        self.jl.close()


def _prune(root: Path, keep: int):
    runs = sorted((p for p in root.iterdir() if p.is_dir()), key=lambda p: p.name)
    for old in runs[:-keep] if keep > 0 else []:
        shutil.rmtree(old, ignore_errors=True)


def current_debug() -> RunDebug | None:
    from ..sdk.context import _current

    return getattr(_current, "debug", None) if _current is not None else None
