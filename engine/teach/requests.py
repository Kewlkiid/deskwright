"""Requests from other programs to teach a task: "show it once".

`engine.cli teach --describe ...` writes DATA_DIR/teach_request.json and opens the app; the engine server picks it up
(take_request) when its window is connected, shows it, and fills in the name and description when recording stops.
A saved task records the request_id, so the asker can tell which task answers its request.
"""
from __future__ import annotations

import json
import time

from ..config import DATA_DIR

PATH = DATA_DIR / "teach_request.json"


def put_request(describe: str, name: str = "", request_id: str | None = None) -> dict:
    req = {"describe": describe, "name": name, "request_id": request_id, "at": time.time()}
    tmp = PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(req))
    tmp.replace(PATH)
    return req


def take_request() -> dict | None:
    try:
        req = json.loads(PATH.read_text())
    except (OSError, ValueError):
        return None
    try:
        PATH.unlink()
    except OSError:
        pass
    return req if isinstance(req, dict) and req.get("describe") else None
