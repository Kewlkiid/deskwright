"""The front window's elements from macOS Accessibility: role, label and exact frame for each button, field, row...

Native apps (Maps, App Store, Finder, Settings) describe their UI this way, so these become extra grounding candidates
next to SAM's boxes and on-screen text; Spark still picks the target among them. Electron apps (Discord) only build
the tree once asked (AXManualAccessibility). Needs the Accessibility permission Deskwright already has.
Frames are global logical points (top-left origin), like the rest of the screen code.
"""
from __future__ import annotations

import sys
import time
from dataclasses import dataclass

try:
    if sys.platform != "darwin":
        raise ImportError
    import ApplicationServices as AS
    from AppKit import NSWorkspace
except ImportError:
    AS = None

# Roles worth clicking or typing into; containers are walked through but not offered.
USEFUL = {"AXButton", "AXTextField", "AXSearchField", "AXTextArea", "AXCheckBox", "AXRadioButton", "AXPopUpButton",
          "AXMenuButton", "AXLink", "AXRow", "AXCell", "AXStaticText", "AXImage", "AXTab", "AXTabGroup",
          "AXComboBox", "AXSlider", "AXDisclosureTriangle", "AXOutlineRow", "AXMenuItem", "AXSegmentedControl",
          "AXIncrementor", "AXSwitch", "AXToolbarButton"}
MAX_NODES = 1500
MAX_SECONDS = 0.6
_electron_on: set[int] = set()


@dataclass
class AXElement:
    role: str
    label: str
    box: list[float]  # global logical [x1, y1, x2, y2]


def available() -> bool:
    return AS is not None


def _attr(el, name):
    err, value = AS.AXUIElementCopyAttributeValue(el, name, None)
    return value if err == 0 else None


def _frame(el) -> list[float] | None:
    pos, size = _attr(el, "AXPosition"), _attr(el, "AXSize")
    if pos is None or size is None:
        return None
    ok1, p = AS.AXValueGetValue(pos, AS.kAXValueCGPointType, None)
    ok2, s = AS.AXValueGetValue(size, AS.kAXValueCGSizeType, None)
    if not (ok1 and ok2) or s.width < 3 or s.height < 3:
        return None
    return [p.x, p.y, p.x + s.width, p.y + s.height]


def _label(el) -> str:
    for name in ("AXTitle", "AXDescription", "AXValue", "AXPlaceholderValue", "AXHelp"):
        v = _attr(el, name)
        if isinstance(v, str) and v.strip():
            return v.strip()[:120]
    return ""


def _pid(app: str) -> int | None:
    name = app.lower()
    for a in NSWorkspace.sharedWorkspace().runningApplications():
        if (a.localizedName() or "").lower() == name:
            return a.processIdentifier()
    return None


def elements(app: str) -> list[AXElement]:
    """Elements of `app`'s front window (empty when Accessibility can't reach it)."""
    if AS is None or not app:
        return []
    pid = _pid(app)
    if pid is None:
        return []
    root = AS.AXUIElementCreateApplication(pid)
    if pid not in _electron_on:
        # Chromium/Electron apps build their tree only for assistive tech that asks; harmless elsewhere.
        AS.AXUIElementSetAttributeValue(root, "AXManualAccessibility", True)
        _electron_on.add(pid)
    window = _attr(root, "AXFocusedWindow") or (_attr(root, "AXWindows") or [None])[0]
    if window is None:
        return []
    out: list[AXElement] = []
    stack, seen, end = [window], 0, time.time() + MAX_SECONDS
    while stack and seen < MAX_NODES and time.time() < end:
        el = stack.pop()
        seen += 1
        role = _attr(el, "AXRole") or ""
        if role in USEFUL:
            box = _frame(el)
            label = _label(el)
            if box and (label or role not in ("AXStaticText", "AXImage", "AXRow", "AXCell")):
                out.append(AXElement(role=role, label=label, box=box))
        kids = _attr(el, "AXChildren") or []
        stack.extend(reversed(list(kids)))
    return out


SCROLLABLE = {"AXScrollArea", "AXList", "AXOutline", "AXTable", "AXBrowser"}


def scroll_areas(app: str) -> list[AXElement]:
    """The front window's scrollable panes (Discord: "Channels", "Messages in support", "Members"), largest last."""
    if AS is None or not app:
        return []
    pid = _pid(app)
    if pid is None:
        return []
    root = AS.AXUIElementCreateApplication(pid)
    window = _attr(root, "AXFocusedWindow") or (_attr(root, "AXWindows") or [None])[0]
    if window is None:
        return []
    out, stack, seen, end = [], [window], 0, time.time() + MAX_SECONDS
    while stack and seen < 3000 and time.time() < end:
        el = stack.pop()
        seen += 1
        role = _attr(el, "AXRole") or ""
        if role in SCROLLABLE:
            box = _frame(el)
            if box and box[2] - box[0] > 40 and box[3] - box[1] > 60:
                out.append(AXElement(role=role, label=_label(el), box=box))
        stack.extend(reversed(list(_attr(el, "AXChildren") or [])))
    return sorted(out, key=lambda e: (e.box[2] - e.box[0]) * (e.box[3] - e.box[1]))


def press_menu(app: str, path: list[str]) -> bool:
    """Press a menu-bar item by its titles, e.g. ["File", "Open…"]. Exact, no vision."""
    if AS is None:
        return False
    pid = _pid(app)
    if pid is None:
        return False
    node = _attr(AS.AXUIElementCreateApplication(pid), "AXMenuBar")
    for i, title in enumerate(path):
        if node is None:
            return False
        want = title.strip().lower().rstrip(".…")
        found = None
        for kid in _attr(node, "AXChildren") or []:
            t = (_attr(kid, "AXTitle") or "").strip().lower().rstrip(".…")
            if t == want or (want and t.startswith(want)):
                found = kid
                break
        if found is None:
            return False
        if i == len(path) - 1:
            return AS.AXUIElementPerformAction(found, "AXPress") == 0
        # Menu bar items and submenus hold their items in a child AXMenu.
        menus = [k for k in (_attr(found, "AXChildren") or []) if _attr(k, "AXRole") == "AXMenu"]
        node = menus[0] if menus else found
    return False
