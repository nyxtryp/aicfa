"""Read-only HTTP feed for the persistent AICFA journal."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from typing import Any
from urllib.parse import parse_qs, urlparse

from .persistent_journal import PersistentJournal
from .setup_registry import SetupRegistry


def _response_payload(journal: PersistentJournal, path: str, query: dict[str, list[str]]) -> Any:
    limit = int(query.get("limit", ["100"])[0])
    limit = max(1, min(limit, 500))
    events = journal.read(limit)

    if path == "/api/health":
        return {"ok": True, "journal": str(journal.path)}
    if path == "/api/journal/events":
        return {"events": list(events)}
    if path == "/api/journal/scans":
        return {"events": [event for event in events if event.get("event_type") == "scan"]}
    if path == "/api/journal/registry":
        registry = SetupRegistry.from_env()
        if registry is None:
            return {"setups": []}
        try:
            return {"setups": list(registry.current())}
        except Exception:
            # The journal feed remains readable even if the durable registry
            # projection is temporarily unreadable/corrupt.
            return {"setups": []}
    if path == "/api/journal/setups":
        setups: list[dict[str, Any]] = []
        for event in events:
            if event.get("event_type") != "scan":
                continue
            payload = event.get("payload", {})
            for market in payload.get("markets", []):
                for setup in market.get("setups", []):
                    setups.append({
                        "timestamp_ms": event.get("timestamp_ms"),
                        "asset": market.get("asset"),
                        "setup": setup,
                    })
        return {"setups": setups}
    raise KeyError(path)


def create_handler(journal: PersistentJournal):
    class JournalFeedHandler(BaseHTTPRequestHandler):
        server_version = "AICFA-Journal/1.0"

        def _send(self, status: int, payload: Any) -> None:
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            try:
                payload = _response_payload(journal, parsed.path, parse_qs(parsed.query))
            except (KeyError, ValueError):
                self._send(404, {"error": "not_found"})
                return
            except OSError:
                self._send(503, {"error": "journal_unavailable"})
                return
            self._send(200, payload)

        def do_POST(self) -> None:
            self._send(405, {"error": "method_not_allowed"})

        def do_PUT(self) -> None:
            self._send(405, {"error": "method_not_allowed"})

        def do_DELETE(self) -> None:
            self._send(405, {"error": "method_not_allowed"})

        def log_message(self, format: str, *args: object) -> None:
            return

    return JournalFeedHandler


def serve_journal(
    journal: PersistentJournal,
    *,
    host: str = "127.0.0.1",
    port: int = 8090,
) -> None:
    server = ThreadingHTTPServer((host, port), create_handler(journal))
    try:
        server.serve_forever()
    finally:
        server.server_close()


__all__ = ["create_handler", "serve_journal"]
