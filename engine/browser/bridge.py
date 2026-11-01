"""WebSocket server the Chrome extension connects to (extension/background.js).

Runs on its own thread and event loop so run threads can make blocking calls: `bridge.call("page", cmd="click",
params={...})`. Bound to 127.0.0.1 on a fixed port (the extension can't discover a random one) and guarded twice:
only chrome-extension:// origins are accepted, and the first message must carry the pairing token that the engine
writes into extension/config.js.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import itertools
import json
import secrets
import threading
from pathlib import Path
from typing import Any

import websockets

from ..config import ROOT, config
from ..sdk.errors import AgentError

EXTENSION_DIR = ROOT / "extension"


class BrowserError(AgentError):
    code = "browser_error"
    default_fix = "The Chrome page did not accept the action. Look at the screenshot; try another target or a click."


class BrowserUnavailableError(AgentError):
    code = "browser_unavailable"
    default_fix = "Chrome with the agent extension is not connected or not in front. Use screen-based actions instead."
    default_retryable = False


def pairing_token() -> str:
    path = config.browser_token_path
    if path.exists():
        token = path.read_text().strip()
        if token:
            return token
    token = secrets.token_urlsafe(24)
    path.write_text(token)
    return token


def write_extension_config(port: int, token: str, directory: Path = EXTENSION_DIR) -> bool:
    """Point the extension at this engine. Returns True when the file changed (the extension must be reloaded)."""
    text = (
        "// Written by the engine (engine/browser/bridge.py) on start: where the local agent engine listens, and the\n"
        "// pairing token it expects. Reload the extension after this file changes.\n"
        f"const ENGINE_WS_URL = 'ws://127.0.0.1:{port}';\n"
        f"const ENGINE_TOKEN = '{token}';\n"
    )
    path = directory / "config.js"
    if not directory.exists() or (path.exists() and path.read_text() == text):
        return False
    path.write_text(text)
    return True


class BrowserBridge:
    def __init__(self, port: int, token: str):
        self.port = port
        self.token = token
        self.loop: asyncio.AbstractEventLoop | None = None
        self.ws = None
        self.info: dict = {}
        self._ids = itertools.count(1)
        self._waiting: dict[int, concurrent.futures.Future] = {}
        self._started = threading.Event()
        self.error: str | None = None

    @property
    def connected(self) -> bool:
        return self.ws is not None

    def start(self, timeout: float = 3.0) -> bool:
        threading.Thread(target=self._run, daemon=True, name="browser-bridge").start()
        self._started.wait(timeout)
        return self.error is None

    def _run(self):
        try:
            asyncio.run(self._serve())
        except Exception as e:  # noqa: BLE001 - e.g. the port is taken by another engine
            self.error = f"{type(e).__name__}: {e}"
            self._started.set()

    async def _serve(self):
        self.loop = asyncio.get_running_loop()
        async with websockets.serve(self._handler, "127.0.0.1", self.port, max_size=32 * 1024 * 1024):
            self._started.set()
            await asyncio.Future()

    async def _handler(self, ws):
        origin = ws.request.headers.get("Origin", "") if ws.request else ""
        if not origin.startswith("chrome-extension://"):
            await ws.close(code=4003, reason="extensions only")
            return
        try:
            hello = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
        except Exception:
            await ws.close(code=4001, reason="hello required")
            return
        if hello.get("type") != "hello" or not secrets.compare_digest(str(hello.get("token", "")), self.token):
            await ws.close(code=4003, reason="bad token")
            return
        if self.ws is not None:
            await self.ws.close(code=4000, reason="replaced")
        self.ws = ws
        self.info = {"version": hello.get("version"), "origin": origin, "ua": hello.get("ua")}
        await ws.send(json.dumps({"type": "welcome"}))
        try:
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except ValueError:
                    continue
                fut = self._waiting.pop(msg.get("id"), None) if "id" in msg else None
                if fut and not fut.done():
                    if msg.get("ok"):
                        fut.set_result(msg.get("result"))
                    else:
                        fut.set_exception(BrowserError(str(msg.get("error") or "browser command failed")))
        except websockets.ConnectionClosed:
            pass
        finally:
            if self.ws is ws:
                self.ws = None
                for fut in list(self._waiting.values()):
                    if not fut.done():
                        fut.set_exception(BrowserUnavailableError("The Chrome extension disconnected"))
                self._waiting.clear()

    def call(self, type: str, timeout: float = 15.0, **data) -> Any:
        """Send one command to the extension and wait for its answer (from any thread but the bridge's own)."""
        ws, loop = self.ws, self.loop
        if ws is None or loop is None:
            raise BrowserUnavailableError("The Chrome extension is not connected")
        rid = next(self._ids)
        fut: concurrent.futures.Future = concurrent.futures.Future()
        self._waiting[rid] = fut
        payload = json.dumps({"id": rid, "type": type, "data": data}, default=str)
        asyncio.run_coroutine_threadsafe(ws.send(payload), loop)
        try:
            return fut.result(timeout=timeout)
        except concurrent.futures.TimeoutError:
            raise BrowserError(f"Chrome did not answer {type} within {timeout:.0f}s")
        finally:
            self._waiting.pop(rid, None)


_bridge: BrowserBridge | Any = None


def get_bridge():
    return _bridge


def set_bridge(bridge):
    """Install a bridge (tests use a fake one)."""
    global _bridge
    _bridge = bridge


def start_bridge(write_config: bool = True) -> BrowserBridge | None:
    """Start the bridge once per process. Returns None when disabled or the port is in use."""
    global _bridge
    if _bridge is not None or not config.browser_enabled:
        return _bridge
    token = pairing_token()
    bridge = BrowserBridge(config.browser_port, token)
    if not bridge.start():
        return None
    if write_config:
        write_extension_config(config.browser_port, token)
    _bridge = bridge
    return bridge
