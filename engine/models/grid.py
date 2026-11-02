"""Grid grounding: the backup to SAM 3.1. Works with any vision chat model: Muse Spark by default (GRID_MODEL).

Vision chat models are poor at emitting exact pixel coordinates but good at reading labels. Two calls:
1. a fine 24x16 grid labelled only along the edges (like a spreadsheet, so the screen stays visible): which cell
   holds the element's centre? "found": false is respected (no guessing at something that isn't there);
2. a 6x6 labelled grid on the area around that cell: the cell again, now small;
then the point snaps to the exact box around it from SAM, on-screen text or Accessibility, when there is one.
Benchmarked on 13 Discord/Maps/App Store targets: 12/13 in ~18s, against 13/13 in ~89s for the old four zooms.
"""
from __future__ import annotations

import re
import string

from PIL import Image, ImageDraw, ImageFont

from ..config import config
from ..sdk.errors import StoppedError
from ..screen.capture import Box, clamp_box, to_data_url
from .client import ModelClient, extract_json, image_part, text_part
from .grounding import Grounded

FINE = (24, 16)  # first pass, labelled along the edges
ZOOM = (6, 6)  # second pass on the area around the first answer
VIEW = 1024  # long edge the gridded image is scaled to before sending
MIN_SHRINK = 0.75  # stop zooming once the next view would keep more than this share of the current one

EDGE_PROMPT = (
    "The image is a computer screen with a thin red grid over it: columns A-{last} are labelled along the top and "
    "bottom edges, rows 1-{rows} along the left and right edges. Find this UI element: {phrase!r}. Give the cell "
    'containing the element\'s centre. Reply with JSON only: {{"found": true, "center": "K7"}} or '
    '{{"found": false, "reason": "..."}} if it is not visible.'
)

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


def draw_edge_grid(img: Image.Image, cols: int, rows: int) -> Image.Image:
    """Scale `img` to VIEW px and draw thin grid lines, with column letters and row numbers only in a margin around it."""
    s = VIEW / max(img.size)
    view = img.convert("RGB").resize((round(img.width * s), round(img.height * s)), Image.LANCZOS)
    pad = 26
    canvas = Image.new("RGB", (view.width + 2 * pad, view.height + 2 * pad), "white")
    canvas.paste(view, (pad, pad))
    d = ImageDraw.Draw(canvas, "RGBA")
    cw, ch = view.width / cols, view.height / rows
    font = _font(14)
    for i in range(cols + 1):
        d.line([(pad + i * cw, pad), (pad + i * cw, pad + view.height)], fill=(255, 0, 0, 110), width=1)
    for j in range(rows + 1):
        d.line([(pad, pad + j * ch), (pad + view.width, pad + j * ch)], fill=(255, 0, 0, 110), width=1)
    for i in range(cols):
        for y in (4, pad + view.height + 5):
            d.text((pad + i * cw + cw / 2 - 4, y), string.ascii_uppercase[i], fill=(200, 0, 0), font=font)
    for j in range(rows):
        for x in (3, pad + view.width + 4):
            d.text((x, pad + j * ch + ch / 2 - 8), str(j + 1), fill=(200, 0, 0), font=font)
    return canvas


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
    accepts_snap = True  # the router hands it the exact boxes already found on the screenshot
    def __init__(self, client: ModelClient):
        self.client = client
        m = config.grid_model.lower()
        self.label = "Gemma grid" if "gemma" in m else "Spark grid" if "spark" in m else "Llama grid" if "llama" in m else "Grid"

    def _ask(self, view: Image.Image, prompt: str) -> dict:
        messages = [{"role": "user", "content": [image_part(to_data_url(view, "PNG")), text_part(prompt)]}]
        # Gemma and Llama answer directly; reasoning models (Muse Spark, Glimmer) think first, kept short here.
        reasoning = not any(k in config.grid_model.lower() for k in ("gemma", "llama"))
        effort = config.grid_effort or "low"
        reply = self.client.chat("grounding", config.grid_model, messages, max_tokens=200, temperature=0.0,
                                 reasoning=reasoning, effort=effort)
        if not reply.strip() and reasoning:
            # Spark sometimes thinks until it runs out of tokens and answers nothing: ask once more.
            reply = self.client.chat("grounding", config.grid_model, messages, max_tokens=200, temperature=0.0,
                                     reasoning=reasoning, effort="low")
        data = extract_json(reply)
        return data if isinstance(data, dict) else {}

    def locate(self, img: Image.Image, phrase: str, snap_to: list[Box] | None = None) -> Grounded:
        """snap_to: exact boxes already known on this screenshot (SAM, text, Accessibility) in `img` pixels."""
        from .grounding import snap

        cols, rows = FINE
        try:
            data = self._ask(draw_edge_grid(img, cols, rows),
                             EDGE_PROMPT.format(last=string.ascii_uppercase[cols - 1], rows=rows, phrase=phrase))
        except StoppedError:
            raise
        except Exception as e:
            return Grounded(box=[0, 0, 0, 0], point=(0, 0), found=False, reason=f"Grounding failed: {e}")
        cell = parse_cell(data.get("center"), cols, rows) if data.get("found") is not False else None
        if cell is None:
            reason = str(data.get("reason") or f"No element matching {phrase!r} is visible.")
            return Grounded(box=[0, 0, 0, 0], point=(0, 0), found=False, reason=reason)
        whole: Box = [0, 0, img.width, img.height]
        box = cells_box([cell], whole, cols, rows)
        point = ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
        cw, ch = img.width / cols, img.height / rows
        radius = (cw ** 2 + ch ** 2) ** 0.5
        # Zoom: the area two and a half cells around that one, a 6x6 grid, once.
        zone = clamp_box([point[0] - 2.5 * cw, point[1] - 2.5 * ch, point[0] + 2.5 * cw, point[1] + 2.5 * ch], img.size)
        zc, zr = ZOOM
        try:
            prompt = GRID_PROMPT.format(where="a zoomed-in part of a computer screen", cols=f"A-{string.ascii_uppercase[zc - 1]}",
                                        rows=zr, phrase=phrase)
            zdata = self._ask(draw_grid(img.crop(tuple(round(v) for v in zone)), zc, zr), prompt)
            zcell = parse_cell(zdata.get("center"), zc, zr) if zdata.get("found") is not False else None
            if zcell is not None:
                box = cells_box([zcell], zone, zc, zr)
                point = ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
                radius = (((zone[2] - zone[0]) / zc) ** 2 + ((zone[3] - zone[1]) / zr) ** 2) ** 0.5
        except StoppedError:
            raise
        except Exception:  # noqa: BLE001 - the first answer stands
            pass
        exact = snap(point, snap_to or [], radius)
        if exact is not None:
            box = clamp_box(list(exact), img.size)
            point = ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
        return Grounded(box=clamp_box(box, img.size), point=point)
