"""Probe real public market-data coverage for every configured market.

This diagnostic intentionally reports unsupported evidence sources as
UNSUPPORTED instead of inventing data. It checks all main-system OHLCV
timeframes plus trades, L1 order book, and short order-book history.
Derivative-specific sources are reported from the current provider contract.
"""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from pathlib import Path

from aicfa.public_market_data import build_public_market_data_provider

TIMEFRAMES = ("1w", "1d", "4h", "1h", "15m", "5m")
MARKET_TIMEOUT_SECONDS = 30.0
OHLCV_LIMIT = 10
TRADES_LIMIT = 10
ORDER_BOOK_LIMIT = 5
ORDER_BOOK_SNAPSHOTS = 2
ORDER_BOOK_INTERVAL_SECONDS = 0.2


def _call_with_timeout(fn, timeout: float):
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(fn)
    try:
        result = future.result(timeout=timeout)
    except TimeoutError:
        future.cancel()
        executor.shutdown(wait=False, cancel_futures=True)
        raise
    except Exception:
        executor.shutdown(wait=True)
        raise
    else:
        executor.shutdown(wait=True)
        return result


def _probe_market(provider, item: dict) -> tuple[bool, list[str]]:
    asset = str(item["asset"])
    market_type = str(item.get("market_type", "spot"))
    raw = item.get("venue_symbols", {})
    if isinstance(raw, dict):
        mappings = tuple((str(k), str(v)) for k, v in raw.items())
    else:
        mappings = tuple(
            (str(pair[0]), str(pair[1]))
            for pair in raw
            if isinstance(pair, (list, tuple)) and len(pair) == 2
        )

    if mappings:
        provider.register_market_symbols(asset, mappings, market_type=market_type)

    symbol = provider.resolve_symbol(asset, market_type=market_type)
    results: list[str] = [f"source={provider._resolved[(asset.upper(), market_type)].provider}", f"symbol={symbol}"]
    ok = True

    for timeframe in TIMEFRAMES:
        try:
            frame = provider.fetch_ohlcv(
                symbol=symbol,
                market_type=market_type,
                timeframe=timeframe,
                since_ms=None,
                limit=OHLCV_LIMIT,
            )
            results.append(f"ohlcv:{timeframe}=OK({len(frame)})")
        except Exception as exc:
            ok = False
            results.append(f"ohlcv:{timeframe}=FAIL({type(exc).__name__}: {exc})")

    try:
        frame = provider._by_symbol[(symbol.upper(), market_type)]
        resolved_provider = next(
            p for p in provider.providers
            if getattr(p, "exchange", p.__class__.__name__.lower()).lower()
            == frame.provider.lower()
        )
        trades = resolved_provider.fetch_trades(
            symbol=frame.symbol, market_type=market_type, limit=TRADES_LIMIT
        )
        results.append(f"trades=OK({len(trades)})")
    except Exception as exc:
        ok = False
        results.append(f"trades=FAIL({type(exc).__name__}: {exc})")

    try:
        book = resolved_provider.fetch_order_book(
            symbol=frame.symbol, market_type=market_type, limit=ORDER_BOOK_LIMIT
        )
        results.append(f"order_book=OK({len(book)})")
    except Exception as exc:
        ok = False
        results.append(f"order_book=FAIL({type(exc).__name__}: {exc})")

    try:
        history = resolved_provider.fetch_order_book_history(
            symbol=frame.symbol,
            market_type=market_type,
            snapshots=ORDER_BOOK_SNAPSHOTS,
            interval_seconds=ORDER_BOOK_INTERVAL_SECONDS,
        )
        results.append(f"order_book_history=OK({len(history)})")
    except Exception as exc:
        ok = False
        results.append(f"order_book_history=FAIL({type(exc).__name__}: {exc})")

    for source in ("funding", "open_interest", "liquidations", "mark_price"):
        results.append(f"{source}=UNSUPPORTED(provider-contract)")

    return ok, results


def main() -> None:
    markets = json.loads(Path("config/market_universe.json").read_text())["markets"]
    provider = build_public_market_data_provider(timeout_seconds=10.0)

    print(f"Configured markets: {len(markets)}", flush=True)
    print(
        "Providers: "
        + ", ".join(
            str(getattr(p, "exchange", p.__class__.__name__)).lower()
            for p in provider.providers
        ),
        flush=True,
    )
    print(
        "Checked: " + ", ".join(TIMEFRAMES)
        + " + trades + order_book + order_book_history",
        flush=True,
    )
    print(
        "Not silently fabricated: funding/open_interest/liquidations/mark_price "
        "are reported as UNSUPPORTED until provider contracts exist.",
        flush=True,
    )

    full = 0
    start_all = time.perf_counter()

    for index, item in enumerate(markets, start=1):
        asset = str(item["asset"])
        market_type = str(item.get("market_type", "spot"))
        start = time.perf_counter()
        try:
            ok, details = _call_with_timeout(
                lambda: _probe_market(provider, item),
                MARKET_TIMEOUT_SECONDS,
            )
            elapsed = time.perf_counter() - start
            if ok:
                full += 1
            status = "OK" if ok else "PARTIAL"
            print(
                f"[{index:03d}/{len(markets)}] {asset} [{market_type}] "
                f"{status} | {elapsed:.2f}s | " + " | ".join(details),
                flush=True,
            )
        except TimeoutError:
            elapsed = time.perf_counter() - start
            print(
                f"[{index:03d}/{len(markets)}] {asset} [{market_type}] "
                f"TIMEOUT | {elapsed:.2f}s",
                flush=True,
            )
        except Exception as exc:
            elapsed = time.perf_counter() - start
            print(
                f"[{index:03d}/{len(markets)}] {asset} [{market_type}] "
                f"FAIL | {elapsed:.2f}s | {type(exc).__name__}: {exc}",
                flush=True,
            )

    print(f"Markets with all currently supported sources OK: {full}/{len(markets)}", flush=True)
    print(f"Total elapsed: {time.perf_counter() - start_all:.2f}s", flush=True)


if __name__ == "__main__":
    main()
