"""Public derivatives market-data adapters for AICFA.

Normalizes funding, open interest, liquidations and mark price from real
exchange endpoints/market streams into one causal schema. No API keys are
required. A zero-liquidation observation is only emitted when the public
liquidation stream was successfully connected and observed for the polling
window; it is not treated as liquidation evidence.
"""
from __future__ import annotations

import json
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd
import websocket


DERIVATIVE_COLUMNS = (
    "timestamp",
    "funding_rate",
    "open_interest",
    "liquidation_volume",
    "long_liquidation_volume",
    "short_liquidation_volume",
    "mark_price",
)


class DerivativesTransportError(RuntimeError):
    pass


def _request_json(url: str, *, timeout_seconds: float = 10.0):
    request = Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "AICFA/1.0"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            return json.load(response)
    except Exception as exc:
        raise DerivativesTransportError(f"derivatives request failed: {exc}") from exc


def _frame(rows: list[dict]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=DERIVATIVE_COLUMNS)
    frame = pd.DataFrame(rows)
    for column in DERIVATIVE_COLUMNS:
        if column not in frame.columns:
            frame[column] = pd.NA
    frame = frame[list(DERIVATIVE_COLUMNS)]
    frame["timestamp"] = pd.to_numeric(frame["timestamp"], errors="coerce")
    frame = frame.dropna(subset=["timestamp"]).copy()
    frame["timestamp"] = frame["timestamp"].astype("int64")
    for column in DERIVATIVE_COLUMNS[1:]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return (
        frame.sort_values("timestamp")
        .drop_duplicates("timestamp", keep="last")
        .reset_index(drop=True)
    )


def _collect_binance_liquidations(symbol: str, *, timeout_seconds: float) -> list[dict]:
    """Collect the public market liquidation stream for a short causal window."""
    ws = websocket.create_connection(
        f"wss://fstream.binance.com/ws/{symbol.lower()}@forceOrder",
        timeout=min(float(timeout_seconds), 2.0),
    )
    rows: list[dict] = []
    deadline = time.monotonic() + min(float(timeout_seconds), 2.0)
    try:
        while time.monotonic() < deadline:
            try:
                raw = ws.recv()
            except Exception:
                break
            if not raw:
                continue
            payload = json.loads(raw)
            order = payload.get("o", {})
            ts = int(order.get("T") or payload.get("E") or 0)
            if not ts:
                continue
            qty = float(order.get("z") or order.get("q") or 0.0)
            price = float(order.get("ap") or order.get("p") or 0.0)
            volume = qty * price if price > 0 else qty
            side = str(order.get("S", "")).upper()
            rows.append({
                "timestamp": ts,
                "liquidation_volume": volume,
                "long_liquidation_volume": volume if side == "SELL" else 0.0,
                "short_liquidation_volume": volume if side == "BUY" else 0.0,
            })
    finally:
        ws.close()
    return rows


def _collect_bybit_liquidations(symbol: str, *, timeout_seconds: float) -> list[dict]:
    """Collect the public Bybit all-liquidation stream for a short window."""
    ws = websocket.create_connection(
        "wss://stream.bybit.com/v5/public/linear",
        timeout=min(float(timeout_seconds), 2.0),
    )
    rows: list[dict] = []
    try:
        ws.send(json.dumps({"op": "subscribe", "args": [f"allLiquidation.{symbol}"]}))
        deadline = time.monotonic() + min(float(timeout_seconds), 2.0)
        while time.monotonic() < deadline:
            try:
                raw = ws.recv()
            except Exception:
                break
            if not raw:
                continue
            payload = json.loads(raw)
            for item in payload.get("data", []) if isinstance(payload.get("data"), list) else []:
                ts = int(item.get("T") or payload.get("ts") or 0)
                if not ts:
                    continue
                qty = float(item.get("v") or 0.0)
                price = float(item.get("p") or 0.0)
                volume = qty * price if price > 0 else qty
                side = str(item.get("S", "")).upper()
                rows.append({
                    "timestamp": ts,
                    "liquidation_volume": volume,
                    "long_liquidation_volume": volume if side == "SELL" else 0.0,
                    "short_liquidation_volume": volume if side == "BUY" else 0.0,
                })
    finally:
        ws.close()
    return rows


class BinanceDerivativesProvider:
    exchange = "binance"

    def __init__(self, *, timeout_seconds: float = 10.0) -> None:
        self.timeout_seconds = float(timeout_seconds)

    def fetch_derivatives(self, *, symbol: str, limit: int = 200) -> pd.DataFrame:
        symbol = symbol.replace("/", "").replace("-", "").replace("_", "").upper()
        funding = _request_json(
            "https://fapi.binance.com/fapi/v1/fundingRate?"
            + urlencode({"symbol": symbol, "limit": min(int(limit), 1000)}),
            timeout_seconds=self.timeout_seconds,
        )
        oi = _request_json(
            "https://fapi.binance.com/futures/data/openInterestHist?"
            + urlencode({"symbol": symbol, "period": "5m", "limit": min(int(limit), 500)}),
            timeout_seconds=self.timeout_seconds,
        )
        mark = _request_json(
            "https://fapi.binance.com/fapi/v1/premiumIndex?"
            + urlencode({"symbol": symbol}),
            timeout_seconds=self.timeout_seconds,
        )
        liquidation_rows = _collect_binance_liquidations(
            symbol, timeout_seconds=self.timeout_seconds
        )

        rows: dict[int, dict] = {}
        for item in funding if isinstance(funding, list) else []:
            ts = int(item["fundingTime"])
            rows.setdefault(ts, {})["funding_rate"] = float(item["fundingRate"])
        for item in oi if isinstance(oi, list) else []:
            ts = int(item["timestamp"])
            rows.setdefault(ts, {})["open_interest"] = float(
                item.get("sumOpenInterestValue", item.get("sumOpenInterest", 0.0))
            )
        if isinstance(mark, dict):
            ts = int(mark.get("time") or time.time() * 1000)
            rows.setdefault(ts, {})["mark_price"] = float(mark["markPrice"])
            if "lastFundingRate" in mark:
                rows[ts].setdefault("funding_rate", float(mark["lastFundingRate"]))

        for item in liquidation_rows:
            ts = int(item["timestamp"])
            row = rows.setdefault(ts, {})
            for column in (
                "liquidation_volume",
                "long_liquidation_volume",
                "short_liquidation_volume",
            ):
                row[column] = row.get(column, 0.0) + float(item[column])

        return _frame([{"timestamp": ts, **values} for ts, values in rows.items()])


class BybitDerivativesProvider:
    exchange = "bybit"

    def __init__(self, *, timeout_seconds: float = 10.0) -> None:
        self.timeout_seconds = float(timeout_seconds)

    def _get(self, path: str, params: dict[str, object]) -> dict:
        payload = _request_json(
            "https://api.bybit.com/v5/market/" + path + "?" + urlencode(params),
            timeout_seconds=self.timeout_seconds,
        )
        if not isinstance(payload, dict) or payload.get("retCode") != 0:
            raise DerivativesTransportError(
                f"Bybit API error: {payload.get('retCode') if isinstance(payload, dict) else payload}"
            )
        return payload

    def fetch_derivatives(self, *, symbol: str, limit: int = 200) -> pd.DataFrame:
        symbol = symbol.replace("/", "").replace("-", "").replace("_", "").upper()
        funding = self._get(
            "funding/history",
            {"category": "linear", "symbol": symbol, "limit": min(int(limit), 200)},
        )
        oi = self._get(
            "open-interest",
            {"category": "linear", "symbol": symbol, "intervalTime": "5min", "limit": min(int(limit), 200)},
        )
        ticker = self._get("tickers", {"category": "linear", "symbol": symbol})
        liquidation_rows = _collect_bybit_liquidations(
            symbol, timeout_seconds=self.timeout_seconds
        )

        rows: dict[int, dict] = {}
        for item in funding.get("result", {}).get("list", []):
            ts = int(item["fundingRateTimestamp"])
            rows.setdefault(ts, {})["funding_rate"] = float(item["fundingRate"])
        for item in oi.get("result", {}).get("list", []):
            ts = int(item["timestamp"])
            rows.setdefault(ts, {})["open_interest"] = float(
                item.get("openInterestValue", item.get("openInterest", 0.0))
            )
        items = ticker.get("result", {}).get("list", [])
        if items:
            item = items[0]
            ts = int(ticker.get("time") or time.time() * 1000)
            rows.setdefault(ts, {})["mark_price"] = float(item["markPrice"])
            if item.get("fundingRate") is not None:
                rows[ts].setdefault("funding_rate", float(item["fundingRate"]))

        for item in liquidation_rows:
            ts = int(item["timestamp"])
            row = rows.setdefault(ts, {})
            for column in (
                "liquidation_volume",
                "long_liquidation_volume",
                "short_liquidation_volume",
            ):
                row[column] = row.get(column, 0.0) + float(item[column])

        return _frame([{"timestamp": ts, **values} for ts, values in rows.items()])


class FallbackDerivativesProvider:
    """Capability-aware Binance -> Bybit fallback with no fabricated fields."""

    def __init__(self, providers=None) -> None:
        self.providers = tuple(
            providers or (BinanceDerivativesProvider(), BybitDerivativesProvider())
        )

    def fetch_derivatives(
        self, *, symbol: str, limit: int = 200
    ) -> tuple[pd.DataFrame, str]:
        attempts: list[str] = []
        for provider in self.providers:
            try:
                frame = provider.fetch_derivatives(symbol=symbol, limit=limit)
                if frame.empty:
                    raise ValueError("provider returned empty derivatives data")
                return frame, provider.exchange
            except Exception as exc:
                attempts.append(f"{provider.exchange}: {exc}")
        raise RuntimeError(
            "all derivatives providers failed: " + "; ".join(attempts)
        )
