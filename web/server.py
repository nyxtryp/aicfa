"""AICFA public web server.

Serves the static monitoring UI and exposes a same-origin read-only /api proxy
to the local journal feed at 127.0.0.1:8090. The web process never runs the
market scanner.
"""
from __future__ import annotations

import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
FEED = "http://127.0.0.1:8090"


class Handler(SimpleHTTPRequestHandler):
    server_version = "AICFA-Web/1.0"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def _json(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self) -> None:
        # The monitoring UI is live state. Never let a browser/CDN keep an old
        # HTML/JS/CSS asset around after a deployment.
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def do_GET(self) -> None:
        if self.path == "/api" or self.path.startswith("/api/"):
            target = FEED + self.path
            try:
                with urlopen(Request(target, method="GET"), timeout=8) as response:
                    body = response.read()
                    self._json(response.status, body)
            except Exception:
                self._json(503, b'{"error":"feed_unavailable"}')
            return
        super().do_GET()

    def do_POST(self) -> None:
        if self.path.startswith("/api/"):
            self._json(405, b'{"error":"method_not_allowed"}')
            return
        self.send_error(405)

    def do_PUT(self) -> None:
        self._json(405, b'{"error":"method_not_allowed"}')

    def do_DELETE(self) -> None:
        self._json(405, b'{"error":"method_not_allowed"}')

    def log_message(self, format: str, *args: object) -> None:
        return


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "3000"))
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
