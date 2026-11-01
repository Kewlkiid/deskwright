"""Cheap image fingerprints: perceptual hashes for cache keys and tiny signatures for change detection."""
from __future__ import annotations

import imagehash
from PIL import Image, ImageChops, ImageStat

from .capture import Box, clamp_box

SIG_SIZE = 24


def screen_hash(img: Image.Image) -> str:
    """Coarse fingerprint of the whole screen."""
    small = img.convert("L").resize((256, int(256 * img.height / max(img.width, 1))))
    return str(imagehash.phash(small, hash_size=8))


def patch_hash(img: Image.Image, box: Box) -> str:
    x1, y1, x2, y2 = clamp_box(box, img.size)
    if x2 - x1 < 2 or y2 - y1 < 2:
        return "0" * 16
    return str(imagehash.phash(img.crop((x1, y1, x2, y2)).convert("L"), hash_size=8))


def hamming(a: str, b: str) -> int:
    try:
        return imagehash.hex_to_hash(a) - imagehash.hex_to_hash(b)
    except Exception:
        return 64


def signature(img: Image.Image, box: Box | None = None) -> bytes:
    """Tiny grayscale thumbnail of a region (or the whole screen) for pixel-level comparison."""
    region = img if box is None else img.crop(tuple(clamp_box(box, img.size)))
    if region.width < 1 or region.height < 1:
        return bytes(SIG_SIZE * SIG_SIZE)
    return region.convert("L").resize((SIG_SIZE, SIG_SIZE), Image.BILINEAR).tobytes()


def sig_diff(a: bytes, b: bytes) -> float:
    """Mean absolute difference (0-255) between two signatures."""
    if not a or not b or len(a) != len(b):
        return 255.0
    return sum(abs(x - y) for x, y in zip(a, b)) / len(a)


CHANGE_LEVEL = 24  # per-pixel grayscale difference that counts as a real change


def sig_changed_pixels(a: bytes, b: bytes) -> int:
    """How many signature pixels changed noticeably. Counting (not averaging) catches small UI changes
    like a toggled checkbox that a mean would wash out."""
    if not a or not b or len(a) != len(b):
        return len(a or b or b"x")
    return sum(1 for x, y in zip(a, b) if abs(x - y) > CHANGE_LEVEL)


def changed_pixels(a: Image.Image, b: Image.Image, size: tuple[int, int] = (160, 100)) -> int:
    """How many pixels of the downscaled frames changed noticeably."""
    da = a.convert("L").resize(size)
    db = b.convert("L").resize(size)
    hist = ImageChops.difference(da, db).histogram()
    return sum(hist[CHANGE_LEVEL + 1 :])


def frame_diff(a: Image.Image, b: Image.Image) -> float:
    """Mean absolute difference (0-255) between two downscaled frames."""
    size = (160, 100)
    da = a.convert("L").resize(size)
    db = b.convert("L").resize(size)
    return ImageStat.Stat(ImageChops.difference(da, db)).mean[0]
