"""Localhost WebSocket link to the Electron window. Bound to 127.0.0.1, guarded by a random session token."""
from __future__ import annotations

import asyncio
import base64
import concurrent.futures
import itertools
import json
import secrets
import sys
import threading
from typing import Any

import websockets

from .agent import Agent
from .sdk.errors import StoppedError
from .sdk.results import export_data

IS_LINUX = sys.platform.startswith("linux")


class ServerHost:
    """Host implementation that forwards events to the UI and blocks the run thread for answers."""

    def __init__(self):
        self.loop: asyncio.AbstractEventLoop | None = None
        self.queue: asyncio.Queue | None = None
        self.connected = threading.Event()
        self._ids = itertools.count(1)
        self._waiting: dict[str, concurrent.futures.Future] = {}
        self._hidden = threading.Event()
        self.approve_all = False  # "Approve all this run": reset when the next run starts
        self.bypass = False  # bypass mode: sensitive actions run without asking (set from the UI)

    def emit(self, type: str, **data: Any):
        if type == "run_started":
            self.approve_all = False
        if self.loop is None or self.queue is None:
            return
        msg = json.dumps({"type": type, **data}, default=str)
        self.loop.call_soon_threadsafe(self.queue.put_nowait, msg)

    def _wait_for_reply(self, kind: str, payload: dict, stop: threading.Event):
        rid = f"q{next(self._ids)}"
        fut: concurrent.futures.Future = concurrent.futures.Future()
        self._waiting[rid] = fut
        self.emit(kind, id=rid, **payload)
        try:
            while True:
                if stop.is_set():
                    raise StoppedError("Stopped while waiting for the user")
                try:
                    return fut.result(timeout=0.2)
                except concurrent.futures.TimeoutError:
                    continue
        finally:
            self._waiting.pop(rid, None)
            self.emit("question_closed", id=rid)

    def resolve(self, rid: str, value):
        fut = self._waiting.get(rid)
        if fut and not fut.done():
            fut.set_result(value)

    def ask_user(self, question: str, stop: threading.Event) -> str:
        return str(self._wait_for_reply("ask_user", {"question": question}, stop) or "")

    def confirm(self, summary: str, stop: threading.Event) -> bool:
        if self.bypass:
            self.emit("status", text=f"Approvals off: {summary.splitlines()[0]}")
            return True
        if self.approve_all:
            self.emit("status", text=f"Approved (all this run): {summary.splitlines()[0]}")
            return True
        value = self._wait_for_reply("confirm_request", {"summary": summary}, stop)
        if value == "all":
            self.approve_all = True
            return True
        return bool(value)

    # On macOS/Windows the window uses setContentProtection and never appears in captures.
    # On Linux, ask the UI to hide and wait briefly for the acknowledgement.
    def before_capture(self):
        if IS_LINUX and self.connected.is_set():
            self._hidden.clear()
            self.emit("request_hide")
            self._hidden.wait(0.3)

    def after_capture(self):
        if IS_LINUX and self.connected.is_set():
            self.emit("request_show")

    def hidden_ack(self):
        self._hidden.set()


class Server:
    def __init__(self, token: str | None = None):
        self.token = token or secrets.token_urlsafe(24)
        self.host = ServerHost()
        self.agent = Agent(self.host)
        self.client = None
        self.settings = {"auto_run": True, "bypass_approvals": False}
        from .browser.bridge import start_bridge

        self.bridge = start_bridge()  # the Chrome extension connects here (extension/config.js)
        threading.Thread(target=self._watch_teach_requests, name="teach-requests", daemon=True).start()

    def _watch_teach_requests(self):
        """Another program asked for a task to be shown once (`engine.cli teach --describe`): it leaves a
        request file; once the window is connected, show the request there and remember it for teach_stop."""
        import time as _time

        from .teach.requests import take_request

        while True:
            _time.sleep(1)
            if not self.host.connected.is_set():
                continue
            req = take_request()
            if req:
                self.agent.teach_request = req
                self.host.emit("teach_request", **req)

    def _bg(self, fn, *args, **kwargs):
        threading.Thread(target=self._safe, args=(fn, *args), kwargs=kwargs, daemon=True).start()

    def _safe(self, fn, *args, **kwargs):
        try:
            fn(*args, **kwargs)
        except Exception as e:  # noqa: BLE001
            self.host.emit("error", message=f"{type(e).__name__}: {e}")

    async def _pump(self, ws):
        while True:
            msg = await self.host.queue.get()
            try:
                await ws.send(msg)
            except websockets.ConnectionClosed:
                return

    async def handler(self, ws):
        try:
            first = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
        except Exception:
            await ws.close(code=4001, reason="auth required")
            return
        if first.get("type") != "auth" or not secrets.compare_digest(str(first.get("token", "")), self.token):
            await ws.close(code=4003, reason="bad token")
            return
        if self.client is not None:
            await self.client.close(code=4000, reason="replaced")
        self.client = ws
        self.host.connected.set()
        pump = asyncio.create_task(self._pump(ws))
        await ws.send(json.dumps({"type": "hello", "tasks": self.agent.db.list_tasks(),
                                  "totals": self.agent.db.all_runs_summary(),
                                  "cache": self.agent.cache.stats(), "settings": self.settings,
                                  "browser": self.agent.browser_status()}, default=str))
        try:
            async for raw in ws:
                try:
                    self.dispatch(json.loads(raw))
                except Exception as e:  # noqa: BLE001
                    self.host.emit("error", message=f"Bad message: {e}")
        except websockets.ConnectionClosed:
            pass
        finally:
            pump.cancel()
            if self.client is ws:
                self.client = None
                self.host.connected.clear()

    def dispatch(self, m: dict):
        a = self.agent
        t = m.get("type")
        if t == "command":
            self._bg(a.handle_command, m.get("text", ""), self.settings.get("auto_run", True))
        elif t == "run_task":
            self._bg(a.run_task, m["task"])
        elif t == "run_script":
            self._bg(a.run_draft, m.get("script"))
        elif t == "stop":
            a.stop()
        elif t in ("answer_user", "confirm_reply"):
            self.host.resolve(m["id"], m.get("value"))
        elif t == "audio":
            def go():
                text = a.transcribe(base64.b64decode(m["data"]), m.get("mime", "audio/webm"))
                if m.get("auto_send", True) and text:
                    a.handle_command(text, self.settings.get("auto_run", True))
            self._bg(go)
        elif t == "wake_audio":
            self._bg(a.hear, base64.b64decode(m["data"]), m.get("mime", "audio/wav"), bool(m.get("command")),
                     self.settings.get("auto_run", True))
        elif t == "teach_start":
            self._bg(a.teach_start)
        elif t == "teach_cancel":
            self._bg(a.teach_cancel)
        elif t == "teach_stop":
            self._bg(a.teach_stop, m.get("name", ""), m.get("description", ""))
        elif t == "save_task":
            self._bg(a.save_task, m["name"], m["script"], m.get("description", ""), m.get("source", "chat"))
        elif t == "delete_task":
            a.db.delete_task(int(m["task_id"]))
            self.host.emit("tasks", tasks=a.db.list_tasks())
        elif t == "list_tasks":
            self.host.emit("tasks", tasks=a.db.list_tasks())
        elif t == "run_saved":
            self._bg(a.run_saved, m.get("task_id"), m.get("name"))
        elif t == "export":
            def go():
                where = export_data(m["data"], m.get("fmt", "csv"), m.get("name"))
                self.host.emit("exported", path=where, fmt=m.get("fmt", "csv"))
            self._bg(go)
        elif t == "settings":
            self.settings.update({k: v for k, v in m.items() if k != "type"})
            self.host.bypass = bool(self.settings.get("bypass_approvals"))
        elif t == "ui_bounds":
            a.ui_bounds = m.get("bounds")
        elif t == "hidden_ack":
            self.host.hidden_ack()
        elif t == "clear_cache":
            a.cache.clear()
            self.host.emit("cache", cache=a.cache.stats())
        elif t == "ping":
            self.host.emit("pong")
        elif t == "browser_status":
            self.host.emit("browser", **a.browser_status())

    async def serve(self, port: int = 0, on_ready=None):
        self.host.loop = asyncio.get_running_loop()
        self.host.queue = asyncio.Queue()
        async with websockets.serve(self.handler, "127.0.0.1", port, max_size=32 * 1024 * 1024) as server:
            actual = server.sockets[0].getsockname()[1]
            if on_ready:
                on_ready(actual, self.token)
            await asyncio.Future()
