"""Measure grounding accuracy (SAM 3.1, or the grid stand-in) on labeled screenshots, for the pitch.

1. Collect screenshots from different apps:
       python -m engine.tools.eval_grounding capture shots/ --count 25 --every 4
2. Write shots/labels.json (screenshot-pixel boxes):
       [{"image": "000.png", "target": "blue Save button", "box": [x1, y1, x2, y2]}, ...]
3. Run:
       python -m engine.tools.eval_grounding run shots/
A hit means the click point lands inside the labeled box.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from PIL import Image


def capture(folder: Path, count: int, every: float):
    from ..screen.capture import grab

    folder.mkdir(parents=True, exist_ok=True)
    for i in range(count):
        print(f"capturing {i + 1}/{count} in {every}s - switch to another app")
        time.sleep(every)
        grab().image.save(folder / f"{i:03d}.png")
    print(f"saved {count} screenshots to {folder}; now write {folder / 'labels.json'}")


def _inside(point, box) -> bool:
    return box[0] <= point[0] <= box[2] and box[1] <= point[1] <= box[3]


def _iou(a, b) -> float:
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union else 0.0


def run(folder: Path):
    from ..models import get_models
    from ..metrics import GLOBAL_METRICS

    models = get_models()
    labels = json.loads((folder / "labels.json").read_text())
    rows = []
    for item in labels:
        img = Image.open(folder / item["image"]).convert("RGB")
        gt = item["box"]
        t0 = time.time()
        g = models.grounder.locate(img, item["target"])
        hit = g.found and _inside(g.point, gt)
        iou = _iou(g.box, gt) if g.found else 0.0
        rows.append({"image": item["image"], "target": item["target"], "found": g.found, "hit": hit,
                     "iou": round(iou, 3), "seconds": round(time.time() - t0, 2)})
        mark = "✓" if hit else "✗"
        print(f"{mark} {item['image']:>10}  {item['target'][:40]:<40} found={g.found} iou={iou:.2f}")
    n = len(rows) or 1
    summary = {
        "samples": len(rows),
        "found_rate": round(sum(r["found"] for r in rows) / n, 3),
        "accuracy": round(sum(r["hit"] for r in rows) / n, 3),
        "mean_iou": round(sum(r["iou"] for r in rows) / n, 3),
        "avg_seconds": round(sum(r["seconds"] for r in rows) / n, 2),
        "cost": round(GLOBAL_METRICS.cost, 4),
    }
    (folder / "results.json").write_text(json.dumps({"summary": summary, "rows": rows}, indent=1))
    print(json.dumps(summary, indent=1))


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("capture")
    c.add_argument("folder", type=Path)
    c.add_argument("--count", type=int, default=25)
    c.add_argument("--every", type=float, default=4)
    r = sub.add_parser("run")
    r.add_argument("folder", type=Path)
    a = p.parse_args()
    capture(a.folder, a.count, a.every) if a.cmd == "capture" else run(a.folder)


if __name__ == "__main__":
    main()
