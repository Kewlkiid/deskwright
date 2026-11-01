"""Serve the demo invoice page over http with a tiny JSON API, for testing the Chrome extension end to end.

    python -m engine.tools.demo_server          # http://127.0.0.1:5050

POST /api/invoices {"customer", "amount"} -> {"id", "number", "customer", "amount"}; GET /api/invoices lists them.
"""
from __future__ import annotations

import argparse
import itertools
import json
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SITE = Path(__file__).resolve().parent / "demo_site"
_ids = itertools.count(812)
INVOICES: list[dict] = []


class Handler(SimpleHTTPRequestHandler):
    def _json(self, status: int, data):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/api/invoices"):
            return self._json(200, INVOICES)
        return super().do_GET()

    def do_POST(self):
        if not self.path.startswith("/api/invoices"):
            return self._json(404, {"error": "not found"})
        data = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        n = next(_ids)
        invoice = {"id": n, "number": f"INV-{n - 770:04d}", "customer": data.get("customer"), "amount": data.get("amount")}
        INVOICES.append(invoice)
        return self._json(201, invoice)

    def log_message(self, *args):
        pass


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=5050)
    args = p.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), partial(Handler, directory=str(SITE)))
    print(f"demo site on http://127.0.0.1:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
