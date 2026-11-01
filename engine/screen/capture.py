"""Screenshots of the primary monitor, plus helpers to shrink and crop them for models.

Coordinate convention used across the engine: boxes are [x1, y1, x2, y2] in *screenshot pixels*
(physical pixels). Divide by Shot.scale to get the logical points pyautogui clicks in.
"""
from __future__ import annotations

import base64
import io
import threading
import time
from dataclasses import dataclass, field

from PIL import Image

Box = list  # [x1, y1, x2, y2]

_mss_local = threading.local()


@dataclass
class Shot:
    image: Image.Image
    scale: float = 1.0
    ts: float = field(default_factory=time.time)
    # Logical screen position of the image's top-left corner: (0, 0) for the full screen, the window's corner when
    # the screenshot is cropped to the app the run is working in.
    origin: tuple[float, float] = (0.0, 0.0)

    @property
    def size(self) -> tuple[int, int]:
        return self.image.size

    def to_logical(self, x: float, y: float) -> tuple[float, float]:
        return x / self.scale + self.origin[0], y / self.scale + self.origin[1]

    def box_to_logical(self, box: Box) -> list[float]:
        ox, oy = self.origin
        return [round(box[0] / self.scale + ox, 1), round(box[1] / self.scale + oy, 1),
                round(box[2] / self.scale + ox, 1), round(box[3] / self.scale + oy, 1)]

    def logical_to_image(self, box: list[float]) -> Box:
        """Logical screen box -> pixel box in this image."""
        ox, oy = self.origin
        return [(box[0] - ox) * self.scale, (box[1] - oy) * self.scale, (box[2] - ox) * self.scale, (box[3] - oy) * self.scale]


def crop_to_window(shot: Shot, bounds: tuple[float, float, float, float]) -> Shot:
    """Crop a full-screen shot to a window's logical bounds (x, y, w, h), clamped to the screen."""
    x, y, w, h = bounds
    box = clamp_box([x * shot.scale, y * shot.scale, (x + w) * shot.scale, (y + h) * shot.scale], shot.size)
    if box[2] - box[0] < 50 or box[3] - box[1] < 50:
        return shot
    img = shot.image.crop(tuple(int(v) for v in box))
    return Shot(image=img, scale=shot.scale, ts=shot.ts, origin=(box[0] / shot.scale, box[1] / shot.scale))


def _mss():
    # mss instances are not thread-safe; keep one per thread.
    inst = getattr(_mss_local, "inst", None)
    if inst is None:
        import mss

        inst = mss.mss()
        _mss_local.inst = inst
    return inst


def logical_screen_size() -> tuple[int, int]:
    import pyautogui

    w, h = pyautogui.size()
    return int(w), int(h)


_fake_version = 0


def bump_fake_screen():
    """Fake-screen mode: an input action happened, so the synthetic screen should change."""
    global _fake_version
    _fake_version += 1


def _fake_grab() -> Shot:
    import random

    from PIL import ImageDraw

    img = Image.new("RGB", (2560, 1600), (236, 238, 243))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 2560, 90], fill=(17, 24, 39))
    for i in range(12):
        x, y = 500 + (i % 6) * 300, 400 + (i // 6) * 400
        d.rounded_rectangle([x, y, x + 220, y + 70], radius=12, fill=(37 + i * 12, 99, 235))
    rnd = random.Random(_fake_version)
    for y in range(120, 360, 12):
        for x in range(40, 320, 12):
            g = rnd.randint(150, 255)
            d.rectangle([x, y, x + 11, y + 11], fill=(g, g, g))
    return Shot(image=img, scale=2.0)


def grab() -> Shot:
    from ..config import config

    if config.fake_screen:
        return _fake_grab()
    sct = _mss()
    if len(sct.monitors) < 2 or not sct.monitors[1].get("width"):
        from ..sdk.errors import AgentError

        raise AgentError(
            "No display available for screenshots. On macOS, grant Screen Recording to the app that launched the "
            "agent (Terminal, VS Code or Electron) in System Settings > Privacy & Security, then restart it.",
            retryable=False,
        )
    mon = sct.monitors[1]  # primary monitor
    raw = sct.grab(mon)
    img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
    try:
        lw, _ = logical_screen_size()
        scale = img.width / lw if lw else 1.0
    except Exception:
        scale = 1.0
    return Shot(image=img, scale=scale)


def clamp_box(box: Box, size: tuple[int, int]) -> Box:
    w, h = size
    x1, y1, x2, y2 = box
    x1, x2 = sorted((max(0, min(w, x1)), max(0, min(w, x2))))
    y1, y2 = sorted((max(0, min(h, y1)), max(0, min(h, y2))))
    return [int(x1), int(y1), int(x2), int(y2)]


def expand_box(box: Box, size: tuple[int, int], pad: float = 0.0, factor: float = 1.0, min_size: int = 0) -> Box:
    x1, y1, x2, y2 = box
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    hw = max((x2 - x1) * factor / 2 + pad, min_size / 2)
    hh = max((y2 - y1) * factor / 2 + pad, min_size / 2)
    return clamp_box([cx - hw, cy - hh, cx + hw, cy + hh], size)


def box_center(box: Box) -> tuple[float, float]:
    return (box[0] + box[2]) / 2, (box[1] + box[3]) / 2


def crop(img: Image.Image, box: Box) -> Image.Image:
    return img.crop(tuple(clamp_box(box, img.size)))


def fit(img: Image.Image, max_edge: int) -> tuple[Image.Image, float]:
    """Downscale so the long edge is <= max_edge. Returns (image, factor) where
    original_px = model_px * factor."""
    long_edge = max(img.size)
    if long_edge <= max_edge:
        return img, 1.0
    f = long_edge / max_edge
    resized = img.resize((round(img.width / f), round(img.height / f)), Image.LANCZOS)
    return resized, f


def to_data_url(img: Image.Image, fmt: str = "JPEG", quality: int = 80) -> str:
    buf = io.BytesIO()
    if fmt == "JPEG":
        img.convert("RGB").save(buf, format="JPEG", quality=quality)
        mime = "image/jpeg"
    else:
        img.save(buf, format="PNG")
        mime = "image/png"
    return f"data:{mime};base64," + base64.b64encode(buf.getvalue()).decode()


def thumbnail_with_outline(img: Image.Image, box: Box, mask: Image.Image | None = None, size: int = 220) -> str:
    """Crop around the found element, draw the mask/box outline, return a PNG data URL for the UI."""
    from PIL import ImageDraw, ImageFilter

    region = expand_box(box, img.size, pad=40, factor=1.6, min_size=120)
    patch = img.crop(tuple(region)).convert("RGB")
    draw = ImageDraw.Draw(patch, "RGBA")
    if mask is not None:
        m = mask.crop(tuple(region)).convert("L")
        edges = m.filter(ImageFilter.FIND_EDGES).point(lambda v: 255 if v > 40 else 0)
        overlay = Image.new("RGBA", patch.size, (99, 102, 241, 0))
        overlay.paste((99, 102, 241, 70), mask=m.point(lambda v: 255 if v > 127 else 0))
        overlay.paste((129, 140, 248, 255), mask=edges)
        patch = Image.alpha_composite(patch.convert("RGBA"), overlay).convert("RGB")
    else:
        rx, ry = region[0], region[1]
        draw.rounded_rectangle(
            [box[0] - rx, box[1] - ry, box[2] - rx, box[3] - ry], radius=6, outline=(129, 140, 248, 255), width=3
        )
    patch.thumbnail((size, size))
    return to_data_url(patch, "PNG")


def mask_overlay(mask: Image.Image, box: Box, scale: float, origin: tuple[float, float] = (0.0, 0.0)) -> dict | None:
    """SAM mask as a tinted, outlined transparent PNG positioned in logical coordinates, for the screen overlay."""
    from PIL import ImageFilter

    region = expand_box(box, mask.size, pad=8)
    m = mask.crop(tuple(region)).convert("L").point(lambda v: 255 if v > 127 else 0)
    if not m.getbbox():
        return None
    # Keep it light: at most ~2x logical resolution.
    max_w = int((region[2] - region[0]) / scale * 2)
    if m.width > max_w > 0:
        m = m.resize((max_w, max(1, int(m.height * max_w / m.width))), Image.NEAREST)
    edge = m.filter(ImageFilter.FIND_EDGES).filter(ImageFilter.MaxFilter(5))
    rgba = Image.new("RGBA", m.size, (0, 0, 0, 0))
    rgba.paste((37, 99, 235, 46), mask=m)
    rgba.paste((37, 99, 235, 255), mask=edge)
    ox, oy = origin
    rect = [region[0] / scale + ox, region[1] / scale + oy, region[2] / scale + ox, region[3] / scale + oy]
    return {"rect": [round(v, 1) for v in rect], "png": to_data_url(rgba, "PNG")}


def paint_box(img: Image.Image, box: Box, fill=(128, 128, 128)) -> Image.Image:
    """Cover a region (the agent's own panel) so models never pick targets behind it."""
    from PIL import ImageDraw

    out = img.copy()
    ImageDraw.Draw(out).rectangle(clamp_box(box, img.size), fill=fill)
    return out
