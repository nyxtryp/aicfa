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
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd
import websocket


DERIVATIVE_COVERAGE_FIELDS = ("funding_rate", "open_interest", "mark_price")
DERIVATIVE_OPTIONAL_FIELDS = ("liquidation_volume", "long_liquidation_volume", "short_liquidation_volume")
DERIVATIVE_PROVIDER_TIMEOUT_SECONDS = 3.0
DERIVATIVE_MAX_CONCURRENT_PROVIDERS = 6

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


def _merge_sources(
    *,
    funding_rows: list[dict],
    oi_rows: list[dict],
    mark_row: dict | None,
    liquidation_rows: list[dict],
) -> pd.DataFrame:
    """Build a causal common timeline from independently timestamped sources.

    Funding and OI endpoints do not normally publish at identical timestamps.
    They therefore must not be joined by exact timestamp. OI is a state carried
    forward from the latest known observation; funding is carried forward from
    its latest known observation; the current mark is added at its own timestamp.
    This preserves causality while producing rows accepted by build_derivatives.
    """
    oi = pd.DataFrame(oi_rows)
    funding = pd.DataFrame(funding_rows)

    oi["timestamp"] = pd.to_numeric(oi["timestamp"], errors="coerce")
    oi["open_interest"] = pd.to_numeric(oi["open_interest"], errors="coerce")
    oi = (
        oi.dropna(subset=["timestamp", "open_interest"])
        .sort_values("timestamp")
        .drop_duplicates("timestamp", keep="last")
    )
    timeline_parts = []
    if not oi.empty:
        timeline_parts.append(oi[["timestamp"]].copy())
    if not funding.empty:
        funding_ts = pd.to_numeric(funding["timestamp"], errors="coerce").dropna()
        if not funding_ts.empty:
            timeline_parts.append(pd.DataFrame({"timestamp": funding_ts.astype("int64")}))
    if mark_row is not None:
        mark_ts = pd.to_numeric(pd.Series([mark_row.get("timestamp")]), errors="coerce").iloc[0]
        mark_price = pd.to_numeric(pd.Series([mark_row.get("mark_price")]), errors="coerce").iloc[0]
        if pd.notna(mark_ts) and pd.notna(mark_price):
            timeline_parts.append(pd.DataFrame({"timestamp": [int(mark_ts)]}))
    if not timeline_parts:
        return _frame([])

    timeline = pd.concat(timeline_parts, ignore_index=True)
    if mark_row is not None:
        mark_ts = pd.to_numeric(pd.Series([mark_row.get("timestamp")]), errors="coerce").iloc[0]
        mark_price = pd.to_numeric(pd.Series([mark_row.get("mark_price")]), errors="coerce").iloc[0]
        if pd.notna(mark_ts) and pd.notna(mark_price):
            timeline = pd.concat(
                [timeline, pd.DataFrame({"timestamp": [int(mark_ts)]})],
                ignore_index=True,
            )

    timeline["timestamp"] = pd.to_numeric(timeline["timestamp"], errors="coerce")
    timeline = (
        timeline.dropna()
        .astype({"timestamp": "int64"})
        .drop_duplicates("timestamp")
        .sort_values("timestamp")
        .reset_index(drop=True)
    )

    if oi.empty:
        oi_state = timeline.copy()
        oi_state["open_interest"] = pd.NA
    else:
        oi_state = pd.merge_asof(
            timeline,
            oi[["timestamp", "open_interest"]].sort_values("timestamp"),
            on="timestamp",
            direction="backward",
            allow_exact_matches=True,
        )
    funding["timestamp"] = pd.to_numeric(funding["timestamp"], errors="coerce")
    funding["funding_rate"] = pd.to_numeric(funding["funding_rate"], errors="coerce")
    funding = (
        funding.dropna(subset=["timestamp", "funding_rate"])
        .sort_values("timestamp")
        .drop_duplicates("timestamp", keep="last")
    )
    if funding.empty:
        aligned = oi_state.copy()
        aligned["funding_rate"] = pd.NA
    else:
        aligned = pd.merge_asof(
            oi_state.sort_values("timestamp"),
            funding[["timestamp", "funding_rate"]].sort_values("timestamp"),
            on="timestamp",
            direction="backward",
            allow_exact_matches=True,
        )

    if mark_row is not None:
        mark_ts = pd.to_numeric(pd.Series([mark_row.get("timestamp")]), errors="coerce").iloc[0]
        mark_price = pd.to_numeric(pd.Series([mark_row.get("mark_price")]), errors="coerce").iloc[0]
        if pd.notna(mark_ts) and pd.notna(mark_price):
            aligned["mark_price"] = pd.NA
            aligned.loc[aligned["timestamp"] == int(mark_ts), "mark_price"] = float(mark_price)

    if liquidation_rows:
        liquidations = pd.DataFrame(liquidation_rows)
        liquidations["timestamp"] = pd.to_numeric(liquidations["timestamp"], errors="coerce")
        for column in (
            "liquidation_volume",
            "long_liquidation_volume",
            "short_liquidation_volume",
        ):
            liquidations[column] = pd.to_numeric(liquidations[column], errors="coerce").fillna(0.0)
        liquidations = (
            liquidations.dropna(subset=["timestamp"])
            .groupby("timestamp", as_index=False)[
                [
                    "liquidation_volume",
                    "long_liquidation_volume",
                    "short_liquidation_volume",
                ]
            ]
            .sum()
        )
        aligned = aligned.merge(liquidations, on="timestamp", how="left", sort=True)

    return _frame(aligned.to_dict("records"))


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

        funding_rows = [
            {"timestamp": int(item["fundingTime"]), "funding_rate": float(item["fundingRate"])}
            for item in funding
            if isinstance(item, dict)
        ]
        oi_rows = [
            {
                "timestamp": int(item["timestamp"]),
                "open_interest": float(
                    item.get("sumOpenInterestValue", item.get("sumOpenInterest", 0.0))
                ),
            }
            for item in oi
            if isinstance(item, dict)
        ]
        mark_row = None
        if isinstance(mark, dict):
            mark_row = {
                "timestamp": int(mark.get("time") or time.time() * 1000),
                "mark_price": float(mark["markPrice"]),
            }
            if "lastFundingRate" in mark:
                funding_rows.append({
                    "timestamp": mark_row["timestamp"],
                    "funding_rate": float(mark["lastFundingRate"]),
                })

        return _merge_sources(
            funding_rows=funding_rows,
            oi_rows=oi_rows,
            mark_row=mark_row,
            liquidation_rows=liquidation_rows,
        )


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

        funding_rows = [
            {
                "timestamp": int(item["fundingRateTimestamp"]),
                "funding_rate": float(item["fundingRate"]),
            }
            for item in funding.get("result", {}).get("list", [])
        ]
        oi_rows = [
            {
                "timestamp": int(item["timestamp"]),
                "open_interest": float(
                    item.get("openInterestValue", item.get("openInterest", 0.0))
                ),
            }
            for item in oi.get("result", {}).get("list", [])
        ]
        mark_row = None
        items = ticker.get("result", {}).get("list", [])
        if items:
            item = items[0]
            mark_row = {
                "timestamp": int(ticker.get("time") or time.time() * 1000),
                "mark_price": float(item["markPrice"]),
            }
            if item.get("fundingRate") is not None:
                funding_rows.append({
                    "timestamp": mark_row["timestamp"],
                    "funding_rate": float(item["fundingRate"]),
                })

        return _merge_sources(
            funding_rows=funding_rows,
            oi_rows=oi_rows,
            mark_row=mark_row,
            liquidation_rows=liquidation_rows,
        )


class FallbackDerivativesProvider:
    """Universal per-field derivatives fallback across allowed venues.\n\n    Each derivative field is independently sourced and causally merged. The\n    chain stops as soon as the minimum coverage target (funding, OI, mark) is complete;\n    liquidation fields remain best-effort context and never justify treating derivatives as a setup prerequisite or waiting on\n    slow or unsupported venues.\n    """

    EXCHANGES = (
        "binance", "bybit", "okx", "bitget", "gateio", "kucoin", "mexc",
        "kraken", "coinbase", "bitfinex", "bingx", "htx", "coinex",
        "whitebit", "cryptocom", "bitrue", "bitstamp", "gemini", "upbit",
    )

    def __init__(self, providers=None, *, provider_timeout_seconds: float = DERIVATIVE_PROVIDER_TIMEOUT_SECONDS) -> None:
        self.provider_timeout_seconds = float(provider_timeout_seconds)
        self.providers = tuple(
            providers
            or (
                BinanceDerivativesProvider(timeout_seconds=self.provider_timeout_seconds),
                BybitDerivativesProvider(timeout_seconds=self.provider_timeout_seconds),
                *(CcxtDerivativesProvider(exchange, timeout_seconds=self.provider_timeout_seconds) for exchange in self.EXCHANGES[2:]),
            )
        )

    @staticmethod
    def _native_symbol(provider, symbol: str, venue_symbols) -> str | None:
        if not venue_symbols:
            return None
        provider_name = str(getattr(provider, "exchange", "")).lower()
        aliases = {"gate": "gateio"}
        for venue, native in venue_symbols:
            if aliases.get(str(venue).lower(), str(venue).lower()) == provider_name:
                return native
        return None

    @staticmethod
    def _combine(frames: list[tuple[pd.DataFrame, str]]) -> tuple[pd.DataFrame, str]:
        if not frames:
            return _frame([]), ""
        timeline = pd.concat(
            [frame[["timestamp"]] for frame, _ in frames if not frame.empty],
            ignore_index=True,
        )
        if timeline.empty:
            return _frame([]), ""
        timeline["timestamp"] = pd.to_numeric(timeline["timestamp"], errors="coerce")
        timeline = (
            timeline.dropna()
            .astype({"timestamp": "int64"})
            .drop_duplicates("timestamp")
            .sort_values("timestamp")
            .reset_index(drop=True)
        )
        result = timeline
        for column in DERIVATIVE_COLUMNS[1:]:
            source_frames = [
                frame[["timestamp", column]].dropna(subset=[column]).copy()
                for frame, _ in frames
                if column in frame.columns and frame[column].notna().any()
            ]
            if not source_frames:
                result[column] = pd.NA
                continue
            series = pd.concat(source_frames, ignore_index=True)
            series["timestamp"] = pd.to_numeric(series["timestamp"], errors="coerce")
            series[column] = pd.to_numeric(series[column], errors="coerce")
            series = (
                series.dropna(subset=["timestamp", column])
                .sort_values("timestamp")
                .drop_duplicates("timestamp", keep="last")
            )
            result = pd.merge_asof(
                result.sort_values("timestamp"),
                series[["timestamp", column]].sort_values("timestamp"),
                on="timestamp",
                direction="backward",
                allow_exact_matches=True,
            )
        field_sources = []
        for column in DERIVATIVE_COLUMNS[1:]:
            names = [
                name for frame, name in frames
                if column in frame.columns and frame[column].notna().any()
            ]
            if names:
                field_sources.append(f"{column}={names[0]}")
        sources = ",".join(field_sources)
        return _frame(result.to_dict("records")), sources

    def _fetch_provider_with_timeout(self, provider, kwargs):
        """Hard-bound one provider attempt so one venue cannot stall fallback."""
        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(provider.fetch_derivatives, **kwargs)
        try:
            return future.result(timeout=self.provider_timeout_seconds)
        except FuturesTimeoutError as exc:
            future.cancel()
            raise TimeoutError(
                f"{provider.exchange} derivative provider timed out after "
                f"{self.provider_timeout_seconds:.1f}s"
            ) from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _provider_kwargs(self, provider, symbol: str, limit: int, venue_symbols):
        native_symbol = self._native_symbol(provider, symbol, venue_symbols)
        kwargs = {"symbol": symbol, "limit": limit}
        if native_symbol is not None:
            kwargs["native_symbol"] = native_symbol
        return kwargs

    def _attempt_provider(self, provider, *, symbol: str, limit: int, venue_symbols):
        kwargs = self._provider_kwargs(provider, symbol, limit, venue_symbols)
        try:
            return self._fetch_provider_with_timeout(provider, kwargs)
        except TypeError:
            return self._fetch_provider_with_timeout(
                provider,
                {"symbol": symbol, "limit": limit},
            )

    def fetch_derivatives(
        self,
        *,
        symbol: str,
        limit: int = 200,
        venue_symbols: tuple[tuple[str, str], ...] = (),
    ) -> tuple[pd.DataFrame, str]:
        """Fetch derivative evidence with bounded parallel venue fallback.

        Providers are attempted in small concurrent batches so one slow or
        unsupported venue cannot consume the whole fallback budget. Results
        are still combined field-by-field and the batch loop stops as soon as
        funding, open interest and mark price have real observations.
        """
        attempts: list[str] = []
        frames: list[tuple[pd.DataFrame, str]] = []
        providers = iter(self.providers)

        # Probe the highest-priority provider alone first. This preserves the
        # strict early-stop contract: if it supplies all coverage fields, no
        # lower-priority provider is even called. Only after that probe fails
        # to complete coverage do we fan out the remaining venues in bounded
        # concurrent batches.
        try:
            first = next(providers)
        except StopIteration:
            first = None

        if first is not None:
            try:
                frame = self._attempt_provider(
                    first,
                    symbol=symbol,
                    limit=limit,
                    venue_symbols=venue_symbols,
                )
                if not frame.empty:
                    frames.append((frame, first.exchange))
            except Exception as exc:
                attempts.append(f"{first.exchange}: {exc}")

            combined, sources = self._combine(frames)
            covered = {
                column for column in DERIVATIVE_COVERAGE_FIELDS
                if combined[column].notna().any()
            }
            if covered == set(DERIVATIVE_COVERAGE_FIELDS):
                return combined, sources

        while True:
            batch = []
            for _ in range(DERIVATIVE_MAX_CONCURRENT_PROVIDERS):
                try:
                    batch.append(next(providers))
                except StopIteration:
                    break
            if not batch:
                break

            with ThreadPoolExecutor(max_workers=len(batch)) as executor:
                futures = {
                    executor.submit(
                        self._attempt_provider,
                        provider,
                        symbol=symbol,
                        limit=limit,
                        venue_symbols=venue_symbols,
                    ): provider
                    for provider in batch
                }
                for future, provider in futures.items():
                    try:
                        frame = future.result()
                        if not frame.empty:
                            frames.append((frame, provider.exchange))
                    except Exception as exc:
                        attempts.append(f"{provider.exchange}: {exc}")

            combined, sources = self._combine(frames)
            covered = {
                column for column in DERIVATIVE_COVERAGE_FIELDS
                if combined[column].notna().any()
            }
            if covered == set(DERIVATIVE_COVERAGE_FIELDS):
                return combined, sources

        combined, sources = self._combine(frames)
        if all(combined[column].notna().any() for column in DERIVATIVE_COVERAGE_FIELDS):
            return combined, sources
        missing = [
            name for name in DERIVATIVE_COVERAGE_FIELDS
            if combined.empty or not combined[name].notna().any()
        ]
        detail = "; ".join(attempts)
        if missing:
            detail = f"{detail}; missing: {','.join(missing)}".strip("; ")
        raise RuntimeError("all derivatives providers failed: " + detail)

class CcxtDerivativesProvider:
    """Capability-aware public derivatives provider backed by CCXT.

    CCXT is used only for venues whose public derivatives methods are actually
    supported by the exchange. Unsupported funding/OI history is not replaced
    with fabricated values; a provider attempt fails and the fallback chain
    continues to the next venue.
    """

    def __init__(
        self,
        exchange_id: str,
        *,
        timeout_seconds: float = 10.0,
        exchange_factory=None,
    ) -> None:
        import ccxt

        exchange_id = exchange_id.strip().lower()
        if not exchange_id:
            raise ValueError("exchange_id must not be empty")
        factory = exchange_factory or getattr(ccxt, exchange_id, None)
        # Some CCXT builds expose Gate under an alternate constructor name.
        # Keep the canonical provider ID as ``gateio`` while accepting that
        # constructor alias so the universal fallback is not rejected merely
        # by the installed CCXT package surface.
        if factory is None and exchange_id == "gateio":
            factory = getattr(ccxt, "gate", None)
        if factory is None:
            raise ValueError(f"unsupported CCXT exchange: {exchange_id}")
        self.exchange = exchange_id
        self.timeout_seconds = float(timeout_seconds)
        options = {"enableRateLimit": True}
        if exchange_id == "gateio":
            options["options"] = {
                "defaultType": "swap",
                "fetchCurrencies": False,
            }
        self._exchange = (
            factory(options)
            if callable(factory)
            else factory
        )
        self._exchange.timeout = int(self.timeout_seconds * 1000)

    def _load_markets(self) -> None:
        if not getattr(self._exchange, "markets", None):
            self._exchange.load_markets()

    def _resolve_symbol(self, symbol: str, native_symbol: str | None = None) -> str:
        self._load_markets()
        if native_symbol:
            return native_symbol
        candidates = [
            symbol,
            f"{symbol}:USDT" if ":" not in symbol and "/" in symbol else symbol,
        ]
        for candidate in candidates:
            if candidate in self._exchange.markets:
                return candidate
        base, _, quote = symbol.partition("/")
        base = base.upper()
        quote = quote.upper() or "USDT"
        for market_symbol, market in self._exchange.markets.items():
            if str(market.get("type", "")).lower() not in {"swap", "future"}:
                continue
            if str(market.get("quote", "")).upper() != quote:
                continue
            if str(market.get("settle", "")).upper() not in {"", quote}:
                continue
            if str(market.get("base", "")).upper() == base or str(market.get("baseId", "")).upper() == base:
                return market_symbol
        raise ValueError(f"{self.exchange} does not have market symbol {symbol}")

    @staticmethod
    def _number(value):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _funding_rows(self, symbol: str, limit: int) -> list[dict]:
        rows = []
        method = getattr(self._exchange, "fetch_funding_rate_history", None)
        if callable(method):
            try:
                history = method(symbol, None, min(int(limit), 200))
            except Exception:
                history = []
            for item in history or []:
                ts = item.get("timestamp") or item.get("fundingTimestamp")
                rate = item.get("fundingRate")
                ts = self._number(ts)
                rate = self._number(rate)
                if ts is not None and rate is not None:
                    rows.append({"timestamp": int(ts), "funding_rate": rate})
        if not rows:
            current_method = getattr(self._exchange, "fetch_funding_rate", None)
            if callable(current_method):
                try:
                    item = current_method(symbol)
                except Exception:
                    item = None
                if isinstance(item, dict):
                    ts = item.get("timestamp") or item.get("fundingTimestamp") or int(time.time() * 1000)
                    rate = item.get("fundingRate")
                    ts = self._number(ts)
                    rate = self._number(rate)
                    if ts is not None and rate is not None:
                        rows.append({"timestamp": int(ts), "funding_rate": rate})
        return rows

    def _oi_rows(self, symbol: str, limit: int) -> list[dict]:
        rows = []
        method = getattr(self._exchange, "fetch_open_interest_history", None)
        if callable(method):
            oi_symbol = symbol
            if self.exchange == "okx":
                oi_symbol = symbol.split("/", 1)[0]
            try:
                history = method(
                    oi_symbol,
                    "5m",
                    None,
                    min(int(limit), 200),
                )
            except Exception:
                history = []
            for item in history or []:
                ts = item.get("timestamp")
                value = item.get("openInterestValue")
                if value is None:
                    value = item.get("openInterestAmount")
                ts = self._number(ts)
                value = self._number(value)
                if ts is not None and value is not None:
                    rows.append({"timestamp": int(ts), "open_interest": value})
        if not rows:
            current_method = getattr(self._exchange, "fetch_open_interest", None)
            if callable(current_method):
                try:
                    item = current_method(symbol)
                except Exception:
                    item = None
                if isinstance(item, dict):
                    ts = item.get("timestamp") or int(time.time() * 1000)
                    value = item.get("openInterestValue")
                    if value is None:
                        value = item.get("openInterestAmount")
                    ts = self._number(ts)
                    value = self._number(value)
                    if ts is not None and value is not None:
                        rows.append({"timestamp": int(ts), "open_interest": value})
        return rows

    def fetch_derivatives(
        self,
        *,
        symbol: str,
        limit: int = 200,
        native_symbol: str | None = None,
    ) -> pd.DataFrame:
        self._load_markets()
        resolved_symbol = self._resolve_symbol(symbol, native_symbol=native_symbol)
        funding_rows = self._funding_rows(resolved_symbol, limit)
        oi_rows = self._oi_rows(resolved_symbol, limit)
        mark_row = None
        funding_method = getattr(self._exchange, "fetch_funding_rate", None)
        if callable(funding_method):
            try:
                current = funding_method(resolved_symbol)
            except Exception:
                current = {}
            mark = self._number(current.get("markPrice")) if isinstance(current, dict) else None
            ts = self._number(
                current.get("timestamp")
                or current.get("fundingTimestamp")
                or int(time.time() * 1000)
            )
            if mark is not None and ts is not None:
                mark_row = {"timestamp": int(ts), "mark_price": mark}

        if mark_row is None:
            ticker_method = getattr(self._exchange, "fetch_ticker", None)
            if callable(ticker_method):
                try:
                    ticker = ticker_method(resolved_symbol)
                except Exception:
                    ticker = None
                if isinstance(ticker, dict):
                    info = ticker.get("info")
                    mark = self._number(ticker.get("markPrice"))
                    if mark is None and isinstance(info, dict):
                        for key in ("markPrice", "markPx", "mark_price"):
                            mark = self._number(info.get(key))
                            if mark is not None:
                                break
                    ts = self._number(ticker.get("timestamp")) or int(time.time() * 1000)
                    if mark is not None:
                        mark_row = {"timestamp": int(ts), "mark_price": mark}

        return _merge_sources(
            funding_rows=funding_rows,
            oi_rows=oi_rows,
            mark_row=mark_row,
            liquidation_rows=[],
        )
