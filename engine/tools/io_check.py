"""End-to-end check of task inputs/outputs in a throwaway Chrome: teach a search on the demo docs site, check the
generated INPUTS/OUTPUTS header, save it, then run it through the public CLI with --input and --json.

    python -m engine.tools.io_check --chrome "/path/to/Google Chrome for Testing" --out /tmp/io-check

Real models (whatever .env configures). The CLI run uses dry-run mode, so a fallback to the desktop could only move
the pointer, never click or type on the real screen; page actions go through the extension.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--chrome", required=True)
    p.add_argument("--out", default=tempfile.mkdtemp(prefix="io-check-"))
    p.add_argument("--term", default="solar", help="what to search while teaching")
    p.add_argument("--run-term", default="wind", help="the input passed to the CLI run")
    args = p.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    data_dir = out / "data"
    data_dir.mkdir(exist_ok=True)
    os.environ["AGENT_DATA_DIR"] = str(data_dir)
    os.environ["AGENT_BROWSER_FORCE"] = "1"
    sys.path.insert(0, str(ROOT))

    from engine.browser.bridge import BrowserBridge, set_bridge, write_extension_config
    from engine.tools.browser_check import CDP, free_port
    from engine.tools.demo_server import SITE, Handler

    report: dict = {}

    def step(name, ok, **detail):
        report[name] = {"ok": bool(ok), **detail}
        print(("PASS " if ok else "FAIL ") + name + "  " + json.dumps(detail, default=str)[:600], flush=True)

    port, token = free_port(), "io-" + base64.urlsafe_b64encode(os.urandom(12)).decode()
    ext = out / "extension"
    shutil.rmtree(ext, ignore_errors=True)
    shutil.copytree(ROOT / "extension", ext)
    write_extension_config(port, token, ext)
    bridge = BrowserBridge(port, token)
    assert bridge.start(), bridge.error
    set_bridge(bridge)

    site_port = free_port()
    httpd = ThreadingHTTPServer(("127.0.0.1", site_port), partial(Handler, directory=str(SITE)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{site_port}/search.html"

    cdp_port = free_port()
    profile = out / "profile"
    shutil.rmtree(profile, ignore_errors=True)
    chrome = subprocess.Popen([args.chrome, f"--user-data-dir={profile}", f"--load-extension={ext}",
                               f"--disable-extensions-except={ext}", f"--remote-debugging-port={cdp_port}",
                               "--no-first-run", "--no-default-browser-check", "--window-size=1200,820", url],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(180):
            if bridge.connected:
                break
            time.sleep(0.5)
        step("extension connects", bridge.connected)
        if not bridge.connected:
            return
        time.sleep(1)

        # 1. Teach: search the docs with trusted input (what a person would do), then stop.
        cdp = CDP(cdp_port)
        m = {e["selector"]: e["rect"] for e in bridge.call("page", cmd="get_map", params={})["elements"]}
        bridge.call("teach_start")
        cdp.click(m["#q"]["centerX"], m["#q"]["centerY"])
        cdp.type(args.term)
        for kind in ("keyDown", "keyUp"):
            cdp.call("Input.dispatchKeyEvent", type=kind, key="Enter", code="Enter", windowsVirtualKeyCode=13,
                     text="\r" if kind == "keyDown" else None)
        time.sleep(1.5)
        rec = bridge.call("teach_stop", timeout=20)
        step("teach recorded", rec["events"] and rec["network"], events=[e["kind"] for e in rec["events"]],
             network=[(n["method"], n["url"].split("?")[0][-20:]) for n in rec["network"]])

        # 2. Generalize with the planner and check the header.
        from engine.agent import Agent
        from engine.runner.schema import parse_header
        from engine.sdk.context import NullHost
        from engine.teach.compiler import compile_recording

        agent = Agent(NullHost())
        description = "Search the docs site for a term and output the first result's title and URL"
        compiled = compile_recording({"events": [], "frames": []}, "search docs", description, agent.models,
                                     lambda *a, **k: None, browser=rec)
        script = compiled["script"]
        (out / "taught_script.py").write_text(script)
        h = parse_header(script)
        sensible = (not h["problems"] and len(h["inputs"]) == 1 and len(h["outputs"]) >= 2
                    and any("title" in k for k in h["outputs"]) and any("url" in k for k in h["outputs"]))
        step("generated header", sensible, inputs=h["inputs"], outputs=h["outputs"], problems=h["problems"] + compiled["problems"])
        print("\n--- taught script ---\n" + script + "\n---------------------\n", flush=True)
        agent.db.save_task("search docs", script, description, "teach")

        # 3. Run it through the public CLI, the way another program would.
        bridge.stop()  # the CLI's engine takes over the port; the extension reconnects to it
        time.sleep(1)
        input_name = next(iter(h["inputs"]), "term")
        env = {**os.environ, "AGENT_BROWSER_PORT": str(port), "AGENT_BROWSER_TOKEN": token, "AGENT_BROWSER_WAIT": "30",
               "AGENT_DRY_RUN": "1"}
        cmd = [sys.executable, "-m", "engine.cli", "run", "--saved", "search docs", "--input",
               f"{input_name}={args.run_term}", "--json", "--yes", "--no-ask"]
        r = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)
        (out / "cli_stderr.txt").write_text(r.stderr)
        lines = [l for l in r.stdout.splitlines() if l.strip()]
        try:
            result = json.loads(lines[-1]) if len(lines) == 1 else None
        except ValueError:
            result = None
        outputs = (result or {}).get("outputs") or {}
        text = json.dumps(outputs).lower()
        good = (r.returncode == 0 and result and result["status"] == "ok"
                and "wind turbine maintenance" in text and "/docs/wind-maintenance" in text)
        step("CLI run --json", good, exit_code=r.returncode, stdout_lines=len(lines), result=result)
    finally:
        (out / "report.json").write_text(json.dumps(report, indent=1, default=str))
        print(f"report: {out / 'report.json'}")
        chrome.terminate()
        httpd.shutdown()


if __name__ == "__main__":
    main()
