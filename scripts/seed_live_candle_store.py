#!/usr/bin/env python3
"""Seed AICFA's actual persistent live candle cache for every configured market.

Writes the same AICFA_DATA_DIR/raw/<symbol>/<timeframe>.csv files consumed by
LiveMarketDataCache and restored by the production websocket coordinator.
"""
from __future__ import annotations

import argparse
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import time

from aicfa.live_market import PersistentCandleStore, WINDOWS
from aicfa.market_data import MarketKey, timeframe_ms, validate_ohlcv
from aicfa.market_universe import load_market_universe
from aicfa.public_market_data import build_public_market_data_provider


def _closed_window(frame, timeframe: str, *, now_ms: int, limit: int):
    if frame is None or frame.empty:
        return frame
    normalized = validate_ohlcv(frame)
    closed = normalized.loc[
        normalized["timestamp"] + timeframe_ms(timeframe) <= int(now_ms)
    ]
    return closed.tail(limit).reset_index(drop=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--timeframes", nargs="*", default=list(WINDOWS))
    parser.add_argument("--assets", nargs="*", help="Optional configured asset filter")
    args = parser.parse_args()
    if args.workers < 1:
        parser.error("--workers must be positive")
    unknown = set(args.timeframes) - set(WINDOWS)
    if unknown:
        parser.error(f"unsupported timeframes: {', '.join(sorted(unknown))}")

    root = Path(os.environ.get("AICFA_DATA_DIR", "data"))
    store = PersistentCandleStore(root / "raw")
    provider = build_public_market_data_provider(timeout_seconds=10.0)
    universe = load_market_universe(Path("config/market_universe.json"))
    requested = {asset.upper() for asset in args.assets or []}
    markets = [
        market for market in universe.markets
        if market.asset_class == "crypto" and (not requested or market.asset.upper() in requested)
    ]
    if not markets:
        raise SystemExit("No configured markets matched --assets")

    tasks = []
    failures: list[str] = []
    for market in markets:
        try:
            provider.register_market_symbols(
                market.asset, market.venue_symbols, market_type=market.market_type
            )
            symbol = provider.resolve_symbol(market.asset, market_type=market.market_type)
            for timeframe in args.timeframes:
                tasks.append((market.asset, market.market_type, symbol, timeframe))
        except Exception as exc:
            failures.append(f"{market.asset}:resolve:{type(exc).__name__}:{exc}")

    def seed_one(task):
        asset, market_type, symbol, timeframe = task
        window = WINDOWS[timeframe]
        key = MarketKey("binance", symbol, market_type, timeframe)
        # Ask for one extra row so removing the currently-forming candle still
        # leaves the requested closed-candle count whenever the venue has it.
        frame = provider.fetch_ohlcv(
            symbol=symbol,
            market_type=market_type,
            timeframe=timeframe,
            since_ms=None,
            limit=window + 1,
        )
        closed = _closed_window(frame, timeframe, now_ms=int(time.time() * 1000), limit=window)
        if closed is None or closed.empty:
            raise RuntimeError("provider returned no closed OHLCV candles")
        stored = store.replace(key, closed)
        return asset, timeframe, len(stored), int(stored["timestamp"].iloc[-1])

    total = len(tasks)
    succeeded = 0
    with ThreadPoolExecutor(max_workers=args.workers, thread_name_prefix="aicfa-seed") as pool:
        futures = {pool.submit(seed_one, task): task for task in tasks}
        for future in as_completed(futures):
            task = futures[future]
            try:
                asset, timeframe, count, latest = future.result()
                succeeded += 1
                print(f"OK {asset} {timeframe}: {count}/{WINDOWS[timeframe]} closed candles latest={latest}", flush=True)
            except Exception as exc:
                failures.append(f"{task[0]} {task[3]}: {type(exc).__name__}: {exc}")
                print(f"FAIL {task[0]} {task[3]}: {type(exc).__name__}: {exc}", flush=True)

    print(f"SEED SUMMARY: markets={len(markets)} timeframes={len(args.timeframes)} success={succeeded}/{total} failures={len(failures)}", flush=True)
    if failures:
        print("FAILURE DETAILS:", flush=True)
        for failure in failures[:100]:
            print(f" - {failure}", flush=True)
    return 0 if not failures and succeeded == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
