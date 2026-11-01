"""Browser-only SDK calls (Google Chrome with the agent extension): open a URL, read network responses, run JS."""
from __future__ import annotations

from .context import ACTION_LOCK, current


def open_url(url: str, new_tab: bool = False) -> None:
    """Open a URL in Google Chrome and wait for the page to load (new_tab=True opens it in a new tab).
    Works without the extension too, by typing into Chrome's address bar."""
    from ..browser.bridge import get_bridge

    ctx = current()
    with ACTION_LOCK:
        ctx.check_stop()
        ctx.status(f"Opening {url}")
        bridge = get_bridge()
        if bridge is not None and bridge.connected:
            # The extension's own window comes to the front (open_app could pick a different Chrome).
            r = bridge.call("navigate", timeout=30, url=url, new_tab=new_tab, focus=not ctx.dry_run)
            ctx.browser_used = True
            ctx.log(f"open_url({url!r}) -> {r.get('url')} ({r.get('status')})")
        else:
            from .apps import open_app
            from .raw import hotkey, press, type_text

            open_app("Google Chrome")
            if new_tab:
                hotkey("cmd", "t")
            hotkey("cmd", "l")
            type_text(url)
            press("enter")
        ctx.set_scope("Google Chrome")
        ctx.pending = None
        ctx.settle(3.0)
        ctx.metrics.steps += 1
        ctx.push_metrics()


def network_response(url_contains: str, method: str | None = None, timeout: float = 10.0):
    """Return the body of the page's most recent network response whose URL contains `url_contains`
    (optionally only this HTTP method), made after the last browser action. JSON comes back as dicts/lists.
    Use it to get values the page received, e.g. a created item's id:
        click("Save button", expect="invoice saved message")
        invoice = network_response("/api/invoices", method="POST")
        show(f"Created invoice {invoice['id']}")
    Waits up to `timeout` seconds for the response to arrive."""
    from ..browser.backend import require_browser
    from ..browser.bridge import BrowserError

    ctx = current()
    b = require_browser(ctx, need_focus=False)
    b.ensure_capture(ctx)
    ctx.status(f"Waiting for a network response from {url_contains}")
    r = b.bridge.call("net_query", timeout=timeout + 5, since=ctx.browser_mark, url_contains=url_contains,
                      method=method, types=["XHR", "Fetch", "Document"], wait_ms=int(timeout * 1000), bodies=1)
    entries = r.get("entries") or []
    if not entries:
        raise BrowserError(
            f"No network response matching {url_contains!r}" + (f" ({method})" if method else "") +
            f" arrived within {timeout:.0f}s of the last action",
            fix="Check that the previous action really triggered that request; use a shorter URL fragment.",
            detail={"url_contains": url_contains, "method": method},
        )
    e = entries[0]
    ctx.log(f"network_response({url_contains!r}) -> {e['method']} {e['url'][:100]} {e.get('status')}")
    return e.get("body")


def page_js(code: str):
    """Run JavaScript in the current Chrome page and return its (JSON-serializable) result. `code` is an expression
    ("document.title") or statements with a return ("return [...document.querySelectorAll('h2')].map(h => h.innerText)").
    Promises are awaited. Prefer the regular actions; use this to read data the page holds but doesn't show."""
    from ..browser.backend import browser_for, require_browser

    ctx = current()
    with ACTION_LOCK:
        b = browser_for(ctx) or require_browser(ctx, need_focus=False)
        ctx.status("Running JavaScript in the page")
        value = b.bridge.call("eval", timeout=20, code=code)
        ctx.log(f"page_js -> {str(value)[:80]!r}")
        return value
