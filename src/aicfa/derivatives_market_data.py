"""Public derivatives market-data adapters for AICFA.

Normalizes funding, open interest, liquidations and mark price from real
exchange endpoints into one causal schema. No API keys are required.
"""
from __future__ import annotations

import json
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd


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
        liquidations = _request_json(
            "https://fapi.binance.com/fapi/v1/allForceOrders?"
            + urlencode({"symbol": symbol, "limit": min(int(limit), 1000)}),
            timeout_seconds=self.timeout_seconds,
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

        for item in liquidations if isinstance(liquidations, list) else []:
            ts = int(item.get("time") or item.get("T") or 0)
            if not ts:
                continue
            qty = float(item.get("origQty") or item.get("executedQty") or item.get("qty") or 0.0)
            price = float(item.get("price") or 0.0)
            volume = qty * price if price > 0 else qty
            row = rows.setdefault(ts, {})
            row["liquidation_volume"] = row.get("liquidation_volume", 0.0) + volume
            side = str(item.get("side", "")).upper()
            if side == "SELL":
                row["long_liquidation_volume"] = row.get("long_liquidation_volume", 0.0) + volume
            elif side == "BUY":
                row["short_liquidation_volume"] = row.get("short_liquidation_volume", 0.0) + volume

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
        ticker = self._get(
            "tickers", {"category": "linear", "symbol": symbol}
        )
        # Public REST does not expose the all-liquidation stream as a historical
        # endpoint. Liquidations therefore remain unavailable here until a
        # websocket/event collector is attached; we never fabricate them.
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
        return _frame([{"timestamp": ts, **values} for ts, values in rows.items()])


class FallbackDerivativesProvider:
    """Capability-aware Binance -> Bybit fallback with no fabricated fields."""

    def __init__(self, providers=None) -> None:
        self.providers = tuple(providers or (BinanceDerivativesProvider(), BybitDerivativesProvider()))

    def fetch_derivatives(self, *, symbol: str, limit: int = 200) -> tuple[pd.DataFrame, str]:
        attempts: list[str] = []
        for provider in self.providers:
            try:
                frame = provider.fetch_derivatives(symbol=symbol, limit=limit)
                if frame.empty:
                    raise ValueError("provider returned empty derivatives data")
                return frame, provider.exchange
            except Exception as exc:
                attempts.append(f"{provider.exchange}: {exc}")
        raise RuntimeError("all derivatives providers failed: " + "; ".join(attempts))
