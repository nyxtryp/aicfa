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
    # Manual scans run independently; they must never pause the automatic rotation.
    state = engine.scan_market(market_index, journal=True, enforce_timeout=False)
    pause_until_ms = engine.automatic_pause_until_ms
    market = state.result.markets[0]
    registry = engine.registry
    setups: list[dict[str, Any]] = []
    watch_candidates: list[dict[str, Any]] = []
    for setup in getattr(market, "setups", ()):
        candidate = getattr(setup, "candidate", None)
        if candidate is None or str(getattr(candidate, "direction", "")).upper() not in {"LONG", "SHORT"}:
            continue
        lifecycle = getattr(setup, "lifecycle_result", None)
        lifecycle_status = str(getattr(getattr(lifecycle, "status", None), "value", getattr(lifecycle, "status", ""))).lower()
        if lifecycle_status in {"active", "tp1_hit"}:
            continue
        watch_candidates.append({
            "asset": market.asset,
            "mode": getattr(setup, "mode", ""),
            "candidate": _jsonable(candidate),
            "lifecycle_status": lifecycle_status or "waiting",
            "decision_action": str(getattr(setup, "decision_action", "wait")),
        })
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
        "watch_candidates": watch_candidates,
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
            if self.path == "/health":
                last = engine.last_state
                market = None
                if last is not None and last.result.markets:
                    market = last.result.markets[0]
                diagnostics = getattr(market, "diagnostics", None) if market is not None else None
                self._send(
                    200,
                    {
                        "ok": True,
                        "scanner": "running",
                        "scan_number": engine.scan_number,
                        "cycle_id": engine.cycle_id,
                        "universe_size": len(engine.universe.markets),
                        "automatic_scan_paused_until_ms": engine.automatic_pause_until_ms,
                        "last_scan_status": getattr(diagnostics, "status", None),
                        "last_scan_error": getattr(diagnostics, "error", ""),
                    },
                )
                return
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
                result = _scan_payload(engine, market_index)
                diagnostics = result.get("market", {}).get("diagnostics") or {}
                status = str(diagnostics.get("status", "completed")).lower()
                if status in {"error", "timeout"}:
                    self._send(
                        504 if status == "timeout" else 503,
                        {
                            "ok": False,
                            "error": "scanner_timeout" if status == "timeout" else "scanner_error",
                            "detail": diagnostics.get("error", ""),
                            "market": result.get("market", {}),
                        },
                    )
                else:
                    self._send(200, result)
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
    # A deployment can briefly race an old worker while FrostDeploy replaces
    # the process. Keep the control plane retrying its bind instead of dying
    # permanently and leaving Market Watch broken for the whole deployment.
    import time
    while True:
        try:
            server = ThreadingHTTPServer((host, port), create_handler(engine))
        except OSError as exc:
            print(
                f"AICFA market control bind failed on {host}:{port}: {exc}; retrying",
                flush=True,
            )
            time.sleep(1.0)
            continue
        try:
            server.serve_forever()
        finally:
            server.server_close()
        return


__all__ = ["create_handler", "serve_control"]
