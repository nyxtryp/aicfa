"""Profile the shared OHLCV feature-engine pass for one configured market.

Measurement-only tooling. It does not change trading logic or production behavior.
"""
from __future__ import annotations

import argparse
import cProfile
import pstats
import time
from pathlib import Path

from aicfa.features import build_features
from aicfa.market_orchestrator import _acquire_primary_snapshot, _primary_snapshot_limits
from aicfa.market_universe import load_market_universe
from aicfa.public_market_data import build_public_market_data_provider
from aicfa.market_data import completed_ohlcv


def _market(universe, requested: str):
    wanted = requested.strip().upper()
    for market in universe.markets:
        if market.asset.upper() == wanted or market.asset.split("/", 1)[0].upper() == wanted:
            return market
    raise SystemExit(f"unknown configured asset: {requested}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Profile AICFA build_features across the shared primary MTF snapshot")
    parser.add_argument("--assets", nargs="+", required=True)
    parser.add_argument("--universe", default="config/market_universe.json")
    parser.add_argument("--top", type=int, default=30)
    args = parser.parse_args()

    universe = load_market_universe(Path(args.universe))
    provider = build_public_market_data_provider(timeout_seconds=10.0)
    modes = _primary_snapshot_limits(("intraday", "swing", "position"))

    for requested in args.assets:
        market = _market(universe, requested)
        register = getattr(provider, "register_market_symbols", None)
        if register is not None and market.venue_symbols:
            register(market.asset, market.venue_symbols, market_type=market.market_type)

        now_ms = int(time.time() * 1000)
        started = time.perf_counter()
        _, _, frames = _acquire_primary_snapshot(
            provider,
            asset=market.asset,
            market_type=market.market_type,
            modes=modes,
            resolver=None,
        )
        snapshot_elapsed = time.perf_counter() - started

        completed = {}
        for timeframe, frame in frames.items():
            item = completed_ohlcv(frame, timeframe=timeframe, now_ms=now_ms)
            if not item.empty:
                completed[timeframe] = item

        print(f"MARKET {market.asset} snapshot={snapshot_elapsed:.3f}s frames={len(completed)}", flush=True)

        def run_features():
            for timeframe in ("1w", "1d", "4h", "1h", "15m", "5m"):
                frame = completed.get(timeframe)
                if frame is not None:
                    build_features(frame)

        profiler = cProfile.Profile()
        started = time.perf_counter()
        profiler.enable()
        run_features()
        profiler.disable()
        elapsed = time.perf_counter() - started

        print(f"FEATURES total={elapsed:.3f}s", flush=True)
        stats = pstats.Stats(profiler).strip_dirs().sort_stats("cumulative")
        stats.print_stats(args.top)


if __name__ == "__main__":
    main()
