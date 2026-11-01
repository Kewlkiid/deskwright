"""SAM 3.1 grounding: finds the element a script line names (e.g. "Save button") on the full screenshot
and returns its box and mask. The click goes to the mask centroid (or box centre).

The exact SAM 3.1 request/response shape on the Meta Model API is not confirmed yet. Everything
provider-specific lives in `_build_request` / `_parse_response` below; adjust those two once the
docs are available. Two transports are supported:
  - GROUNDING_ENDPOINT set (e.g. "/segment"): POST JSON to {MODEL_BASE_URL}{GROUNDING_ENDPOINT}
  - otherwise: chat.completions with model=sam-3.1, image + JSON text prompt
"""
from __future__ import annotations

import base64
import io
import time
from dataclasses import dataclass

from PIL import Image, ImageDraw

from ..config import config
from ..screen.capture import Box, clamp_box, fit, to_data_url
from .client import ModelClient, extract_json, image_part, text_part


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


class SamGrounder:
    label = "SAM 3.1"

    def __init__(self, client: ModelClient):
        self.client = client

    # Provider-specific -----------------------------------------------------
    def _build_request(self, img: Image.Image, phrase: str) -> dict:
        # TODO(meta-api): confirm SAM 3.1 field names once the API docs are out.
        return {
            "model": config.grounding_model,
            "image": to_data_url(img, "PNG"),
            "prompt": {"text": phrase},
            "output": ["box", "mask"],
        }

    def _parse_response(self, data: dict, size: tuple[int, int]) -> tuple[Box | None, Image.Image | None]:
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

            r = httpx.post(
                config.base_url.rstrip("/") + config.grounding_endpoint,
                headers={"Authorization": f"Bearer {config.api_key}"},
                json=req,
                timeout=config.request_timeout,
            )
            r.raise_for_status()
            return r.json()
        prompt = (
            f"Segment the UI element: {phrase!r} (image is {img.width}x{img.height} pixels). "
            'Reply with JSON only: {"box": [x1, y1, x2, y2], "mask": <polygon [[x,y],...] or base64 PNG>, "score": 0-1}, '
            'or {"box": null} if it is not visible.'
        )
        reply = self.client.chat(
            "grounding",
            config.grounding_model,
            [{"role": "user", "content": [image_part(req["image"]), text_part(prompt)]}],
            max_tokens=1500,
            temperature=0.0,
        )
        return extract_json(reply)

    # Public ----------------------------------------------------------------
    def locate(self, img: Image.Image, phrase: str) -> Grounded:
        small, f = fit(img, config.model_image_max)
        t0 = time.time()
        try:
            data = self._call(small, phrase)
            box, mask = self._parse_response(data if isinstance(data, dict) else {}, small.size)
        except Exception as e:
            box, mask = None, None
            reason = f"Grounding failed: {e}"
        else:
            reason = f"No element matching {phrase!r} is visible."
        if config.grounding_endpoint:
            self.client.record_external("grounding", time.time() - t0, config.price_per_grounding_call)
        if box is None:
            return Grounded(box=[0, 0, 0, 0], point=(0, 0), found=False, reason=reason)
        box = clamp_box([v * f for v in box], img.size)
        point = ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
        full_mask = None
        if mask is not None:
            full_mask = mask.resize(img.size)
            c = mask_centroid(mask)
            if c:
                point = (c[0] * f, c[1] * f)
        return Grounded(box=box, point=point, mask=full_mask)
