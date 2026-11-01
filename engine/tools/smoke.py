"""One call per model role against the Meta Model API, to confirm keys, model IDs and response shapes.

    python -m engine.tools.smoke            # uses MODEL_API_KEY from .env
    python -m engine.tools.smoke --raw      # also print raw replies
"""
from __future__ import annotations

import argparse
import io
import json
import time
import traceback
import wave

from PIL import Image, ImageDraw


def _test_image() -> Image.Image:
    img = Image.new("RGB", (1280, 800), (245, 245, 248))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 1280, 56], fill=(32, 33, 36))
    d.text((20, 20), "Invoices - Demo App", fill=(255, 255, 255))
    d.rounded_rectangle([1040, 100, 1240, 150], radius=8, fill=(37, 99, 235))
    d.text((1085, 117), "New Invoice", fill=(255, 255, 255))
    d.rectangle([40, 200, 600, 240], outline=(150, 150, 150), width=2)
    d.text((50, 213), "Customer name", fill=(120, 120, 120))
    return img


def _silent_wav(seconds: float = 1.0) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * int(16000 * seconds))
    return buf.getvalue()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--raw", action="store_true")
    args = p.parse_args()

    from ..config import config
    from ..metrics import GLOBAL_METRICS
    from ..models import get_models
    from ..sdk import sdk_reference

    print(f"base_url={config.base_url} fake={config.fake_models}")
    print(f"planner={config.planner_model} vision={config.vision_model} grounding={config.grounding_model} "
          f"voice={config.voice_model}\n")
    models = get_models()
    img = _test_image()
    checks = {
        "planner": lambda: models.planner.generate_script("Click the New Invoice button", img, sdk_reference()),
        "vision.check": lambda: models.vision.check(img, "a New Invoice button is visible"),
        "vision.read_text": lambda: models.vision.read_text(img.crop((0, 0, 640, 60))),
        "grounding": lambda: models.grounder.locate(img, "New Invoice button"),
        "voice": lambda: models.voice.transcribe(_silent_wav(), "audio/wav"),
    }
    ok = True
    for name, fn in checks.items():
        t0 = time.time()
        try:
            out = fn()
            dt = time.time() - t0
            summary = out if isinstance(out, str) else getattr(out, "__dict__", out)
            if name == "grounding":
                # The test image's New Invoice button spans (1040, 100)-(1240, 150).
                hit = out.found and 1040 <= out.point[0] <= 1240 and 100 <= out.point[1] <= 150
                summary = {"found": out.found, "box": out.box, "point": out.point, "on_button": hit,
                           "has_mask": out.mask is not None, "reason": out.reason}
                if not hit:
                    print(f"⚠ {name}: missed the button - for SAM, adjust _build_request/_parse_response in models/grounding.py")
            print(f"✓ {name} ({dt:.1f}s): {json.dumps(summary, default=str)[:300 if not args.raw else 3000]}")
        except Exception as e:  # noqa: BLE001
            ok = False
            print(f"✗ {name}: {type(e).__name__}: {e}")
            if args.raw:
                traceback.print_exc()
    print(f"\nmetrics: {json.dumps(GLOBAL_METRICS.snapshot(), default=str)}")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
