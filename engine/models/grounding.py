"""SAM 3.1 grounding: finds the element a script line names (e.g. "Save button") on the full screenshot
and returns its box and mask. The click goes to the mask centroid (or box centre).

On the Meta Model API, SAM 3.1 is served on the Responses endpoint (/v1/responses, not chat completions):
the input is the image plus a short object phrase, and the answer is text with one token per found object:

    <|box;x1=1040;y1=100;x2=1240;y2=150;w=1280;h=800|><|mask;x=0;y=0;data=51,201,...|>

Box coordinates are in a w x h frame (the image as SAM saw it). An empty answer means nothing matched. The mask's
encoding isn't documented yet, so only the box is used (the click goes to its centre).

SAM returns every instance of what it's asked for, with precise boxes, but it matches the kind of object ("button")
far better than the label on it ("Rename Save button" often comes back as a different button). So SAM proposes
candidates, for the phrase and for the element kind in it, and the vision model (Muse Spark), which reads labels,
picks the target from the candidates drawn as numbered boxes. No candidates, or none that is the target, means
"not found" and the router falls back to the grid.
GROUNDING_ENDPOINT (e.g. "/segment") still switches to a plain JSON POST for other providers.
"""
from __future__ import annotations

import base64
import re
import io
import time
from dataclasses import dataclass

from PIL import Image, ImageDraw

from ..config import config
from ..sdk.errors import StoppedError
from ..screen.capture import Box, clamp_box, fit, to_data_url
from .client import ModelClient, extract_json, image_part, interruptible, text_part


@dataclass
class Grounded:
    box: Box  # screenshot pixels
    point: tuple[float, float]  # click point in screenshot pixels (mask centroid or box center)
    mask: Image.Image | None = None  # full-screenshot-size L mask, if SAM returned one
    found: bool = True
    reason: str = ""  # why it was not found
    label: str = ""  # which method found it ("SAM 3.1", "Spark grid", ...), set by the router


def mask_centroid(mask: Image.Image) -> tuple[float, float] | None:
    small = mask.convert("L")
    f = max(1, max(small.size) // 400)
    if f > 1:
        small = small.resize((small.width // f, small.height // f))
    px = small.load()
    sx = sy = n = 0
    for y in range(small.height):
        for x in range(small.width):
            if px[x, y] > 127:
                sx += x
                sy += y
                n += 1
    if not n:
        return None
    return (sx / n + 0.5) * f, (sy / n + 0.5) * f


def _decode_mask(raw, crop_size: tuple[int, int]) -> Image.Image | None:
    """Accepts a base64 PNG, a polygon [[x,y],...], or COCO-style uncompressed RLE {"size":[h,w],"counts":[...]}."""
    try:
        if isinstance(raw, str):
            data = raw.split(",", 1)[1] if raw.startswith("data:") else raw
            return Image.open(io.BytesIO(base64.b64decode(data))).convert("L").resize(crop_size)
        if isinstance(raw, dict) and isinstance(raw.get("counts"), list):
            h, w = raw["size"]
            flat = bytearray(h * w)
            pos, val = 0, 0
            for c in raw["counts"]:
                if val:
                    flat[pos : pos + c] = b"\xff" * c
                pos += c
                val ^= 1
            # COCO RLE is column-major.
            img = Image.frombytes("L", (h, w), bytes(flat)).transpose(Image.TRANSPOSE)
            return img.resize(crop_size)
        if isinstance(raw, list) and raw and isinstance(raw[0], (list, tuple)):
            img = Image.new("L", crop_size, 0)
            ImageDraw.Draw(img).polygon([tuple(map(float, p[:2])) for p in raw], fill=255)
            return img
    except Exception:
        return None
    return None


# Element kinds SAM finds well as plain objects; a phrase naming one is also searched as that kind.
KINDS = [
    (r"\b(field|input|textbox|text box|search box|box)\b", "input field"),
    (r"\bbutton\b", "button"),
    (r"\blink\b", "link"),
    (r"\bcheck ?box\b", "checkbox"),
    (r"\btab\b", "tab"),
    (r"\bicon\b", "icon"),
    (r"\b(dropdown|drop-down|select|menu)\b", "dropdown"),
    (r"\b(toggle|switch)\b", "switch"),
]
MAX_CANDIDATES = 12


def _iou(a: Box, b: Box) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


class SamGrounder:
    label = "SAM 3.1"

    def __init__(self, client: ModelClient, picker=None):
        self.client = client
        # picker(image, boxes, phrase) -> index of the target among the boxes, or None (the vision model).
        self.picker = picker

    # Provider-specific -----------------------------------------------------
    def _build_request(self, img: Image.Image, phrase: str) -> dict:
        # Only for GROUNDING_ENDPOINT (a plain JSON segmentation endpoint); the Meta API uses /v1/responses.
        return {
            "model": config.grounding_model,
            "image": to_data_url(img, "PNG"),
            "prompt": {"text": phrase},
            "output": ["box", "mask"],
        }

    @staticmethod
    def _parse_all(text: str, size: tuple[int, int]) -> list[Box]:
        """Every `<|box;x1=..;y1=..;x2=..;y2=..;w=..;h=..|>` token, scaled from SAM's frame to `size`."""
        boxes = []
        for m in re.finditer(r"<\|box;([^|]*)\|>", text or ""):
            v = dict(kv.split("=", 1) for kv in m.group(1).split(";") if "=" in kv)
            try:
                w, h = float(v.get("w") or size[0]), float(v.get("h") or size[1])
                sx, sy = size[0] / w, size[1] / h
                boxes.append([float(v["x1"]) * sx, float(v["y1"]) * sy, float(v["x2"]) * sx, float(v["y2"]) * sy])
            except (KeyError, ValueError, ZeroDivisionError):
                continue
        return boxes

    @classmethod
    def _parse_text(cls, text: str, size: tuple[int, int]) -> Box | None:
        boxes = cls._parse_all(text, size)
        return boxes[0] if boxes else None

    def _parse_response(self, data: dict, size: tuple[int, int]) -> tuple[Box | None, Image.Image | None]:
        if "text" in data:
            return self._parse_text(data["text"], size), None
        # TODO(meta-api): confirm response shape. Tolerates common variants.
        item = data
        for key in ("results", "masks", "objects", "predictions", "data"):
            if isinstance(data.get(key), list) and data[key]:
                item = max(data[key], key=lambda r: float(r.get("score", 0)) if isinstance(r, dict) else 0)
                break
        if not isinstance(item, dict):
            return None, None
        raw_box = item.get("box") or item.get("bbox") or item.get("bounding_box")
        box = None
        if raw_box and len(raw_box) == 4:
            box = [float(v) for v in raw_box]
            if item.get("bbox_format") == "xywh":
                box = [box[0], box[1], box[0] + box[2], box[1] + box[3]]
        mask = _decode_mask(item.get("mask") or item.get("segmentation") or item.get("polygon"), size)
        if box is None and mask is not None:
            bb = mask.getbbox()
            box = list(bb) if bb else None
        return box, mask

    def _call(self, img: Image.Image, phrase: str) -> dict:
        req = self._build_request(img, phrase)
        if config.grounding_endpoint:
            import httpx

            r = interruptible(lambda: httpx.post(
                config.base_url.rstrip("/") + config.grounding_endpoint,
                headers={"Authorization": f"Bearer {config.api_key}"},
                json=req,
                timeout=config.request_timeout,
            ))
            r.raise_for_status()
            return r.json()
        resp = interruptible(lambda: self.client.client.responses.create(
            model=config.grounding_model,
            input=[{"role": "user", "content": [{"type": "input_image", "image_url": req["image"]},
                                                {"type": "input_text", "text": phrase}]}],
        ))
        return {"text": getattr(resp, "output_text", "") or ""}

    # Public ----------------------------------------------------------------
    def candidates(self, small: Image.Image, phrase: str) -> list[Box]:
        """SAM's boxes for the phrase and for the element kind it names, plus on-screen text lines whose words match
        the phrase (SAM finds icons and images but not plain text). Without near-duplicates, at most MAX_CANDIDATES."""
        queries = [phrase] + [kind for pat, kind in KINDS if re.search(pat, phrase, re.I) and kind != phrase.lower()]
        sam: list[Box] = []
        for q in queries:
            t0 = time.time()
            data = self._call(small, q)
            self.client.record_external("grounding", time.time() - t0, config.price_per_grounding_call)
            _debug_sam(small, q, data, time.time() - t0)
            for b in self._parse_response_all(data, small.size):
                if all(_iou(b, o) < 0.7 for o in sam):
                    sam.append(b)
        if len(sam) > MAX_CANDIDATES:
            sam = in_zone(sam, phrase, small.size) or sam  # e.g. 67 icons, "far-left sidebar": keep the left ones
        texts = text_candidates(small, phrase) if config.ocr_candidates else []
        boxes: list[Box] = []
        for b in texts + sam:
            if all(_iou(b, o) < 0.5 for o in boxes):
                boxes.append(b)
        return boxes[:MAX_CANDIDATES]

    def _parse_response_all(self, data, size) -> list[Box]:
        if isinstance(data, dict) and "text" in data:
            return self._parse_all(data["text"], size)
        box, _ = self._parse_response(data if isinstance(data, dict) else {}, size)
        return [box] if box else []

    def locate(self, img: Image.Image, phrase: str) -> Grounded:
        small, f = fit(img, config.model_image_max)
        try:
            boxes = self.candidates(small, phrase)
        except StoppedError:
            raise
        except Exception as e:
            return Grounded(box=[0, 0, 0, 0], point=(0, 0), found=False, reason=f"Grounding failed: {e}")
        if not boxes:
            return Grounded(box=[0, 0, 0, 0], point=(0, 0), found=False, reason=f"No element matching {phrase!r} is visible.")
        index = 0
        if self.picker is not None:
            index = self.picker(small, boxes, phrase)
            if index is None or not 0 <= index < len(boxes):
                _debug_pick(small, boxes, None, phrase)
                return Grounded(box=[0, 0, 0, 0], point=(0, 0), found=False,
                                reason=f"SAM found {len(boxes)} candidate(s), but none of them is {phrase!r}.")
        box = clamp_box([v * f for v in boxes[index]], img.size)
        _debug_pick(small, boxes, index, phrase)
        return Grounded(box=box, point=((box[0] + box[2]) / 2, (box[1] + box[3]) / 2))


def _debug_sam(small: Image.Image, query: str, data: dict, seconds: float):
    from ..runner.debug import current_debug

    d = current_debug()
    if d is not None:
        text = (data.get("text") if isinstance(data, dict) else "") or str(data)[:500]
        d.note(f"SAM “{query}” ({seconds:.1f}s): {text.count('<|box;')} box(es)", kind="sam")


def _debug_pick(small: Image.Image, boxes: list, index: int | None, phrase: str):
    from ..runner.debug import current_debug

    d = current_debug()
    if d is not None:
        d.annotate(small, "sam-pick", boxes=boxes, box=boxes[index] if index is not None else None,
                   caption=f"SAM candidates for “{phrase}”: Spark picked {index if index is not None else 'none'}")


# Location words in a target description -> the part of the screen (fractions x1, y1, x2, y2) it must be in.
ZONES = [
    (r"\b(far[- ]left|left(most)?|left[- ]hand)\b", (0, 0, 0.4, 1)),
    (r"\b(far[- ]right|right(most)?|right[- ]hand)\b", (0.6, 0, 1, 1)),
    (r"\b(top|upper|header|title bar|toolbar)\b", (0, 0, 1, 0.35)),
    (r"\b(bottom|lower|footer)\b", (0, 0.65, 1, 1)),
]


def in_zone(boxes: list[Box], phrase: str, size: tuple[int, int]) -> list[Box]:
    w, h = size
    keep = boxes
    for pat, (x1, y1, x2, y2) in ZONES:
        if re.search(pat, phrase, re.I):
            keep = [b for b in keep if x1 * w <= (b[0] + b[2]) / 2 <= x2 * w and y1 * h <= (b[1] + b[3]) / 2 <= y2 * h]
    return keep


# Words that describe what kind of element or where it is, not what it says.
GENERIC = set("""a an the at in on of to for with and or by from into its it is that which this
button field input icon box bar text area link tab menu item list row column entry option panel pane sidebar side
left right top bottom center centre middle upper lower far near next below above under over beside first second
third last vertical horizontal window screen page app main small large big blue red green grey gray white black
dark light round rounded circular square labeled labelled named called says shows showing containing placeholder
starting reads with""".split())


def _words(text: str) -> list[str]:
    return [w for w in re.findall(r"#?[\w][\w'.-]*", text.lower()) if w not in GENERIC and len(w.strip("#")) >= 2]


def text_candidates(small: Image.Image, phrase: str, limit: int = 6) -> list[Box]:
    """Boxes of on-screen text lines (on-device OCR) that match the phrase's words or quoted text, best first."""
    from ..screen import ocr

    if not ocr.available():
        return []
    try:
        lines = ocr.text_boxes(small, accurate=True)
    except Exception:  # noqa: BLE001 - OCR is a bonus; SAM still runs
        return []
    quoted = [q.strip().lower() for q in re.findall(r"['\"“‘]([^'\"”’]{2,})['\"”’]", phrase)]
    want = _words(phrase)
    scored = []
    for box, text in lines:
        low = text.lower()
        have = _words(text)
        score = sum(3 for q in quoted if q.strip("# ") and q.strip("# ") in low)
        for w in want:
            bare = w.strip("#")
            if any(h.strip("#") == bare for h in have):
                score += 1
            elif len(bare) >= 4 and any(h.strip("#.").startswith(bare[:4]) and len(h) >= 4 for h in have):
                score += 0.5  # truncated ("build-for-your-w...") or misread
        if score >= 1:
            pad = 4
            scored.append((score, [box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad]))
    scored.sort(key=lambda s: -s[0])
    debug_note = [(round(s, 1), [round(v) for v in b]) for s, b in scored[:limit]]
    from ..runner.debug import current_debug

    d = current_debug()
    if d is not None:
        d.note(f"text matches for “{phrase}”: {debug_note}", kind="ocr")
    return [b for _, b in scored[:limit]]
