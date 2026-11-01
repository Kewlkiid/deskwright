"""Browser backend for the Agent SDK: when Chrome with the extension is in front, SDK actions use the page's DOM.

Order for finding a target: browser cache (selector re-checked in the live DOM) -> element map matched by text ->
the vision model picking from the map as a text list -> None, and the caller falls back to screenshot grounding.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from ..config import config
from . import match
from .bridge import BrowserError, BrowserUnavailableError, get_bridge

CHROME_APPS = ("Google Chrome", "Chromium")


def page_key(url: str) -> str:
    """Cache key for a page: origin + path with ids generalized (/invoices/123 and /invoices/456 share entries)."""
    u = urlsplit(url or "")
    path = re.sub(r"/[0-9a-f]{8,}(?=/|$)", "/#", u.path or "/", flags=re.I)
    path = re.sub(r"/\d+(?=/|$)", "/#", path)
    return f"{u.scheme}://{u.netloc}{path}"


@dataclass
class Element:
    selector: str
    name: str = ""
    rect: dict = field(default_factory=dict)
    index: int | None = None  # valid only for the scan it came from
    from_cache: bool = False
    via: str = "dom"  # "cache", "dom" (text match) or "model" (picked from the map)
    entry: dict = field(default_factory=dict)

    def ref(self) -> dict:
        return {"selector": self.selector, **({"index": self.index} if self.index is not None else {})}


class Browser:
    def __init__(self, bridge, status: dict):
        self.bridge = bridge
        self.status = status
        self._viewport: dict | None = None

    # Plumbing --------------------------------------------------------------
    @property
    def url(self) -> str:
        return (self.status.get("tab") or {}).get("url") or ""

    def page(self, cmd: str, timeout: float = 10.0, **params):
        return self.bridge.call("page", timeout=timeout + 2, cmd=cmd, params=params, timeout_ms=int(timeout * 1000))

    def viewport(self) -> dict:
        if self._viewport is None:
            self._viewport = self.page("viewport")
        return self._viewport

    def screen_box(self, rect: dict) -> list[float] | None:
        """Viewport CSS rect -> logical screen box, for the on-screen overlay (assumes 100% page zoom)."""
        if not rect:
            return None
        try:
            v = self.viewport()
            x0 = v["screenX"] + max(0, v["outerWidth"] - v["innerWidth"]) / 2
            y0 = v["screenY"] + max(0, v["outerHeight"] - v["innerHeight"])
        except (BrowserError, KeyError, TypeError):
            return None
        return [x0 + rect["x"], y0 + rect["y"], x0 + rect["x"] + rect["width"], y0 + rect["y"] + rect["height"]]

    def mark_network(self, ctx):
        """Remember the network position before an action, so network_response() finds what the action caused."""
        if ctx.browser_capture:
            try:
                ctx.browser_mark = self.bridge.call("net_mark", timeout=3)["seq"]
            except BrowserError:
                pass

    def ensure_capture(self, ctx):
        if not ctx.browser_capture:
            r = self.bridge.call("net_start", timeout=5)
            ctx.browser_capture = True
            ctx.browser_mark = r.get("seq", 0)

    # Finding ----------------------------------------------------------------
    def resolve(self, ctx, target: str, verb: str = "click") -> Element | None:
        page = page_key(self.url)
        cached = ctx.cache.browser_lookup(page, target)
        if cached:
            probe = self.page("probe", selector=cached["selector"], name=cached["name"])
            if probe.get("found"):
                ctx.cache.browser_hit(page, target)
                ctx.metrics.record_cache(True, saved_calls=1)
                ctx.emit("cache_hit", target=target, line=ctx.current_line, segment=ctx.segment, hits=cached["hits"] + 1)
                return Element(cached["selector"], cached["name"], probe.get("rect") or {}, from_cache=True, via="cache")
            ctx.cache.browser_invalidate(page, target)

        entries = self.page("get_map", layer="interactive", offscreen=True)["elements"]
        if verb == "read":
            # Static text has its own numbering; it is acted on by selector only.
            entries = entries + [{**e, "index": None} for e in self.page("get_map", layer="static")["elements"]]
        pick, via = match.best(entries, target, verb), "dom"
        if pick is None:
            cands = match.candidates(entries, target, verb)
            if cands:
                ctx.status(f"Choosing {target} from the page's elements")
                lines = [match.describe_line(i, e) for i, e in enumerate(cands)]
                i = ctx.models.vision.pick_element(target, verb, lines, self.url)
                if i is not None and 0 <= i < len(cands):
                    pick, via = cands[i], "model"
        ctx.metrics.record_cache(False)
        if pick is None:
            ctx.log(f'"{target}" not found in the page map; falling back to the screen')
            return None
        name = pick.get("label") or pick.get("accessible_name") or ""
        if pick.get("category") != "static":
            ctx.cache.browser_put(page, target, pick["selector"], name)
        return Element(pick["selector"], name, pick.get("rect") or {}, index=pick.get("index"), via=via, entry=pick)

    # Acting -----------------------------------------------------------------
    def reveal(self, el: Element) -> dict:
        info = self.page("reveal", **el.ref())
        el.rect = info.get("rect") or el.rect
        return info

    def click(self, el: Element, kind: str = "single") -> dict:
        return self.page("click", kind=kind, **el.ref())

    def type(self, el: Element, text: str, clear: bool = False) -> dict:
        return self.page("type", text=text, clear=clear, **el.ref())

    def read(self, el: Element) -> dict:
        return self.page("read", **el.ref())

    def signature(self) -> dict | None:
        try:
            return self.page("signature", timeout=3)
        except BrowserError:
            return None

    def settle(self, ctx, before: dict | None, max_wait: float = 2.0) -> bool:
        """Wait until the page stops changing after an action. Returns whether it changed at all (DOM or network)."""
        import time

        ctx.sleep(0.25)
        prev, changed = self.signature(), False
        end = time.time() + max_wait
        while time.time() < end:
            changed = changed or (prev is not None and prev != before)
            ctx.sleep(0.2)
            cur = self.signature()
            if cur == prev:
                break
            prev = cur
        changed = changed or (prev is not None and prev != before)
        if not changed and ctx.browser_capture:
            try:
                changed = bool(self.bridge.call("net_query", timeout=3, since=ctx.browser_mark, limit=1, bodies=0)["entries"])
            except BrowserError:
                pass
        return changed

    # Questions --------------------------------------------------------------
    def network_lines(self, ctx, limit: int = 12) -> list[str]:
        if not ctx.browser_capture:
            return []
        try:
            r = self.bridge.call("net_query", timeout=5, since=ctx.browser_mark, types=["XHR", "Fetch", "Document"],
                                 limit=limit, bodies=0)
        except BrowserError:
            return []
        return [f"{e['method']} {e['url'][:120]} -> {e.get('status') or ('failed' if e.get('failed') else '?')}"
                for e in r.get("entries", [])]

    def check(self, ctx, condition: str) -> dict | None:
        """Judge a condition from the page's text (and recent network calls). result None means "can't tell"."""
        try:
            pt = self.page("page_text", max=6000)
        except BrowserError:
            return None
        r = ctx.models.vision.check_text(condition, pt.get("text", ""), pt.get("url", ""), self.network_lines(ctx))
        return r if r.get("result") is not None else None

    def read_table(self, ctx, target: str, columns: list[str] | None = None) -> tuple[list[str], list[list]] | None:
        tables = self.page("tables", timeout=15).get("tables") or []
        tables = [t for t in tables if t.get("rows")]
        if not tables:
            return None
        if len(tables) == 1:
            t = tables[0]
        else:
            as_entries = [{"index": t["index"], "label": t.get("caption") or "", "text": t.get("heading") or "",
                           "accessible_name": " ".join(t.get("headers") or []), "id": t.get("id"), "category": "table"}
                          for t in tables]
            pick = match.best(as_entries, target, "read")
            if pick is None:
                lines = [f"{i}: table" + (f' captioned "{t["caption"]}"' if t.get("caption") else "") +
                         (f' under heading "{t["heading"]}"' if t.get("heading") else "") +
                         f' with columns {json.dumps(t.get("headers") or [])}, {t.get("total_rows")} rows'
                         for i, t in enumerate(tables)]
                i = ctx.models.vision.pick_element(target, "read", lines, self.url)
                if i is None or not 0 <= i < len(tables):
                    return None
                t = tables[i]
            else:
                t = tables[pick["index"]]
        headers = [h or f"column {i + 1}" for i, h in enumerate(t.get("headers") or [])]
        width = max((len(r) for r in t["rows"]), default=0)
        headers += [f"column {i + 1}" for i in range(len(headers), width)]
        return headers, t["rows"]


def _chrome_in_front(ctx) -> bool:
    app = (ctx.window() or "").split("|")[0]
    return app.startswith(CHROME_APPS)


def browser_for(ctx, need_focus: bool = True) -> Browser | None:
    """The browser backend when Chrome (with the extension) is the app in front, else None."""
    if not config.browser_enabled or config.fake_screen:
        return None
    bridge = get_bridge()
    if bridge is None or not bridge.connected:
        return None
    if need_focus and not config.browser_force and not _chrome_in_front(ctx):
        return None
    try:
        status = bridge.call("status", timeout=3)
    except (BrowserError, BrowserUnavailableError):
        return None
    tab = status.get("tab") or {}
    if not re.match(r"^(https?|file):", tab.get("url") or ""):
        return None
    if need_focus and not config.browser_force and not status.get("focused"):
        return None
    if not status.get("focused"):
        # The agent works in the app in front: bring the extension's Chrome window forward before acting.
        try:
            bridge.call("focus", timeout=3)
            ctx.invalidate_window()
        except (BrowserError, BrowserUnavailableError):
            pass
    ctx.browser_used = True
    return Browser(bridge, status)


def require_browser(ctx, need_focus: bool = True) -> Browser:
    b = browser_for(ctx, need_focus)
    if b is None:
        raise BrowserUnavailableError(
            "This needs Google Chrome in front with the agent extension connected (and a normal web page open)."
        )
    return b
