"""Live end-to-end check of the Chrome extension in a separate, throwaway Chrome (own profile, own extension copy,
own port and token). It never touches the user's Chrome, extension/config.js, or a running engine, and it blocks
desktop mouse/keyboard input for the whole run.

    python -m engine.tools.browser_check --chrome "/path/to/Chrome for Testing" --out /tmp/check

Steps: load the extension and connect -> overlays on the demo page (map vs live DOM, screenshots of the labels) ->
an SDK script that clicks, types, reads a value and captures a network response -> teach a short task with trusted
CDP input, generalize it with the planner, and replay it. Writes report.json and screenshots to --out.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def block_desktop_input():
    """The check drives Chrome through the DOM only; any desktop input would mean a fallback hit the real screen."""
    from engine.screen import input as inp

    def refuse(*a, **k):
        raise RuntimeError("desktop input attempted during the browser check")

    for name in ("move", "click", "drag", "scroll", "type_text", "press", "hotkey", "select_all", "caret_to_end"):
        setattr(inp, name, refuse)


class CDP:
    """Minimal client for the test Chrome's own DevTools endpoint (trusted input for the teach step)."""

    def __init__(self, port: int):
        from websockets.sync.client import connect

        targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json"))
        page = next(t for t in targets if t["type"] == "page" and t["url"].startswith("http"))
        self.ws = connect(page["webSocketDebuggerUrl"], max_size=None)
        self.n = 0

    def call(self, method: str, **params):
        self.n += 1
        self.ws.send(json.dumps({"id": self.n, "method": method, "params": params}))
        while True:
            r = json.loads(self.ws.recv(timeout=15))
            if r.get("id") == self.n:
                return r.get("result", r)

    def click(self, x: float, y: float):
        for kind in ("mousePressed", "mouseReleased"):
            self.call("Input.dispatchMouseEvent", type=kind, x=x, y=y, button="left", clickCount=1)
        time.sleep(0.4)

    def type(self, text: str):
        self.call("Input.insertText", text=text)
        time.sleep(0.2)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--chrome", default="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    p.add_argument("--out", default=tempfile.mkdtemp(prefix="browser-check-"))
    p.add_argument("--skip-teach", action="store_true")
    args = p.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    report: dict = {"steps": {}}

    def step(name, ok, **detail):
        report["steps"][name] = {"ok": bool(ok), **detail}
        print(("PASS " if ok else "FAIL ") + name + (f"  {json.dumps(detail, default=str)[:300]}" if detail else ""), flush=True)

    os.environ["AGENT_BROWSER_FORCE"] = "1"  # the test Chrome need not be the frontmost app
    os.environ.setdefault("AGENT_DATA_DIR", tempfile.mkdtemp(prefix="browser-check-data-"))
    sys.path.insert(0, str(ROOT))
    from engine.browser.bridge import BrowserBridge, set_bridge, write_extension_config

    # 1. Separate extension copy, bridge, demo server, Chrome.
    bridge_port, token = free_port(), "check-" + base64.urlsafe_b64encode(os.urandom(12)).decode()
    ext = out / "extension"
    shutil.rmtree(ext, ignore_errors=True)
    shutil.copytree(ROOT / "extension", ext)
    write_extension_config(bridge_port, token, ext)
    bridge = BrowserBridge(bridge_port, token)
    assert bridge.start(), bridge.error
    set_bridge(bridge)

    from engine.tools.demo_server import Handler, SITE
    from functools import partial
    from http.server import ThreadingHTTPServer

    site_port = free_port()
    httpd = ThreadingHTTPServer(("127.0.0.1", site_port), partial(Handler, directory=str(SITE)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{site_port}/"

    cdp_port = free_port()
    profile = out / "profile"
    shutil.rmtree(profile, ignore_errors=True)  # a reused profile keeps the old worker (and old config.js) cached
    chrome = subprocess.Popen([
        args.chrome, f"--user-data-dir={profile}", f"--load-extension={ext}", f"--disable-extensions-except={ext}",
        f"--remote-debugging-port={cdp_port}", "--no-first-run", "--no-default-browser-check",
        "--window-size=1280,860", "--window-position=40,40", url,
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(180):  # first launch can sit behind macOS's Local Network prompt
            if bridge.connected:
                break
            time.sleep(0.5)
        step("extension connects", bridge.connected, info=bridge.info)
        if not bridge.connected:
            report["hint"] = ("Branded Google Chrome 137+ ignores --load-extension; pass --chrome pointing at Chrome for "
                              "Testing or Chromium.")
            return
        block_desktop_input()

        # 2. Overlays: the map must match the live DOM, and the labels must sit on their elements.
        bridge.call("navigate", url=url)
        time.sleep(0.8)
        shown = bridge.call("page", cmd="show", params={"layer": "interactive"})["elements"]
        dom = bridge.call("eval", code="return [...document.querySelectorAll('button, input, a[href], select, textarea')]"
                                        ".filter(e => e.offsetParent).map(e => { const r = e.getBoundingClientRect();"
                                        " return {id: e.id, x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height)} })")
        by_id = {d["id"]: d for d in dom if d["id"]}
        mism = [e["selector"] for e in shown if e.get("id") in by_id and (
            abs(e["rect"]["x"] - by_id[e["id"]]["x"]) > 1 or abs(e["rect"]["y"] - by_id[e["id"]]["y"]) > 1 or
            abs(e["rect"]["width"] - by_id[e["id"]]["w"]) > 1)]
        missing = [i for i in by_id if i not in {e.get("id") for e in shown}]
        step("getMap matches the page", not mism and not missing, elements=len(shown), dom=len(by_id), mismatched=mism, missing=missing)
        shot = bridge.call("screenshot")["data_url"]
        (out / "overlay_interactive.png").write_bytes(base64.b64decode(shot.split(",", 1)[1]))
        for layer, mode in (("interactive", "regions"), ("static", None), ("scrollable", None)):
            bridge.call("page", cmd="hide", params={"layer": "all"})
            els = bridge.call("page", cmd="show", params={"layer": layer, "mode": mode})["elements"]
            name = f"overlay_{mode or layer}.png"
            (out / name).write_bytes(base64.b64decode(bridge.call("screenshot")["data_url"].split(",", 1)[1]))
            step(f"{mode or layer} overlay", True, elements=len(els), screenshot=name)
        bridge.call("page", cmd="hide", params={"layer": "all"})
        el = bridge.call("page", cmd="find_element", params={"text": "Reset"})["element"]
        step("findElement(text)", el and el["selector"] == "#reset", element=el and el["selector"])

        # 3. SDK script through the DOM: click, type, read a value, capture a network response.
        from engine.agent import Agent
        from engine.sdk.context import NullHost

        host = NullHost()
        agent = Agent(host)
        script = (
            'click("New Invoice button", expect="an empty invoice form is open")\n'
            'type_into("Customer field", "Acme Corp")\n'
            'type_into("Amount field", "1200")\n'
            'typed = read_text("Customer field")\n'
            'click("Save button", expect="an invoice saved message is shown")\n'
            'inv = network_response("/api/invoices", method="POST")\n'
            'show(typed + " -> " + inv["number"] + " (id " + str(inv["id"]) + ")")\n'
        )
        r = agent.run_task("browser check", script)
        shown_results = [d for t, d in host.events if t == "run_finished"][-1]["results"]
        step("SDK script (click, type, read, network)", r["status"] == "succeeded", status=r["status"], error=r.get("error"),
             results=shown_results, metrics={k: r["metrics"].get(k) for k in ("model_calls", "calls_by_role", "cache_hits", "cost", "elapsed", "fixes")})
        r2 = agent.run_task("browser check again", script)
        step("replay uses the browser cache", r2["status"] == "succeeded" and r2["metrics"]["cache_hits"] >= 4,
             cache_hits=r2["metrics"]["cache_hits"], model_calls=r2["metrics"]["model_calls"],
             by_role=r2["metrics"].get("calls_by_role"), fixes=r2["metrics"].get("fixes"))

        # 4. Teach in Chrome with trusted input, generalize, replay.
        if not args.skip_teach:
            bridge.call("navigate", url=url)
            time.sleep(0.8)
            cdp = CDP(cdp_port)
            m = {e["selector"]: e["rect"] for e in bridge.call("page", cmd="get_map", params={"offscreen": True})["elements"]}
            bridge.call("teach_start")
            cdp.click(m["#new-invoice"]["centerX"], m["#new-invoice"]["centerY"])
            m = {e["selector"]: e["rect"] for e in bridge.call("page", cmd="get_map", params={})["elements"]}
            cdp.click(m["#customer"]["centerX"], m["#customer"]["centerY"])
            cdp.type("Globex")
            cdp.click(m["#amount"]["centerX"], m["#amount"]["centerY"])
            cdp.type("860.50")
            cdp.click(m["#save"]["centerX"], m["#save"]["centerY"])
            time.sleep(1.2)
            rec = bridge.call("teach_stop", timeout=20)
            kinds = [e["kind"] for e in rec["events"]]
            step("teach records DOM actions and network", "click" in kinds and "input" in kinds and rec["network"],
                 events=kinds, network=[(n["method"], n["url"][-30:]) for n in rec["network"]])
            from engine.teach.compiler import compile_recording

            compiled = compile_recording({"events": [], "frames": []}, "Create invoice", "Create an invoice in the demo app",
                                         agent.models, lambda *a, **k: None, browser=rec)
            (out / "taught_script.py").write_text(compiled["script"])
            step("teach compiles to a script", not compiled["problems"], problems=compiled["problems"],
                 script=compiled["script"][:600])
            if not compiled["problems"]:
                host.answers[:] = ["Initech", "455.25"]  # for any ask_user() the planner put in for inputs
                rr = agent.run_task("taught replay", compiled["script"])
                step("taught script replays", rr["status"] == "succeeded", status=rr["status"], error=rr.get("error"),
                     cache_hits=rr["metrics"]["cache_hits"])
    finally:
        (out / "report.json").write_text(json.dumps(report, indent=1, default=str))
        print(f"\nreport: {out / 'report.json'}")
        chrome.terminate()
        httpd.shutdown()


if __name__ == "__main__":
    main()
