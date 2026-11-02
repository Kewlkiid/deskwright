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
    ref: object = None  # the AXUIElement itself, to act on it (press, scroll into view, focus)


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
                out.append(AXElement(role=role, label=label, box=box, ref=el))
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


def actions(el: AXElement) -> list[str]:
    if AS is None or el.ref is None:
        return []
    err, names = AS.AXUIElementCopyActionNames(el.ref, None)
    return list(names or []) if err == 0 else []


def perform(el: AXElement, action: str) -> bool:
    """Do one of the element's own actions (AXPress, AXScrollToVisible, AXShowMenu...)."""
    if AS is None or el.ref is None:
        return False
    return AS.AXUIElementPerformAction(el.ref, action) == 0


def focus(el: AXElement) -> bool:
    if AS is None or el.ref is None:
        return False
    return AS.AXUIElementSetAttributeValue(el.ref, "AXFocused", True) == 0


def window_box(app: str) -> list[float] | None:
    """The front window's frame (global logical)."""
    if AS is None:
        return None
    pid = _pid(app)
    if pid is None:
        return None
    root = AS.AXUIElementCreateApplication(pid)
    window = _attr(root, "AXFocusedWindow") or (_attr(root, "AXWindows") or [None])[0]
    return _frame(window) if window is not None else None


def menu_title_box(app: str, title: str) -> list[float] | None:
    """Where a menu-bar title ("File") is on screen (global logical), for showing the press."""
    if AS is None:
        return None
    pid = _pid(app)
    bar = _attr(AS.AXUIElementCreateApplication(pid), "AXMenuBar") if pid is not None else None
    want = title.strip().lower().rstrip(".…")
    for kid in (_attr(bar, "AXChildren") or []) if bar is not None else []:
        t = (_attr(kid, "AXTitle") or "").strip().lower().rstrip(".…")
        if t == want or (want and t.startswith(want)):
            return _frame(kid)
    return None


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


def restore_typed(app: str, typed: str) -> bool:
    """Undo auto-capitalisation/auto-correct of what was just typed into `app`'s focused text field: when the field
    holds `typed` with only its letter case changed ("Deskwright save test" for "deskwright save test"), that span
    is replaced through Accessibility, which doesn't go through auto-correct. True when it fixed something."""
    if AS is None or not typed.strip():
        return False
    pid = _pid(app)
    if pid is None:
        return False
    el = _attr(AS.AXUIElementCreateApplication(pid), "AXFocusedUIElement")
    value = _attr(el, "AXValue") if el is not None else None
    if not isinstance(value, str):
        return False
    i = value.lower().rfind(typed.lower())
    if i < 0 or value[i:i + len(typed)] == typed:
        return False
    rng = AS.AXValueCreate(AS.kAXValueCFRangeType, (i, len(typed)))
    if AS.AXUIElementSetAttributeValue(el, "AXSelectedTextRange", rng) != 0:
        return False
    if AS.AXUIElementSetAttributeValue(el, "AXSelectedText", typed) != 0:
        return False
    after = _attr(el, "AXValue")
    return isinstance(after, str) and typed in after


def focus_thief() -> str | None:
    """When a background system process (not a regular app: a Dictation prompt, a permission alert...) holds the
    keyboard focus, the title or text of its window; keys sent now would go there. None otherwise."""
    if AS is None:
        return None
    from AppKit import NSApplicationActivationPolicyRegular, NSRunningApplication

    app = _attr(AS.AXUIElementCreateSystemWide(), "AXFocusedApplication")
    if app is None:
        return None
    err, pid = AS.AXUIElementGetPid(app, None)
    running = NSRunningApplication.runningApplicationWithProcessIdentifier_(pid) if err == 0 else None
    if running is None or running.activationPolicy() == NSApplicationActivationPolicyRegular:
        return None
    window = _attr(app, "AXFocusedWindow") or (_attr(app, "AXWindows") or [None])[0]
    if window is None:
        return None  # a menu-bar helper without a window doesn't take typing
    texts = [_label(window)] + [_label(k) for k in (_attr(window, "AXChildren") or [])[:8]]
    text = " / ".join(t for t in texts if t)
    return f"{running.localizedName() or 'a system process'}: {text}" if text else (running.localizedName() or "")
