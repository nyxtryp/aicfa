"""Loopback control endpoint for the shared AICFA scanner engine.

The web UI never owns or reimplements market analysis. It asks the already
running autonomous worker to scan one configured market through the same
AutonomousScanEngine instance used by the automatic queue.
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .persistent_journal import _jsonable


def _market_payload(engine: Any) -> list[dict[str, Any]]:
    return [
        {
            "index": index,
            "asset": market.asset,
            "market_type": market.market_type,
            "asset_class": market.asset_class,
            "category": market.category,
        }
        for index, market in enumerate(engine.universe.markets)
    ]


def _scan_payload(engine: Any, market_index: int) -> dict[str, Any]:
    pause_until_ms = engine.pause_automatic_scanning()
    state = engine.scan_market(market_index, journal=False, enforce_timeout=False)
    market = state.result.markets[0]
    registry = engine.registry
    setups: list[dict[str, Any]] = []
    if registry is not None:
        for record in registry.current():
            if record.get("asset") == market.asset and int(record.get("last_seen_at_ms", -1)) == int(state.scanned_at_ms):
                setups.append(record)
    return {
        "ok": True,
        "scan_number": state.scan_number,
        "scanned_at_ms": state.scanned_at_ms,
        "market": {
            "index": market_index,
            "asset": market.asset,
            "diagnostics": _jsonable(market.diagnostics),
        },
        "setups": setups,
        "automatic_scan_paused_until_ms": pause_until_ms,
    }


def create_handler(engine: Any):
    class ControlHandler(BaseHTTPRequestHandler):
        server_version = "AICFA-Control/1.0"

        def _send(self, status: int, payload: Any) -> None:
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            if self.path == "/markets":
                self._send(200, {"markets": _market_payload(engine)})
                return
            self._send(404, {"error": "not_found"})

        def do_POST(self) -> None:
            if self.path != "/scan/market":
                self._send(404, {"error": "not_found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length) or b"{}")
                market_index = int(payload["market_index"])
                if market_index < 0 or market_index >= len(engine.universe.markets):
                    raise ValueError("market_index_out_of_range")
                self._send(200, _scan_payload(engine, market_index))
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                self._send(400, {"error": str(exc)})
            except Exception as exc:
                self._send(500, {"error": f"{type(exc).__name__}: {exc}"})

        def do_PUT(self) -> None:
            self._send(405, {"error": "method_not_allowed"})

        def do_DELETE(self) -> None:
            self._send(405, {"error": "method_not_allowed"})

        def log_message(self, format: str, *args: object) -> None:
            return

    return ControlHandler


def serve_control(engine: Any, *, host: str = "127.0.0.1", port: int = 8091) -> None:
    server = ThreadingHTTPServer((host, port), create_handler(engine))
    try:
        server.serve_forever()
    finally:
        server.server_close()


__all__ = ["create_handler", "serve_control"]
