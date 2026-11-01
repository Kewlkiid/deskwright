"""Prompt-driven actions: find the target, then act.

In Chrome with the agent extension in front, the page's DOM comes first (browser cache, element map, model pick
from the map) and the action is a DOM event. Everywhere else, and when the map can't resolve the target: position
cache, else SAM 3.1 with grid grounding as backup, then the real mouse and keyboard.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from PIL import Image

from ..config import config
from ..screen import capture as cap
from ..screen import input as inp
from ..screen.fingerprint import frame_diff
from .context import ACTION_LOCK, RunContext, current
from .errors import ElementNotFoundError, FieldChangedError, NoChangeError, UserDeclinedError
from .raw import run_input
from .safety import is_sensitive

if TYPE_CHECKING:
    from ..browser.backend import Browser, Element

TYPE_CHUNK = 20


def browser_for(ctx: RunContext):
    """The Chrome backend when Chrome with the extension is in front (imported late: the browser package imports
    the SDK's errors)."""
    from ..browser.backend import browser_for as get

    return get(ctx)


@dataclass
class Found:
    box: list
    point: tuple[float, float]
    shot: cap.Shot
    from_cache: bool
    cached_expect: str = ""  # expectation remembered with a cached position
    mask: Image.Image | None = None


def settle_previous(ctx: RunContext, shot: cap.Shot, browser: Browser | None = None):
    """Check the previous action's written expectation on this screenshot: from the page text in Chrome when that
    settles it, else Spark on the screenshot. Without a written expectation, a pixel-change check."""
    p = ctx.pending
    if p is None or not p.expect:
        ctx.resolve_pending(shot)
        return
    ctx.status(f"Checking: {p.expect}")
    v = browser.check(ctx, p.expect) if browser else None
    if v is None:
        v = ctx.models.vision.check(shot.image, p.expect)
    ctx.resolve_pending(shot, v["result"], v["reason"])


def find(ctx: RunContext, target: str, action: str = "click", raise_missing: bool = True) -> Found | None:
    """Ground `target` on a fresh screenshot. Also settles the previous action's expectation."""
    shot = ctx.capture()
    window = ctx.window()
    entry = ctx.cache.lookup(window, shot.image, target)
    if entry is not None:
        # Cached: no model looks at this screen, so verify the previous action by pixel diff.
        ctx.resolve_pending(shot)
        avg_t, avg_c = ctx.cache.avg_miss()
        ctx.metrics.record_cache(True, saved_calls=2, saved_time=avg_t, saved_cost=avg_c)
        ctx.emit("cache_hit", target=target, line=ctx.current_line, segment=ctx.segment, hits=entry.hits)
        # Click where the element was found, not the middle of its box: grid boxes can be wider than the element.
        return Found(entry.box, entry.point or cap.box_center(entry.box), shot, True, entry.expect or "")

    t0, c0 = ctx.metrics.model_time, ctx.metrics.cost
    settle_previous(ctx, shot)
    grounder = getattr(ctx.models.grounder, "label", "SAM 3.1")
    ctx.status(f"Looking for {target}")
    ctx.emit("vision_scan", target=target, line=ctx.current_line, segment=ctx.segment, grounder=grounder)
    g = ctx.models.grounder.locate(shot.image, target)
    if g.found and ctx.in_panel(shot, g.point):
        g.found = False
        g.reason = "It is behind the agent's own panel on the right side of the screen."
    if not g.found:
        ctx.metrics.record_cache(False)
        ctx.emit("vision_miss", target=target, reason=g.reason)
        if not raise_missing:
            return None
        raise ElementNotFoundError(
            f'Could not find "{target}" on screen. {g.reason}'.strip(),
            screenshot=shot.image,
            detail={"target": target, "seen": g.reason},
        )
    ctx.emit(
        "sam_mask",
        target=target,
        box=shot.box_to_logical(g.box),
        point=list(shot.to_logical(*g.point)),
        refined=True,
        grounder=g.label or grounder,
        mask=cap.mask_overlay(g.mask, g.box, shot.scale, shot.origin) if g.mask is not None else None,
    )
    if g.label and g.label != grounder:
        ctx.log(f'found "{target}" with {g.label} after {grounder} missed')
    ctx.cache.put(window, shot.image, target, g.box, point=g.point)
    ctx.cache.record_miss(ctx.metrics.model_time - t0, ctx.metrics.cost - c0)
    ctx.metrics.record_cache(False)
    return Found(g.box, g.point, shot, False, mask=g.mask)


def announce(ctx: RunContext, f: Found, target: str, verb: str, expect: str | None):
    try:
        thumb = cap.thumbnail_with_outline(f.shot.image, f.box, f.mask)
    except Exception:
        thumb = None
    ctx.emit(
        "element_found",
        target=target,
        verb=verb,
        line=ctx.current_line,
        segment=ctx.segment,
        box=f.shot.box_to_logical(f.box),
        point=list(f.shot.to_logical(*f.point)),
        from_cache=f.from_cache,
        thumbnail=thumb,
        expect=expect or f.cached_expect,
    )
    ctx.status(f"{verb.capitalize()} {target}")


def present(ctx: RunContext, f: Found, kind: str):
    """Give the on-screen overlay a beat to show what was found, then signal the pointer action."""
    ctx.sleep(config.show_delay * (0.5 if f.from_cache else 1.0))
    ctx.emit("pointer", kind=kind, point=list(f.shot.to_logical(*f.point)))


def require_confirmation(ctx: RunContext, verb: str, target: str, expect: str | None, confirm: bool, extra: str = ""):
    if confirm or is_sensitive(target, expect, extra):
        summary = f"{verb.capitalize()} “{target}”" + (f"\nExpected result: {expect}" if expect else "") + (
            f"\n{extra}" if extra else ""
        )
        ctx.status(f"Waiting for confirmation: {verb} {target}")
        if not ctx.host.confirm(summary, ctx.stop_event):
            raise UserDeclinedError(f"User declined: {verb} {target}")
        ctx.check_stop()


def browser_find(ctx: RunContext, b: Browser, target: str, verb: str) -> tuple[Element, cap.Shot, list | None] | None:
    """Resolve `target` in the page and show it on screen. None when the page map can't resolve it."""
    shot = ctx.capture()
    settle_previous(ctx, shot, b)
    el = b.resolve(ctx, target, verb)
    if el is None:
        return None
    b.reveal(el)
    logical = b.screen_box(el.rect)
    box = shot.logical_to_image(logical) if logical else None
    ctx.emit(
        "element_found",
        target=target,
        verb=verb,
        line=ctx.current_line,
        segment=ctx.segment,
        box=logical,
        point=[(logical[0] + logical[2]) / 2, (logical[1] + logical[3]) / 2] if logical else None,
        from_cache=el.from_cache,
        thumbnail=None,
        source="dom",
    )
    ctx.status(f"{verb.capitalize()} {target}")
    return el, shot, box


def _browser_present(ctx: RunContext, el: Element, box: list | None, shot: cap.Shot, kind: str):
    """Same look as an on-screen action: the overlay box, the real pointer gliding onto the element, the ripple.
    The action itself is a DOM event; the pointer move is only so people can follow along."""
    ctx.sleep(config.show_delay * (0.5 if el.from_cache else 1.0))
    if not box:
        return
    x, y = shot.to_logical((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)
    if not config.browser_force:  # a forced (background) test Chrome isn't where the pointer would go
        try:
            run_input(inp.move, x, y)
        except Exception:  # noqa: BLE001 - purely visual
            pass
    ctx.emit("pointer", kind=kind, point=[x, y])


BROWSER_CLICK = {"click": "single", "double-click": "double", "right-click": "right", "hover over": "hover"}


def _browser_pointer(ctx: RunContext, b: Browser, target: str, verb: str, expect: str | None, confirm: bool,
                     require_change: bool) -> bool:
    found = browser_find(ctx, b, target, verb)
    if found is None:
        return False
    el, shot, box = found
    require_confirmation(ctx, verb, target, expect, confirm)
    _browser_present(ctx, el, box, shot, "hover" if verb == "hover over" else "click")
    b.mark_network(ctx)
    before = b.signature()
    b.click(el, BROWSER_CLICK[verb])
    ctx.metrics.steps += 1
    ctx.log(f'{verb} "{target}" via the page DOM ({el.selector}) [{el.via}]')
    # Judge "did anything happen" from the page itself (DOM and network), not from screen pixels.
    changed = b.settle(ctx, before)
    ctx.invalidate_window()
    if require_change and not expect and not changed and before is not None:
        raise NoChangeError(f'Nothing changed in the page after {verb} "{target}"', detail={"target": target})
    ctx.set_pending(shot, expect, f'{verb} "{target}"', box, explicit=bool(expect), require_change=False)
    ctx.push_metrics()
    return True


def _pointer_action(target: str, verb: str, expect: str | None, confirm: bool, button: str = "left",
                    clicks: int = 1, require_change: bool = True):
    ctx = current()
    with ACTION_LOCK:
        ctx.check_stop()
        b = browser_for(ctx)
        if b and _browser_pointer(ctx, b, target, verb, expect, confirm, require_change):
            return
        f = find(ctx, target, verb)
        announce(ctx, f, target, verb, expect)
        require_confirmation(ctx, verb, target, expect, confirm)
        present(ctx, f, "hover" if verb == "hover over" else "click")
        x, y = f.shot.to_logical(*f.point)
        if verb == "hover over":
            run_input(inp.move, x, y)
        else:
            run_input(inp.click, x, y, button, clicks)
        ctx.metrics.steps += 1
        ctx.log(f'{verb} "{target}" at ({x:.0f},{y:.0f}) [{"cache" if f.from_cache else "spark+sam"}]')
        ctx.settle()
        ctx.invalidate_window()
        ctx.set_pending(f.shot, expect or f.cached_expect, f'{verb} "{target}"', f.box,
                        explicit=bool(expect), require_change=require_change)
        ctx.push_metrics()


def click(target: str, expect: str | None = None, confirm: bool = False) -> None:
    """Click the element described by `target` (e.g. "blue Save button at the bottom of the form").
    expect: one line describing what should visibly happen next; checked on the next screenshot.
    confirm=True asks the user first (always forced for send/submit/purchase/delete actions)."""
    _pointer_action(target, "click", expect, confirm)


def double_click(target: str, expect: str | None = None, confirm: bool = False) -> None:
    """Double-click the described element."""
    _pointer_action(target, "double-click", expect, confirm, clicks=2)


def right_click(target: str, expect: str | None = None, confirm: bool = False) -> None:
    """Right-click the described element (usually opens a context menu)."""
    _pointer_action(target, "right-click", expect, confirm, button="right")


def move_mouse(target: str, expect: str | None = None, confirm: bool = False) -> None:
    """Move the mouse over the described element (hover), e.g. to reveal a menu or tooltip."""
    _pointer_action(target, "hover over", expect, confirm, require_change=False)


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()


def _field_ok(ctx: RunContext, field_box: list, typed: str, shot: cap.Shot) -> bool:
    text = ctx.models.vision.read_text(cap.crop(shot.image, cap.expand_box(field_box, shot.size, pad=12)))
    tail = _norm(typed)[-12:]
    return bool(tail) and tail in _norm(text)


def _verify_field(ctx: RunContext, target: str, f: Found, typed: str, window: str, last_small: Image.Image):
    """Between chunks: cheap checks first; only call the model if something looks off."""
    shot = ctx.capture()
    ctx.invalidate_window()
    window_changed = ctx.window() != window
    big_change = frame_diff(last_small, shot.image) > 2.5
    if not window_changed and not big_change:
        return shot
    if not window_changed and _field_ok(ctx, f.box, typed, shot):
        return shot  # e.g. an autocomplete popup opened; the field still has our text
    ctx.status(f"Typing interrupted, re-checking: {target}")
    res = ctx.models.grounder.locate(shot.image, target)
    if not res.found:
        raise FieldChangedError(
            f'The field "{target}" disappeared while typing (typed so far: {typed!r})',
            screenshot=shot.image,
            detail={"typed_so_far": typed},
        )
    x, y = shot.to_logical(*res.point)
    run_input(inp.click, x, y)
    run_input(inp.caret_to_end)
    ctx.sleep(0.2)
    shot = ctx.capture()
    if not _field_ok(ctx, res.box, typed, shot):
        raise FieldChangedError(
            f'The field "{target}" no longer ends with the text already typed ({typed!r})',
            screenshot=shot.image,
            detail={"typed_so_far": typed},
        )
    f.box = res.box
    return shot


def _browser_type(ctx: RunContext, b: Browser, target: str, text: str, expect: str | None, confirm: bool,
                  clear: bool) -> bool:
    found = browser_find(ctx, b, target, "type into")
    if found is None:
        return False
    el, shot, box = found
    require_confirmation(ctx, "type into", target, expect, confirm)
    _browser_present(ctx, el, box, shot, "type")
    b.mark_network(ctx)
    result = b.type(el, text, clear)
    value = result.get("value")
    # Selects report the option's value, not its text; only text fields can be checked this way.
    if isinstance(value, str) and result.get("tag") in ("input", "textarea") and not _norm(value).endswith(_norm(text)):
        raise FieldChangedError(
            f'The field "{target}" shows {value!r} after typing {text!r}',
            detail={"typed_so_far": text, "field_value": value},
        )
    ctx.metrics.steps += 1
    ctx.log(f'type_into "{target}": {text[:40]!r} via the page DOM ({el.selector}) [{el.via}]')
    b.settle(ctx, None, 1.0)
    ctx.set_pending(shot, expect, f'typing into "{target}"', box, explicit=bool(expect), require_change=False)
    ctx.push_metrics()
    return True


def type_into(target: str, text, expect: str | None = None, confirm: bool = False, clear: bool = False) -> None:
    """Click the described text field and type `text` into it. clear=True empties the field first.
    Long text is typed in chunks; if focus moves away mid-entry the field is re-focused, and if the field
    changed, FieldChangedError is raised instead of typing into the wrong place."""
    ctx = current()
    text = "" if text is None else str(text)
    with ACTION_LOCK:
        ctx.check_stop()
        b = browser_for(ctx)
        if b and _browser_type(ctx, b, target, text, expect, confirm, clear):
            return
        f = find(ctx, target, "type into")
        announce(ctx, f, target, "type into", expect)
        require_confirmation(ctx, "type into", target, expect, confirm)
        present(ctx, f, "type")
        x, y = f.shot.to_logical(*f.point)
        run_input(inp.click, x, y)
        ctx.sleep(0.15)
        if clear:
            run_input(inp.select_all)
            run_input(inp.press, "backspace")
        window = ctx.window()
        typed = ""
        last = cap.grab().image
        chunks = [text[i : i + TYPE_CHUNK] for i in range(0, len(text), TYPE_CHUNK)] or [""]
        for i, chunk in enumerate(chunks):
            ctx.check_stop()
            if i > 0 and not ctx.dry_run:
                last = _verify_field(ctx, target, f, typed, window, last).image
            if chunk:
                run_input(inp.type_text, chunk)
            typed += chunk
        ctx.metrics.steps += 1
        ctx.log(f'type_into "{target}": {text[:40]!r} [{"cache" if f.from_cache else "spark+sam"}]')
        ctx.settle(1.0)
        ctx.set_pending(f.shot, expect, f'typing into "{target}"', f.box, explicit=bool(expect), require_change=False)
        ctx.push_metrics()


def drag(from_target: str, to_target: str, expect: str | None = None, confirm: bool = False) -> None:
    """Drag from one described element to another."""
    ctx = current()
    with ACTION_LOCK:
        ctx.check_stop()
        a = find(ctx, from_target, "drag")
        announce(ctx, a, from_target, "drag", expect)
        b = find(ctx, to_target, "drop onto")
        announce(ctx, b, to_target, "drop onto", expect)
        require_confirmation(ctx, "drag", f"{from_target} -> {to_target}", expect, confirm)
        present(ctx, a, "drag")
        x1, y1 = a.shot.to_logical(*a.point)
        x2, y2 = b.shot.to_logical(*b.point)
        run_input(inp.drag, x1, y1, x2, y2)
        ctx.metrics.steps += 1
        ctx.log(f'drag "{from_target}" -> "{to_target}"')
        ctx.settle()
        ctx.set_pending(b.shot, expect or b.cached_expect, f'drag "{from_target}" onto "{to_target}"', b.box,
                        explicit=bool(expect))
        ctx.push_metrics()


def scroll_until(target: str, direction: str = "down", max_scrolls: int = 15) -> None:
    """Scroll (at the current mouse position) until the described element is visible.
    Raises ElementNotFoundError if it never appears or the content stops moving."""
    ctx = current()
    amount = -5 if direction.lower().startswith("d") else 5
    with ACTION_LOCK:
        b = browser_for(ctx)
        if b and browser_find(ctx, b, target, "scroll to") is not None:  # the page scrolls it into view
            ctx.pending = None
            return
        for _ in range(max_scrolls):
            ctx.check_stop()
            f = find(ctx, target, "scroll to", raise_missing=False)
            if f is not None:
                announce(ctx, f, target, "found", None)
                ctx.pending = None
                return
            before = ctx.last_shot.image if ctx.last_shot else None
            run_input(inp.scroll, amount)
            ctx.metrics.steps += 1
            ctx.settle(1.0)
            after = cap.grab().image
            if before is not None and frame_diff(before, after) < 0.3:
                break
        raise ElementNotFoundError(
            f'Scrolled {direction} but "{target}" never appeared',
            screenshot=ctx.last_shot.image if ctx.last_shot else None,
            detail={"target": target},
        )


def use_grounding(method: str) -> None:
    """Choose how elements are found for the rest of this run: "sam" (SAM 3.1 only), "grid" (labelled-grid
    grounding on a vision model only), or "auto" (default: SAM first, grid if SAM misses; switches to grid first
    after SAM misses 3 times). Use "grid" when SAM keeps failing on an app, e.g. tiny icons or unusual widgets."""
    ctx = current()
    router = ctx.models.grounder
    if not hasattr(router, "set_mode"):
        return
    router.set_mode(method)
    ctx.log(f"grounding method: {router.mode}")
    ctx.status(f"Finding elements with: {router.mode}")
