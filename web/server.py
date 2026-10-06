"""AICFA public web server.

Serves the static monitoring UI and exposes a same-origin read-only /api proxy
to the local journal feed at 127.0.0.1:8090. The web process never runs the
market scanner.
"""
from __future__ import annotations

import csv
import json
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
FEED = "http://127.0.0.1:8090"



DATA_DIR = Path(os.getenv("AICFA_DATA_DIR", str(ROOT.parent / "data")))
RAW_DIR = DATA_DIR / "raw"

def _chart_data(symbol: str, timeframe: str, limit: int = 160) -> bytes:
    raw = symbol.strip().upper()
    normalized = raw.replace("/", "_").replace(":", "_")
    if normalized.endswith("_USDT_USDT"):
        normalized = normalized[:-5]
    elif normalized.endswith("USDT") and "_" not in normalized:
        normalized = normalized[:-4] + "_USDT"
    if not normalized or any(part in normalized for part in ("..", "/", "\\")):
        raise ValueError("invalid symbol")
    if timeframe not in {"1m", "5m", "15m", "1h", "4h", "1d", "1w"}:
        raise ValueError("invalid timeframe")
    try:
        limit = max(20, min(int(limit), 300))
    except (TypeError, ValueError):
        limit = 160

    candidates = [
        RAW_DIR / normalized / f"{timeframe}.csv",
        RAW_DIR / normalized.replace("_USDT", "_USDT_USDT") / f"{timeframe}.csv",
    ]
    if raw.endswith(":USDT"):
        candidates.append(RAW_DIR / raw.replace("/", "_").replace(":", "_") / f"{timeframe}.csv")

    rows = []
    path = next((p for p in candidates if p.is_file()), None)
    if path is not None:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                try:
                    rows.append({
                        "timestamp": int(row["timestamp"]),
                        "open": float(row["open"]),
                        "high": float(row["high"]),
                        "low": float(row["low"]),
                        "close": float(row["close"]),
                        "volume": float(row["volume"]),
                    })
                except (KeyError, TypeError, ValueError):
                    continue

    # Scanner markets can be Binance USD-M perpetuals (e.g. PEPE/USDT:USDT)
    # while the historical downloader currently stores spot symbols locally.
    # For a chart only, use Binance's public kline endpoint when no local file
    # exists. This is read-only and keeps the scanner/journal untouched.
    if not rows:
        from urllib.parse import urlencode
        quote = normalized.replace("_", "")
        if raw.endswith(":USDT"):
            endpoint = "https://fapi.binance.com/fapi/v1/klines"
        else:
            endpoint = "https://api.binance.com/api/v3/klines"
        query = urlencode({"symbol": quote, "interval": timeframe, "limit": limit})
        try:
            with urlopen(Request(endpoint + "?" + query, method="GET"), timeout=8) as response:
                payload = json.loads(response.read().decode("utf-8"))
            for row in payload:
                rows.append({
                    "timestamp": int(row[0]),
                    "open": float(row[1]),
                    "high": float(row[2]),
                    "low": float(row[3]),
                    "close": float(row[4]),
                    "volume": float(row[5]),
                })
        except Exception:
            rows = []

    if not rows:
        raise FileNotFoundError(normalized)

    return json.dumps(
        {"symbol": symbol, "timeframe": timeframe, "candles": rows[-limit:]},
        separators=(",", ":"),
    ).encode("utf-8")


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
        if self.path.startswith("/api/chart"):
            from urllib.parse import parse_qs
            query = parse_qs(urlsplit(self.path).query)
            try:
                self._json(200, _chart_data(query.get("symbol", [""])[0], query.get("timeframe", ["15m"])[0], query.get("limit", ["160"])[0]))
            except FileNotFoundError:
                self._json(404, b'{"error":"chart_data_not_found"}')
            except ValueError as exc:
                self._json(400, json.dumps({"error": str(exc)}).encode("utf-8"))
            except Exception:
                self._json(500, b'{"error":"chart_data_unavailable"}')
            return
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
