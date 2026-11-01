"""Match a script's target description ("blue 'Save' button at the bottom of the form") to the page's element map.

Cheap and deterministic: quoted text and the remaining content words are compared with each element's names
(accessible name, label, text, placeholder, ...). A clear winner is used directly; otherwise the best candidates go
to the vision model as a numbered text list (no screenshot).
"""
from __future__ import annotations

import re

# Words that describe looks or kind rather than identity.
FILLER = {
    "the", "a", "an", "on", "in", "at", "of", "to", "for", "with", "and", "or", "that", "this", "which", "says",
    "named", "called", "labeled", "labelled", "label", "button", "btn", "field", "input", "box", "textbox", "link",
    "icon", "menu", "item", "tab", "area", "text", "page", "form", "section", "dialog", "window", "panel", "control",
    "blue", "red", "green", "gray", "grey", "black", "white", "orange", "purple", "yellow", "primary", "main", "big",
    "small", "large", "dropdown", "select", "checkbox", "option", "element", "entry", "top", "bottom", "left",
    "right", "corner", "upper", "lower", "under", "below", "above", "next", "near", "beside", "side", "header",
    "toolbar", "navbar", "bar", "sidebar", "footer",
}
# Ordinals pick one of several look-alikes: never decide those by text alone. Location words ("top right") are
# only hints; they're fine as long as the text match is unique.
ORDINAL = re.compile(r"\b(first|second|third|fourth|fifth|last|nth|row \d+|\d+(st|nd|rd|th))\b", re.I)
QUOTED = re.compile(r"[\"'“”‘’]([^\"'“”‘’]{1,80})[\"'“”‘’]")
TYPE_VERBS = ("type into", "type")
FIELD_CATS = {"input", "textarea", "select"}


def norm(s) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip()


def words(s) -> list[str]:
    return [w for w in norm(s).split() if w]


def names(e: dict) -> list[str]:
    a = e.get("attributes") or {}
    vals = [e.get("accessible_name"), e.get("label"), e.get("text"), a.get("placeholder"), a.get("aria_label"),
            a.get("title"), a.get("alt"), a.get("name"), e.get("id")]
    return [v for v in (norm(x) for x in vals) if v]


def _kind_bonus(e: dict, target: str, verb: str) -> float:
    cat = e.get("category", "")
    t = norm(target)
    is_field = cat in FIELD_CATS or e.get("tag") in ("input", "textarea", "select")
    if verb in TYPE_VERBS:
        return 0.1 if is_field else -0.4
    bonus = 0.0
    if re.search(r"\b(field|input|box|textbox)\b", t) and is_field:
        bonus += 0.1
    if re.search(r"\bbutton\b", t) and cat == "button":
        bonus += 0.1
    if re.search(r"\blink\b", t) and cat in ("a", "link"):
        bonus += 0.1
    if cat == "structural":
        bonus -= 0.3
    return bonus


def score(e: dict, target: str, verb: str = "click") -> float:
    ns = names(e)
    if not ns:
        return 0.0
    quoted = [norm(q) for q in QUOTED.findall(target) if norm(q)]
    best = 0.0
    if quoted:
        for q in quoted:
            for n in ns:
                if n == q:
                    best = max(best, 1.0)
                elif q in n.split(" ") or (q in n and len(q) >= 0.5 * len(n)):
                    best = max(best, 0.85)
                elif n in q and len(n) >= 3:
                    best = max(best, 0.6)
    else:
        want = [w for w in words(target) if w not in FILLER]
        if not want:
            return 0.0
        for n in ns:
            have = set(n.split())
            hit = sum(1 for w in want if w in have)
            if not hit:
                continue
            coverage = hit / len(want)
            precision = hit / len(have)
            # Precision matters: "Save" should prefer a "Save" button over "Rename Save button".
            s = 1.0 if " ".join(want) == n else 0.6 * coverage + 0.4 * precision
            best = max(best, s)
    # Up to 1.2 so an exact name plus the right kind clearly beats a partial match.
    return max(0.0, min(1.2, best + _kind_bonus(e, target, verb))) if best else 0.0


def ranked(entries: list[dict], target: str, verb: str = "click") -> list[tuple[float, dict]]:
    out = [(score(e, target, verb), e) for e in entries]
    out.sort(key=lambda p: (-p[0], p[1].get("offscreen", False)))
    return out


def best(entries: list[dict], target: str, verb: str = "click") -> dict | None:
    """The element when the text alone identifies it beyond doubt, else None."""
    if ORDINAL.search(target):
        return None
    r = ranked(entries, target, verb)
    if not r or r[0][0] < 0.8:
        return None
    if len(r) > 1 and r[1][0] > r[0][0] - 0.2:
        return None
    return r[0][1]


def candidates(entries: list[dict], target: str, verb: str = "click", limit: int = 60) -> list[dict]:
    r = ranked(entries, target, verb)
    scored = [e for s, e in r if s > 0]
    if len(scored) >= 5:
        return scored[:limit]
    # Weak text overlap: let the model see everything near the top of the page order.
    rest = [e for _, e in r if e not in scored and e.get("category") != "structural"]
    return (scored + rest)[:limit]


def describe_line(i: int, e: dict) -> str:
    a = e.get("attributes") or {}
    bits = [e.get("description") or e.get("tag", "element")]
    if e.get("label") and norm(e["label"]) not in norm(bits[0]):
        bits.append(f'label "{e["label"]}"')
    if a.get("placeholder"):
        bits.append(f'placeholder "{a["placeholder"]}"')
    if a.get("href"):
        bits.append(f'href {str(a["href"])[:60]}')
    r = e.get("rect") or {}
    if r:
        bits.append(f"at x={r.get('centerX')}, y={r.get('centerY')}" + (" (scrolled out of view)" if e.get("offscreen") else ""))
    return f"{i}: " + ", ".join(bits)
