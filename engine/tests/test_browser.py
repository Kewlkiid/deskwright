"""Chrome backend: target matching, DOM-first actions with screen fallback, browser cache, read_table, network
responses, Chrome teach compile, and the bridge's origin/token checks. A FakeBridge stands in for the extension."""
import json
import socket

import pytest

from engine.browser import match
from engine.browser.backend import page_key
from engine.browser.bridge import BrowserBridge, set_bridge, write_extension_config
from engine.config import config

URL = "http://localhost:5050/invoices"


def entry(index, tag, category, name=None, label=None, text="", selector=None, **attrs):
    return {
        "index": index, "tag": tag, "category": category, "accessible_name": name, "label": label, "text": text,
        "selector": selector or f"#el{index}", "description": f'{category} "{label or name or text}"',
        "rect": {"x": 100 + index * 10, "y": 200, "width": 80, "height": 30, "centerX": 140 + index * 10, "centerY": 215},
        "attributes": attrs, "offscreen": False,
    }


PAGE = [
    entry(0, "button", "button", "New Invoice", text="New Invoice", selector="#new-invoice"),
    entry(1, "button", "button", "Rename Save button", text="Rename Save button", selector="#rename"),
    entry(2, "button", "button", "Reset", text="Reset", selector="#reset"),
    entry(3, "input", "input", None, label="Customer", selector="#customer"),
    entry(4, "input", "input", None, label="Amount", selector="#amount"),
    entry(5, "button", "button", "Save", text="Save", selector="#save"),
]


class FakeBridge:
    """Answers the extension's commands from an in-memory page."""

    def __init__(self, screen, page=None):
        self.screen = screen
        self.page = [dict(e) for e in (page or PAGE)]
        self.values = {}
        self.calls = []
        self.net = []
        self.seq = 0
        self.teach = {"events": [], "network": []}
        self.connected = True
        self.info = {}
        self.port = 0
        self.active_tab = 1
        self.navigations = []  # (url, new_tab)

    def by_ref(self, p):
        if p.get("index") is not None:
            return next(e for e in self.page if e["index"] == p["index"])
        return next(e for e in self.page if e["selector"] == p["selector"])

    def call(self, type, timeout=15.0, **d):
        self.calls.append((type, d.get("cmd"), d.get("params")))
        if type == "status":
            return {"connected": True, "focused": True, "tab": {"id": self.active_tab, "url": URL, "title": "Invoices"}}
        if type == "navigate":
            self.navigations.append((d["url"], d["new_tab"]))
            if d["new_tab"]:
                self.active_tab += 1
            return {"id": self.active_tab, "url": d["url"], "status": "complete"}
        if type == "page":
            return self.page_cmd(d["cmd"], d.get("params") or {})
        if type in ("net_start", "net_mark"):
            return {"seq": self.seq}
        if type == "net_query":
            hits = [e for e in self.net if e["seq"] > d.get("since", 0) and d.get("url_contains", "") in e["url"]
                    and (not d.get("method") or e["method"] == d["method"])]
            return {"entries": list(reversed(hits)), "seq": self.seq}
        if type == "net_stop":
            return {"attached": False}
        if type == "eval":
            return {"title": "Invoices"}
        if type == "teach_start":
            return {"teaching": True}
        if type == "teach_stop":
            return self.teach
        raise AssertionError(f"unexpected command {type}")

    def page_cmd(self, cmd, p):
        if cmd == "get_map":
            return {"elements": [] if p.get("layer") == "static" else self.page}
        if cmd == "probe":
            e = next((e for e in self.page if e["selector"] == p["selector"]), None)
            ok = e is not None and p.get("name", "") in ((e.get("label") or ""), (e.get("accessible_name") or ""), "")
            return {"found": ok, "rect": e["rect"] if e else None}
        if cmd in ("reveal", "click"):
            e = self.by_ref(p)
            if cmd == "click":
                self.screen.bump("dom_click", e["selector"])  # the page reacts, like a real one
                if e["selector"] == "#save":
                    self.seq += 1
                    self.net.append({"seq": self.seq, "method": "POST", "url": "http://localhost:5050/api/invoices",
                                     "status": 201, "body": {"id": 812, "number": "INV-0042"}})
            return {"tag": e["tag"], "selector": e["selector"], "rect": e["rect"]}
        if cmd == "type":
            e = self.by_ref(p)
            v = ("" if p.get("clear") else self.values.get(e["selector"], "")) + p["text"]
            self.values[e["selector"]] = v
            return {"tag": e["tag"], "selector": e["selector"], "value": v, "rect": e["rect"]}
        if cmd == "read":
            e = self.by_ref(p)
            return {"value": self.values.get(e["selector"], e.get("text", ""))}
        if cmd == "tables":
            return {"tables": [{"index": 0, "selector": "#orders", "caption": "", "heading": "Orders",
                                "headers": ["Customer", "Amount", "Status"], "total_rows": 2,
                                "rows": [["Acme Corp", "1,200.00", "Open"], ["Globex", "860.50", "Open"]]}]}
        if cmd == "page_text":
            return {"url": URL, "text": "Invoices created\nInvoice saved"}
        if cmd == "signature":
            return {"version": self.screen.version, "values": dict(self.values)}
        if cmd == "viewport":
            return {"screenX": 0, "screenY": 0, "outerWidth": 1440, "innerWidth": 1440, "outerHeight": 900, "innerHeight": 800}
        raise AssertionError(f"unexpected page command {cmd}")

    def page_calls(self, cmd):
        return [c for c in self.calls if c[0] == "page" and c[1] == cmd]


@pytest.fixture
def chrome(screen, monkeypatch):
    monkeypatch.setattr(config, "browser_force", True)
    bridge = FakeBridge(screen)
    set_bridge(bridge)
    yield bridge
    set_bridge(None)


def events(host, kind):
    return [d for t, d in host.events if t == kind]


# ---------------------------------------------------------------- matching
def test_match_prefers_exact_names_and_fields_for_typing():
    assert match.best(PAGE, "Save button")["selector"] == "#save"
    assert match.best(PAGE, "blue 'New Invoice' button in the top right")["selector"] == "#new-invoice"
    assert match.best(PAGE, "New Invoice button at the top of the page")["selector"] == "#new-invoice"
    assert match.best(PAGE, "Customer field", "type into")["selector"] == "#customer"
    assert match.best(PAGE, "Amount", "type into")["selector"] == "#amount"
    assert match.best(PAGE, "second button in the toolbar") is None  # ordinal: leave it to the model
    assert match.best(PAGE, "Delete account") is None


def test_page_key_generalizes_ids():
    assert page_key("https://app.example.com/invoices/812?tab=1#x") == "https://app.example.com/invoices/#"
    assert page_key("https://x.io/u/3f2a9c1e7b6d/edit") == "https://x.io/u/#/edit"


# ---------------------------------------------------------------- actions
def test_click_and_type_go_through_the_dom_and_hit_the_cache_next_run(screen, chrome, agent_factory):
    agent, host = agent_factory()
    script = 'click("New Invoice button", expect="empty invoice form")\ntype_into("Customer field", "Acme Corp")'
    out = agent.run_task("dom", script)
    assert out["status"] == "succeeded", out
    assert [c[2]["selector"] for c in chrome.page_calls("click")] == ["#new-invoice"]
    assert chrome.values["#customer"] == "Acme Corp"
    assert not [i for i in screen.inputs if i[0] in ("click", "type_text", "move")]  # no real mouse or keyboard
    assert events(host, "element_found")[0]["source"] == "dom"

    maps_before = len(chrome.page_calls("get_map"))
    out = agent.run_task("dom again", script)
    assert out["status"] == "succeeded"
    assert len(chrome.page_calls("get_map")) == maps_before  # both targets came from the browser cache
    assert out["metrics"]["cache_hits"] == 2


def test_cache_entry_is_dropped_when_the_element_changed(screen, chrome, agent_factory):
    agent, _ = agent_factory()
    agent.run_task("one", 'click("Reset button")')
    assert agent.cache.browser_lookup(page_key(URL), "Reset button")["selector"] == "#reset"
    reset = next(e for e in chrome.page if e["selector"] == "#reset")
    reset["accessible_name"] = reset["text"] = "Start over"  # same selector, different element now
    reset["description"] = 'button "Start over"'
    out = agent.run_task("two", 'click("Reset button")')
    assert out["status"] == "succeeded"
    assert out["metrics"]["cache_hits"] == 0  # the re-check in the live DOM rejected the stale entry
    assert agent.cache.browser_lookup(page_key(URL), "Reset button") is None
    assert [i for i in screen.inputs if i[0] in ("click", "move")]  # nothing named "Reset" any more: screen fallback


def test_unknown_target_falls_back_to_the_screen(screen, chrome, agent_factory):
    agent, _ = agent_factory()
    out = agent.run_task("fallback", 'click("Export to PDF icon")')
    assert out["status"] == "succeeded"
    assert not chrome.page_calls("click")
    assert [i for i in screen.inputs if i[0] in ("click", "move")]  # the desktop path acted (dry run: moves only)


def test_typing_mismatch_raises_field_changed(screen, chrome, agent_factory, monkeypatch):
    agent, host = agent_factory(answers=["stop"])
    orig = chrome.page_cmd

    def lossy(cmd, p):
        r = orig(cmd, p)
        if cmd == "type":
            r["value"] = "Acm"  # the page's own handler mangled the value
        return r

    monkeypatch.setattr(chrome, "page_cmd", lossy)
    agent.run_task("mismatch", 'type_into("Customer field", "Acme Corp")')
    # The line fails instead of carrying on with a wrong value; self-healing then takes over.
    assert events(host, "line_failed")[0]["error"]["type"] == "FieldChangedError"


def test_read_table_and_expect_use_the_page(screen, chrome, agent_factory, monkeypatch):
    from engine.models.fake import FakeVision

    def screen_path(*a, **k):
        raise AssertionError("the screenshot path was used")

    agent, host = agent_factory()
    monkeypatch.setattr(FakeVision, "read_table", screen_path)
    monkeypatch.setattr(FakeVision, "check", screen_path)
    script = (
        'rows = read_table("orders table")\n'
        'expect("invoice saved message is shown")\n'
        'show(make_table(rows))'
    )
    out = agent.run_task("table", script)
    assert out["status"] == "succeeded", out
    table = events(host, "run_finished")[0]["results"][0]
    assert "Acme Corp" in json.dumps(table) and "860.50" in json.dumps(table)
    assert chrome.page_calls("tables") and chrome.page_calls("page_text")


def test_read_table_maps_requested_columns(screen, chrome, agent_factory):
    from engine.sdk.context import set_current

    agent, _ = agent_factory()
    ctx = agent._new_context("t")
    set_current(ctx)
    try:
        from engine.sdk.questions import read_table

        rows = read_table("orders table", columns=["customer", "amount"])
    finally:
        set_current(None)
    assert rows == [{"customer": "Acme Corp", "amount": "1,200.00"}, {"customer": "Globex", "amount": "860.50"}]
    assert rows[0]["Customer"] == "Acme Corp"


def test_a_click_that_changes_nothing_in_the_page_fails(screen, chrome, agent_factory, monkeypatch):
    agent, host = agent_factory(answers=["stop"])
    orig = chrome.page_cmd

    def inert(cmd, p):
        if cmd == "click":
            return {"tag": "button", "selector": p.get("selector")}  # no DOM change, no request
        return orig(cmd, p)

    monkeypatch.setattr(chrome, "page_cmd", inert)
    agent.run_task("inert", 'click("Reset button")')
    assert events(host, "line_failed")[0]["error"]["type"] == "NoChangeError"


def test_network_response_returns_the_created_id(screen, chrome, agent_factory):
    agent, host = agent_factory()
    script = (
        'click("Save button", expect="invoice saved message")\n'
        'inv = network_response("/api/invoices", method="POST")\n'
        'show("Created " + str(inv["id"]))'
    )
    out = agent.run_task("net", script)
    assert out["status"] == "succeeded", out
    assert ("net_start", None, None) in chrome.calls  # capture started before the first line
    assert ("net_stop", None, None) in chrome.calls  # and released at the end
    assert any("Created 812" in json.dumps(d, default=str) for t, d in host.events if t == "run_finished")


def test_network_response_without_a_match_fails_the_line(screen, chrome, agent_factory):
    agent, host = agent_factory(answers=["stop"])
    out = agent.run_task("net", 'click("Reset button")\nnetwork_response("/api/nothing", timeout=0.1)')
    assert out["status"] == "stopped"
    assert "No network response" in events(host, "line_failed")[0]["error"]["message"]


# ---------------------------------------------------------------- teach
def test_chrome_teach_steps_replace_desktop_clicks(tmp_path):
    from engine.models.fake import FakeGrounder, FakePlanner, FakeVision, FakeVoice
    from engine.models import Models
    from engine.teach.compiler import browser_steps, compile_recording

    t0 = 1_800_000_000_000
    rec = {
        "events": [
            {"kind": "navigate", "t": t0, "url": URL, "initial": True},
            {"kind": "click", "t": t0 + 1000, "url": URL, "selector": "#new-invoice", "description": 'button "New Invoice"', "name": "New Invoice"},
            {"kind": "click", "t": t0 + 2000, "url": URL, "selector": "#customer", "description": 'input field "Customer"', "name": "Customer"},
            {"kind": "input", "t": t0 + 3000, "url": URL, "selector": "#customer", "description": 'input field "Customer"', "name": "Customer", "value": "Acme Corp"},
            {"kind": "input", "t": t0 + 3500, "url": URL, "selector": "#pw", "description": 'password input field "Password"', "name": "Password", "value": "", "secret": True},
            {"kind": "click", "t": t0 + 4000, "url": URL, "selector": "#save", "description": 'button "Save"', "name": "Save"},
            {"kind": "navigate", "t": t0 + 4500, "url": URL + "/812"},
        ],
        "network": [
            {"t": t0 + 4200, "method": "POST", "url": "http://localhost:5050/api/invoices", "status": 201,
             "body": {"id": 812, "invoice": {"number": "INV-0042"}, "total": 1200}},
            {"t": t0 + 4300, "method": "GET", "url": "http://localhost:5050/api/stats", "status": 200, "body": {"count": 3}},
        ],
    }
    steps = browser_steps(rec)
    kinds = [s["kind"] for s in steps]
    assert kinds == ["start_page", "click", "type", "type", "click", "network"]  # field click folded into type_into
    assert steps[2]["text"] == "Acme Corp" and steps[3]["text"] == "" and steps[3]["secret"]
    assert steps[-1]["ids"] == {"id": 812, "invoice.number": "INV-0042"}

    meta = {"events": [{"type": "click", "t": (t0 + 1000) / 1000, "x": 10, "y": 10, "window": "Google Chrome|Invoices"},
                       {"type": "hotkey", "t": (t0 + 500) / 1000, "keys": ["cmd", "l"], "window": "Google Chrome|Invoices"}],
            "frames": []}
    models = Models(FakePlanner(), FakeVision(), FakeGrounder(), FakeVoice())
    out = compile_recording(meta, "Make invoice", "", models, lambda *a, **k: None, browser=rec)
    got = [s["kind"] for s in out["steps"]]
    assert got.count("click") == 2 and "hotkey" in got  # desktop click inside Chrome dropped, hotkey kept


# ---------------------------------------------------------------- bridge
def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_bridge_accepts_only_the_extension_with_the_token():
    from websockets.sync.client import connect
    import threading

    bridge = BrowserBridge(_free_port(), "secret-token")
    assert bridge.start()
    url = f"ws://127.0.0.1:{bridge.port}"

    from websockets.exceptions import ConnectionClosed

    for origin, token, reason in (("http://evil.example", "secret-token", "extensions only"),  # a web page
                                  ("chrome-extension://abc", "nope", "bad token")):
        with pytest.raises(ConnectionClosed) as e:
            with connect(url, origin=origin) as ws:
                ws.send(json.dumps({"type": "hello", "token": token}))
                ws.recv(timeout=2)
        assert e.value.rcvd.code == 4003 and e.value.rcvd.reason == reason
    assert not bridge.connected

    with connect(url, origin="chrome-extension://abc") as ws:
        ws.send(json.dumps({"type": "hello", "token": "secret-token", "version": "0.1.0"}))
        assert json.loads(ws.recv(timeout=2))["type"] == "welcome"

        def extension():
            msg = json.loads(ws.recv(timeout=5))
            ws.send(json.dumps({"id": msg["id"], "ok": True, "result": {"echo": msg["data"]}}))
            msg = json.loads(ws.recv(timeout=5))
            ws.send(json.dumps({"id": msg["id"], "ok": False, "error": "element not found"}))

        t = threading.Thread(target=extension)
        t.start()
        assert bridge.call("page", cmd="ping") == {"echo": {"cmd": "ping"}}
        with pytest.raises(Exception, match="element not found"):
            bridge.call("page", cmd="click")
        t.join()
        assert bridge.connected and bridge.info["version"] == "0.1.0"


def test_extension_config_is_written_only_when_it_changes(tmp_path):
    assert write_extension_config(8777, "tok", tmp_path)
    assert "ws://127.0.0.1:8777" in (tmp_path / "config.js").read_text()
    assert "'tok'" in (tmp_path / "config.js").read_text()
    assert not write_extension_config(8777, "tok", tmp_path)


def test_open_url_never_replaces_the_users_tab(screen, chrome, agent_factory):
    agent, _ = agent_factory()
    out = agent.run_task("open", 'open_url("http://a.test")\nopen_url("http://b.test")\nopen_url("http://c.test", new_tab=True)')
    assert out["status"] == "succeeded", out
    # The user's tab (1) is left alone; the second URL reuses the tab the run opened; new_tab=True opens another.
    assert chrome.navigations == [("http://a.test", True), ("http://b.test", False), ("http://c.test", True)]
