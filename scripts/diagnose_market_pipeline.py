"""Run one configured market through the full primary AICFA pipeline.

This is measurement tooling only. It does not add scanner or trading logic.
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

from aicfa.market_orchestrator import analyze_market_horizons
from aicfa.market_universe import load_market_universe
from aicfa.public_market_data import build_public_market_data_provider


def _market(universe, requested: str):
    wanted = requested.strip().upper()
    for market in universe.markets:
        if market.asset.upper() == wanted or market.asset.split("/", 1)[0].upper() == wanted:
            return market
    raise SystemExit(f"unknown configured asset: {requested}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnose one full AICFA market pipeline")
    parser.add_argument("--assets", nargs="+", required=True, help="Configured asset/base symbol")
    parser.add_argument("--universe", default="config/market_universe.json")
    args = parser.parse_args()

    universe = load_market_universe(Path(args.universe))
    provider = build_public_market_data_provider(timeout_seconds=10.0)

    for requested in args.assets:
        market = _market(universe, requested)
        register = getattr(provider, "register_market_symbols", None)
        if register is not None and market.venue_symbols:
            register(market.asset, market.venue_symbols, market_type=market.market_type)

        started = time.perf_counter()
        try:
            scan = analyze_market_horizons(
                market.asset,
                provider=provider,
                now_ms=int(time.time() * 1000),
                market_type=market.market_type,
            )
            diagnostics = scan.diagnostics
            if diagnostics is None:
                raise RuntimeError("pipeline returned no diagnostics")

            print(
                f"MARKET {market.asset} [{market.market_type}] "
                f"status={diagnostics.status} total={diagnostics.total_duration_ms / 1000:.3f}s "
                f"resolution={diagnostics.resolution_duration_ms / 1000:.3f}s "
                f"snapshot={diagnostics.snapshot_duration_ms / 1000:.3f}s "
                f"refetch={diagnostics.refetched_between_horizons} "
                f"setups={len(scan.setups)} lifecycle={diagnostics.lifecycle_event_count}",
                flush=True,
            )

            print("  OHLCV", flush=True)
            for item in diagnostics.snapshot_metrics:
                print(
                    f"    {item.timeframe}: {item.status} rows={item.rows} "
                    f"time={item.duration_ms / 1000:.3f}s",
                    flush=True,
                )

            print("  HORIZONS", flush=True)
            for item in diagnostics.horizon_timings:
                print(
                    f"    {item.mode.value}: {item.duration_ms / 1000:.3f}s "
                    f"setups={item.setup_count} decision={item.decision}",
                    flush=True,
                )

            print(
                f"  PIPELINE features={diagnostics.feature_duration_ms / 1000:.3f}s "
                f"evidence={diagnostics.evidence_duration_ms / 1000:.3f}s "
                f"setup={diagnostics.setup_duration_ms / 1000:.3f}s",
                flush=True,
            )
            print("  BLOCKS", flush=True)
            for item in diagnostics.block_timings:
                provider_name = f" provider={item.provider}" if item.provider else ""
                reason = f" reason={item.reason}" if item.reason else ""
                print(
                    f"    {item.block}: {item.status} rows={item.rows} "
                    f"time={item.duration_ms / 1000:.3f}s{provider_name}{reason}",
                    flush=True,
                )

            print(
                f"  WALL_CLOCK {time.perf_counter() - started:.3f}s",
                flush=True,
            )
        except Exception as exc:
            elapsed = time.perf_counter() - started
            print(
                f"MARKET {market.asset} [{market.market_type}] "
                f"status=error total={elapsed:.3f}s "
                f"error={type(exc).__name__}: {exc}",
                flush=True,
            )


if __name__ == "__main__":
    main()
