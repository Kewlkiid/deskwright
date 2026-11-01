"""Teach-mode compiler: recorded events -> described steps -> generalized script. It only writes the script: the
first replay finds the elements and fills the cache like any other run.

When the Chrome extension recorded too, its DOM steps (exact labels, selectors, typed values) replace the desktop
recorder's clicks and typing inside Chrome, and the page's API calls are added as network steps so the planner can
return values such as a created item's id with network_response().
"""
from __future__ import annotations

import re
from bisect import bisect_left

from PIL import Image

from ..runner.schema import header_problems
from ..runner.validate import scope_problems, validate
from ..sdk import SDK_NAMES, sdk_reference

DOUBLE_CLICK_GAP = 0.45
AFTER_DELAY = 1.0
CHROME_APPS = ("Google Chrome", "Chromium")
NAV_AFTER_CLICK = 2.0  # a navigation this soon after a click was caused by the click
ID_KEY = re.compile(r"(^|_)(id|uuid|key|number|ref)$|Id$", re.I)
MAX_NETWORK_STEPS = 12


def group_steps(events: list[dict]) -> list[dict]:
    steps: list[dict] = []
    for e in sorted(events, key=lambda e: e["t"]):
        last = steps[-1] if steps else None
        kind = e["type"]
        if kind == "click":
            if (last and last["kind"] in ("click", "double_click") and e["t"] - last["t"] < DOUBLE_CLICK_GAP
                    and abs(e["x"] - last["x"]) < 6 and abs(e["y"] - last["y"]) < 6):
                last["kind"] = "double_click"
                continue
            steps.append({"kind": "right_click" if e.get("button") == "right" else "click", "t": e["t"], "x": e["x"],
                          "y": e["y"], "window": e.get("window", ""), "before": e.get("before"),
                          "scale": e.get("scale", 1.0)})
        elif kind == "char":
            if last and last["kind"] == "type":
                last["text"] += e["char"]
            else:
                steps.append({"kind": "type", "t": e["t"], "text": e["char"], "window": e.get("window", "")})
        elif kind == "key":
            key = e["key"]
            if key == "backspace" and last and last["kind"] == "type" and last["text"]:
                last["text"] = last["text"][:-1]
            elif key == "space" and last and last["kind"] == "type":
                last["text"] += " "
            elif key == "space":
                steps.append({"kind": "type", "t": e["t"], "text": " ", "window": e.get("window", "")})
            else:
                steps.append({"kind": "press", "t": e["t"], "key": key, "window": e.get("window", "")})
        elif kind == "hotkey":
            steps.append({"kind": "hotkey", "t": e["t"], "keys": e["keys"], "window": e.get("window", "")})
        elif kind == "scroll":
            if last and last["kind"] == "scroll":
                last["amount"] += e["dy"]
            else:
                steps.append({"kind": "scroll", "t": e["t"], "amount": e["dy"], "window": e.get("window", "")})
    return steps


def _frame_after(frames: list, t: float) -> str | None:
    if not frames:
        return None
    times = [f[0] for f in frames]
    i = min(bisect_left(times, t), len(frames) - 1)
    return frames[i][1]


def _ids(body, prefix: str = "", out: dict | None = None, depth: int = 0) -> dict:
    """Id-like fields of a JSON response (top two levels), e.g. {"id": 812, "invoice.number": "INV-0042"}."""
    out = {} if out is None else out
    if isinstance(body, dict) and depth < 2:
        for k, v in body.items():
            if isinstance(v, (str, int)) and ID_KEY.search(str(k)):
                out[prefix + str(k)] = v
            elif isinstance(v, dict):
                _ids(v, f"{prefix}{k}.", out, depth + 1)
    return out


def browser_steps(rec: dict) -> list[dict]:
    """Chrome extension events -> steps in the same shape as desktop ones (t in seconds, "source": "chrome")."""
    steps: list[dict] = []
    last_click_t = -1e9
    for e in sorted(rec.get("events") or [], key=lambda e: e.get("t", 0)):
        t = e.get("t", 0) / 1000
        kind = e.get("kind")
        base = {"t": t, "source": "chrome", "page": e.get("url", ""), "selector": e.get("selector")}
        if kind in ("click", "double_click", "right_click"):
            steps.append({**base, "kind": kind, "element": e.get("description") or e.get("name") or e.get("tag"),
                          "name": e.get("name") or ""})
            last_click_t = t
        elif kind in ("input", "select"):
            field = e.get("description") or e.get("name") or "text field"
            # type_into() clicks the field itself, and one field keeps only its final value.
            while steps and steps[-1].get("selector") == e.get("selector") and steps[-1]["kind"] in ("click", "type"):
                steps.pop()
            steps.append({**base, "kind": "type", "field": field, "name": e.get("name") or "",
                          "text": "" if e.get("secret") else str(e.get("value", "")), "secret": bool(e.get("secret"))})
        elif kind == "key":
            steps.append({**base, "kind": "press", "key": str(e.get("key", "")).lower()})
        elif kind == "navigate":
            if e.get("initial"):
                steps.append({**base, "kind": "start_page", "url": e.get("url", "")})
            elif t - last_click_t > NAV_AFTER_CLICK:
                steps.append({**base, "kind": "navigate", "url": e.get("url", "")})
    calls = []
    for c in rec.get("network") or []:
        ids = _ids(c.get("body"))
        if c.get("method", "GET").upper() != "GET" or ids:
            calls.append({"t": c.get("t", 0) / 1000, "source": "chrome", "kind": "network", "method": c.get("method"),
                          "url": c.get("url", "")[:200], "status": c.get("status"), "ids": ids,
                          "response_keys": list(c["body"].keys())[:15] if isinstance(c.get("body"), dict) else []})
    return sorted(steps + calls[-MAX_NETWORK_STEPS:], key=lambda s: s["t"])


def _in_chrome(step: dict) -> bool:
    return str(step.get("window", "")).startswith(CHROME_APPS)


def compile_recording(meta: dict, name: str, description: str, models, emit, browser: dict | None = None) -> dict:
    steps = group_steps(meta["events"])
    if browser and browser.get("events"):
        # The DOM recording is exact inside Chrome: drop the desktop recorder's clicks and typing there.
        steps = [s for s in steps if not (_in_chrome(s) and s["kind"] in ("click", "double_click", "right_click", "type", "press"))]
        steps = sorted(steps + browser_steps(browser), key=lambda s: s["t"])
    frames = meta["frames"]
    out_steps = []
    for n, s in enumerate(steps, 1):
        emit("teach_status", text=f"Understanding step {n}/{len(steps)}")
        item = {"step": n, "kind": s["kind"]}
        if s.get("source") == "chrome":
            item.update({k: v for k, v in s.items() if k not in ("t", "selector", "source")}, app="Google Chrome")
            out_steps.append(item)
            emit("teach_step", step=item)
            continue
        if s["kind"] in ("click", "double_click", "right_click") and s.get("before"):
            scale = s.get("scale") or 1.0
            before = Image.open(s["before"]).convert("RGB")
            after_path = _frame_after(frames, s["t"] + AFTER_DELAY)
            after = Image.open(after_path).convert("RGB") if after_path else before
            px = (int(s["x"] * scale), int(s["y"] * scale))
            d = models.vision.describe_step(before, after, f"{s['kind']} at the red circle", px)
            element = (d.get("element") or f"element near ({s['x']:.0f}, {s['y']:.0f})").strip()
            item.update(element=element, intent=d.get("intent", ""), result=d.get("result", ""))
        elif s["kind"] == "type":
            item.update(text=s["text"], intent=f"type {s['text']!r}", result="the typed text appears in the field")
        elif s["kind"] == "press":
            item.update(key=s["key"], intent=f"press {s['key']}")
        elif s["kind"] == "hotkey":
            item.update(keys=s["keys"], intent="shortcut " + "+".join(s["keys"]))
        elif s["kind"] == "scroll":
            item.update(amount=s["amount"], intent="scroll")
        item["window"] = s.get("window", "")
        out_steps.append(item)
        emit("teach_step", step=item)

    emit("teach_status", text="Writing the script")
    ref = sdk_reference()
    script = models.planner.generalize_recording(name, description, out_steps, ref)
    problems = validate(script, SDK_NAMES) + scope_problems(script) + header_problems(script)
    if problems:
        script = models.planner.repair_validation(f"{name}: {description}", script, problems, ref)
        problems = validate(script, SDK_NAMES) + scope_problems(script) + header_problems(script)
    return {"steps": out_steps, "script": script, "problems": problems}
