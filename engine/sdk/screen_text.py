"""Free yes-answers for "is X on screen" checks: the words are looked up in on-device text recognition and the app's
Accessibility labels before any model is asked. Only ever answers True, and only for plain presence conditions
("the Directions panel is shown", "'Message #support' input is visible"); everything else, and every no, goes to Spark.
"""
from __future__ import annotations

import re

from ..config import config
from ..screen import capture as cap
from ..screen.fingerprint import screen_hash

# Presence words: the condition asks whether something is on screen.
PRESENCE = re.compile(r"\b(visible|shown|showing|shows|displayed|appears?|open|opened|opens|loaded|on screen|present)\b", re.I)
# Anything about state, change or absence needs eyes, not a word lookup.
NEEDS_MODEL = re.compile(
    r"\b(not|no|without|empty|blank|disabled|enabled|selected|highlighted|checked|unchecked|active|focused|"
    r"contains?|typed|entered|sent|posted|saved|deleted|changed|updated|closed|gone|disappear\w*|only|exactly|"
    r"error|failed|success\w*|count|number|more|less|than|before|after|first|last|newest|latest|"
    r"color|colou?r|red|green|blue|says|reads|named)\b", re.I)
FILLER = set("""the a an is are was be been being of in on at to for with and or its it this that these those
visible shown showing shows displayed appear appears open opened opens loaded screen present window page app panel
view area list section now currently which where has have left right top bottom side main center centre upper lower
field fields input inputs box boxes button buttons icon icons tab tabs row rows menu menus dialog sidebar bar toolbar
link links item items label text title header pane form card""".split())  # kinds of element, not words on screen

_cache: dict = {}


def _content_words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9#@'.-]{2,}", text.lower()) if w not in FILLER]


def confirms(ctx, shot: cap.Shot, condition: str) -> bool:
    """True when the condition is a plain "X is shown" and all of X's words (or its quoted text) are on screen."""
    if config.fake_screen or config.fake_models or not PRESENCE.search(condition) or NEEDS_MODEL.search(condition):
        return False
    quoted = [q.strip().lower() for q in re.findall(r"['\"“‘]([^'\"”’]{2,})['\"”’]", condition)]
    words = _content_words(re.sub(r"['\"“‘][^'\"”’]*['\"”’]", " ", condition))
    if not quoted and len(words) < 2:
        return False  # too little to go on
    on_screen = _screen_text(ctx, shot)
    if not on_screen:
        return False
    if any(q not in on_screen for q in quoted):
        return False
    seen = set(re.findall(r"[a-z0-9#@'.-]{2,}", on_screen))
    return all(w in seen or w.rstrip("s") in seen for w in words)


def _screen_text(ctx, shot: cap.Shot) -> str:
    key = screen_hash(shot.image)
    if key in _cache:
        return _cache[key]
    parts: list[str] = []
    try:
        from ..screen import ocr

        parts += [t for _, t in ocr.text_boxes(cap.fit(shot.image, config.model_image_max)[0], accurate=True)]
    except Exception:  # noqa: BLE001
        pass
    try:
        from .actions import ax_elements

        parts += [label for _, _, label in ax_elements(ctx, shot) if label]
    except Exception:  # noqa: BLE001
        pass
    text = " \n ".join(parts).lower()
    if len(_cache) > 50:
        _cache.clear()
    _cache[key] = text
    return text
