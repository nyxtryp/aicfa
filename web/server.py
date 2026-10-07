"""AICFA public web server.

Serves the static monitoring UI, proxies read-only journal data, and forwards
market-watch scan requests to the loopback control endpoint owned by the
already-running scanner worker. The web process never runs market analysis.
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
SRC = ROOT.parent / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
FEED = "http://127.0.0.1:8090"
CONTROL = "http://127.0.0.1:8091"



DATA_DIR = Path(os.getenv("AICFA_DATA_DIR", str(ROOT.parent / "data")))
RAW_DIR = DATA_DIR / "raw"

def _journal_payload(path: str, query: dict[str, list[str]]) -> bytes:
    """Serve the terminal journal directly from the shared persistent data directory."""
    from src.aicfa.persistent_journal import PersistentJournal
    from src.aicfa.setup_registry import SetupRegistry

    try:
        limit = int(query.get("limit", ["100"])[0])
    except (TypeError, ValueError):
        limit = 100
    limit = max(1, min(limit, 500))
    journal = PersistentJournal(DATA_DIR / "journal" / "events.jsonl")
    events = journal.read(limit)

    if path == "/api/health":
        payload = {"ok": True, "journal": str(journal.path)}
    elif path == "/api/journal/events":
        payload = {"events": list(events)}
    elif path == "/api/journal/scans":
        payload = {"events": [e for e in events if e.get("event_type") == "scan"]}
    elif path == "/api/journal/setups":
        setups = []
        for event in events:
            if event.get("event_type") != "scan":
                continue
            event_payload = event.get("payload", {})
            for market in event_payload.get("markets", []):
                for setup in market.get("setups", []):
                    setups.append({"timestamp_ms": event.get("timestamp_ms"), "asset": market.get("asset"), "setup": setup})
        payload = {"setups": setups}
    elif path == "/api/journal/registry":
        registry = SetupRegistry.from_env()
        payload = {"setups": list(registry.current()) if registry is not None else []}
    else:
        raise KeyError(path)
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


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

    aliases = {"SHIB_USDT": "1000SHIB_USDT"}
    storage_symbols = [normalized]
    if normalized in aliases:
        storage_symbols.append(aliases[normalized])
    candidates = [p for symbol_name in storage_symbols for p in (
        RAW_DIR / symbol_name / f"{timeframe}.csv",
        RAW_DIR / symbol_name.replace("_USDT", "_USDT_USDT") / f"{timeframe}.csv",
    )]
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
        quote = aliases.get(normalized, normalized).replace("_", "")
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



def _market_prices() -> bytes:
    universe_path = ROOT.parent / "config" / "market_universe.json"
    payload = json.loads(universe_path.read_text(encoding="utf-8"))
    markets = payload.get("markets", [])
    endpoints = {
        "spot": "https://api.binance.com/api/v3/ticker/price",
        "futures": "https://fapi.binance.com/fapi/v1/ticker/price",
    }
    ticker_maps = {}
    for market_type, endpoint in endpoints.items():
        try:
            with urlopen(Request(endpoint, method="GET"), timeout=8) as response:
                tickers = json.loads(response.read().decode("utf-8"))
            ticker_maps[market_type] = {
                str(item.get("symbol", "")).upper(): float(item["price"])
                for item in tickers
                if item.get("symbol") and item.get("price") is not None
            }
        except Exception:
            ticker_maps[market_type] = {}

    prices = {}
    for index, item in enumerate(markets):
        asset = str(item.get("asset", "")).upper()
        market_type = str(item.get("market_type", "futures")).lower()
        symbol = asset.replace("/", "").replace(":", "")
        price = ticker_maps.get(market_type, {}).get(symbol)
        if price is not None:
            prices[str(index)] = price
    return json.dumps({"prices": prices}, separators=(",", ":")).encode("utf-8")


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

    def _control_request(self, method: str, path: str, body: bytes | None = None) -> None:
        target = CONTROL + path
        request = Request(target, data=body, method=method)
        if body is not None:
            request.add_header("Content-Type", "application/json")
        try:
            # The scanner has a 90s per-market budget. The web proxy
            # must not give up after 25s and falsely report a healthy scanner
            # as unavailable.
            with urlopen(request, timeout=100) as response:
                self._json(response.status, response.read())
        except Exception as exc:
            self._json(503, json.dumps({"error": "scanner_unavailable", "detail": str(exc)}).encode("utf-8"))

    def end_headers(self) -> None:
        # The monitoring UI is live state. Never let a browser/CDN keep an old
        # HTML/JS/CSS asset around after a deployment.
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()

    def do_GET(self) -> None:
        if urlsplit(self.path).path == "/api/market-prices":
            try:
                self._json(200, _market_prices())
            except Exception:
                self._json(503, b'{"error":"market_prices_unavailable","prices":{}}')
            return
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
        if urlsplit(self.path).path == "/api/markets":
            try:
                universe_path = ROOT.parent / "config" / "market_universe.json"
                payload = json.loads(universe_path.read_text(encoding="utf-8"))
                markets = [
                    {
                        "index": index,
                        "asset": item["asset"],
                        "market_type": item.get("market_type", "futures"),
                        "asset_class": item.get("asset_class", ""),
                        "category": item.get("category", ""),
                    }
                    for index, item in enumerate(payload.get("markets", []))
                ]
                self._json(200, json.dumps({"markets": markets}, ensure_ascii=False).encode("utf-8"))
            except Exception as exc:
                self._json(500, json.dumps({"error": "market_universe_unavailable", "detail": str(exc)}).encode("utf-8"))
            return
        if self.path == "/api" or self.path.startswith("/api/"):
            from urllib.parse import parse_qs
            parsed = urlsplit(self.path)
            if parsed.path in {
                "/api/health",
                "/api/journal/events",
                "/api/journal/scans",
                "/api/journal/setups",
                "/api/journal/registry",
            }:
                try:
                    self._json(200, _journal_payload(parsed.path, parse_qs(parsed.query)))
                except Exception as exc:
                    self._json(503, json.dumps({"error": "journal_unavailable", "detail": str(exc)}).encode("utf-8"))
                return
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
        if self.path == "/api/market-scan":
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            self._control_request("POST", "/scan/market", body)
            return
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
