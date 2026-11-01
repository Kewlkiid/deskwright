"""Engine entry point, spawned by Electron. Prints one JSON line with the port and token, then serves."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import sys
import threading


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--token", default=None)
    args = parser.parse_args()

    from .server import Server

    server = Server(token=args.token or os.environ.get("AGENT_SESSION_TOKEN"))

    # Electron's global shortcut sends SIGUSR1 as a second, UI-independent stop path.
    if hasattr(signal, "SIGUSR1"):
        signal.signal(signal.SIGUSR1, lambda *_: server.agent.stop())

    # Exit when the parent closes our stdin (Electron quit or crashed).
    def watch_stdin():
        try:
            while sys.stdin.read(1):
                pass
        except Exception:
            pass
        os._exit(0)

    if not sys.stdin.isatty():
        threading.Thread(target=watch_stdin, daemon=True).start()

    def ready(port, token):
        print(json.dumps({"type": "ready", "port": port, "token": token}), flush=True)

    try:
        asyncio.run(server.serve(args.port, ready))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
