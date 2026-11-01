"""Grid grounding: the backup to SAM 3.1 (and the only method on OpenRouter, which doesn't host SAM). Works with
any vision chat model: Muse Spark on the Meta API, Gemma 4 26B on OpenRouter (GRID_MODEL).

Vision chat models are poor at emitting exact pixel coordinates but good at reading labels. So we draw a
labelled grid over the full screenshot and ask which cells the named element covers, then zoom into those
cells (plus a one-cell margin) with a fresh grid and ask again. Each pass is one cheap call; after a few
passes (up to four) the covered cells are a tight box around the element, and we click the centre of the cell the model
says holds the element's centre.
"""
from __future__ import annotations

import re
import string

from PIL import Image, ImageDraw, ImageFont

from ..config import config
from ..screen.capture import Box, clamp_box, to_data_url
from .client import ModelClient, extract_json, image_part, text_part
from .grounding import Grounded

PASSES = [(12, 8), (8, 8), (8, 8), (6, 6)]  # columns x rows: full screen, then up to three zooms
VIEW = 1024  # long edge the gridded image is scaled to before sending
MIN_SHRINK = 0.75  # stop zooming once the next view would keep more than this share of the current one

GRID_PROMPT = (
    "The image shows {where} with a red labelled grid drawn over it. Columns are letters {cols} "
    "(left to right), rows are numbers 1-{rows} (top to bottom); each cell's label is in its top-left corner.\n"
    "Find this UI element: {phrase!r}.\n"
    'List every cell the element overlaps in "cells", and in "center" give the single cell containing the '
    "element's centre (for a text field, a point inside the field; for a button, its middle).\n"
    'Reply with JSON only: {{"found": true, "cells": ["B2", ...], "center": "B2"}} '
    'or {{"found": false, "reason": "..."}} if it is not visible.'
)


def _font(size: int):
    for name in ("/System/Library/Fonts/SFNSMono.ttf", "/System/Library/Fonts/Menlo.ttc", "DejaVuSansMono.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def draw_grid(img: Image.Image, cols: int, rows: int) -> Image.Image:
    """Scale `img` to VIEW px on its long edge and draw a labelled cols x rows grid over it."""
    s = VIEW / max(img.size)
    view = img.convert("RGB").resize((round(img.width * s), round(img.height * s)), Image.LANCZOS)
    d = ImageDraw.Draw(view, "RGBA")
    cw, ch = view.width / cols, view.height / rows
    font = _font(max(14, int(min(cw, ch) / 5)))
    for i in range(1, cols):
        d.line([(i * cw, 0), (i * cw, view.height)], fill=(255, 0, 0, 170), width=2)
    for j in range(1, rows):
        d.line([(0, j * ch), (view.width, j * ch)], fill=(255, 0, 0, 170), width=2)
    for i in range(cols):
        for j in range(rows):
            label = f"{string.ascii_uppercase[i]}{j + 1}"
            x, y = i * cw + 3, j * ch + 2
            tb = d.textbbox((x, y), label, font=font)
            d.rectangle([tb[0] - 2, tb[1] - 1, tb[2] + 2, tb[3] + 1], fill=(255, 255, 255, 215))
            d.text((x, y), label, fill=(220, 0, 0, 255), font=font)
    return view


def parse_cell(label, cols: int, rows: int) -> tuple[int, int] | None:
    m = re.fullmatch(r"\s*([A-Za-z])\s*-?\s*(\d+)\s*", str(label or ""))
    if not m:
        return None
    c, r = string.ascii_uppercase.index(m.group(1).upper()), int(m.group(2)) - 1
    return (c, r) if 0 <= c < cols and 0 <= r < rows else None


def cells_box(cells: list[tuple[int, int]], zone: Box, cols: int, rows: int, margin: int = 0) -> Box:
    """Screenshot-pixel box covering `cells` of a grid laid over `zone`, grown by `margin` cells."""
    cw, ch = (zone[2] - zone[0]) / cols, (zone[3] - zone[1]) / rows
    c1, r1 = min(c for c, _ in cells) - margin, min(r for _, r in cells) - margin
    c2, r2 = max(c for c, _ in cells) + 1 + margin, max(r for _, r in cells) + 1 + margin
    return [
        zone[0] + max(0, c1) * cw,
        zone[1] + max(0, r1) * ch,
        zone[0] + min(cols, c2) * cw,
        zone[1] + min(rows, r2) * ch,
    ]


def _area(b: Box) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


class GridGrounder:
    def __init__(self, client: ModelClient):
        self.client = client
        m = config.grid_model.lower()
        self.label = "Gemma grid" if "gemma" in m else "Spark grid" if "spark" in m else "Llama grid" if "llama" in m else "Grid"

    def _ask(self, img: Image.Image, phrase: str, cols: int, rows: int, first: bool) -> dict:
        prompt = GRID_PROMPT.format(
            where="a computer screen" if first else "a zoomed-in part of a computer screen",
            cols=f"A-{string.ascii_uppercase[cols - 1]}",
            rows=rows,
            phrase=phrase,
        )
        reply = self.client.chat(
            "grounding",
            config.grid_model,
            [{"role": "user", "content": [image_part(to_data_url(draw_grid(img, cols, rows), "PNG")), text_part(prompt)]}],
            max_tokens=200,
            temperature=0.0,
            # Gemma and Llama answer directly; reasoning models (Muse Spark, Glimmer) need room to think first.
            reasoning=not any(k in config.grid_model.lower() for k in ("gemma", "llama")),
        )
        data = extract_json(reply)
        return data if isinstance(data, dict) else {}

    def locate(self, img: Image.Image, phrase: str) -> Grounded:
        zone: Box = [0, 0, img.width, img.height]
        box = point = None
        for i, (cols, rows) in enumerate(PASSES):
            view = img.crop(tuple(round(v) for v in zone))
            try:
                data = self._ask(view, phrase, cols, rows, first=i == 0)
            except Exception as e:
                if box is None:
                    return Grounded(box=[0, 0, 0, 0], point=(0, 0), found=False, reason=f"Grounding failed: {e}")
                break  # keep the previous pass's answer
            cells = [c for c in (parse_cell(x, cols, rows) for x in data.get("cells") or []) if c]
            center = parse_cell(data.get("center"), cols, rows)
            if data.get("found") is False or not (cells or center):
                if box is None:
                    reason = str(data.get("reason") or f"No element matching {phrase!r} is visible.")
                    return Grounded(box=[0, 0, 0, 0], point=(0, 0), found=False, reason=reason)
                break  # lost it after zooming in: keep the coarser answer
            cells = cells or [center]
            center = center if center in cells else cells[len(cells) // 2]
            box = cells_box(cells, zone, cols, rows)
            cb = cells_box([center], zone, cols, rows)
            point = ((cb[0] + cb[2]) / 2, (cb[1] + cb[3]) / 2)
            nxt = cells_box(cells, zone, cols, rows, margin=1)
            if _area(nxt) > MIN_SHRINK * _area(zone):
                break  # the element fills most of this view; zooming further would not tighten the box
            zone = nxt
        return Grounded(box=clamp_box(box, img.size), point=point)
