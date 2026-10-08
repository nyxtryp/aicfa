"""Run one finite production rotation with per-market and seven-block diagnostics."""
from __future__ import annotations

import argparse
import time
from pathlib import Path

from aicfa.autonomous_scan import AutonomousScanEngine, RotationMarketMetric
from aicfa.market_universe import load_market_universe
from aicfa.public_market_data import build_public_market_data_provider


SEVEN_BLOCKS = (
    "ohlcv",
    "trades",
    "order_book",
    "funding",
    "open_interest",
    "liquidations",
    "mark_price",
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one finite AICFA production market rotation")
    parser.add_argument("--universe", default="config/market_universe.json")
    parser.add_argument("--market-timeout", type=float, default=60.0)
    args = parser.parse_args()

    universe = load_market_universe(Path(args.universe))
    provider = build_public_market_data_provider(timeout_seconds=10.0)
    engine = AutonomousScanEngine(
        universe,
        provider=provider,
        market_timeout_seconds=args.market_timeout,
    )

    print(
        f"ROTATION START markets={len(universe.markets)} "
        f"timeout={args.market_timeout:.1f}s",
        flush=True,
    )

    coverage: dict[str, dict[str, int]] = {block: {} for block in SEVEN_BLOCKS}

    def record_block(block: str, status: str) -> None:
        bucket = coverage[block]
        bucket[status] = bucket.get(status, 0) + 1

    def on_market(metric: RotationMarketMetric) -> None:
        scan = engine.last_state.result.markets[0] if engine.last_state is not None else None
        diagnostics = scan.diagnostics if scan is not None else None
        refetch = diagnostics is not None and diagnostics.refetched_between_horizons
        marker = " REFETCH" if refetch else ""
        print(
            f"[{metric.queue_position:03d}/{len(universe.markets):03d}] "
            f"{metric.asset} {metric.status.upper()} "
            f"{metric.duration_ms / 1000.0:.3f}s setups={metric.setup_count}{marker}",
            flush=True,
        )
        if diagnostics is None:
            return

        ohlcv_statuses = [str(item.status).strip().lower() for item in diagnostics.snapshot_metrics]
        if ohlcv_statuses:
            record_block("ohlcv", "complete" if all(s in {"complete", "cached"} for s in ohlcv_statuses) else "partial")

        seen: set[str] = set()
        for item in diagnostics.block_timings:
            block = str(getattr(item, "block", "")).strip().lower()
            if block not in SEVEN_BLOCKS[1:] or block in seen:
                continue
            seen.add(block)
            record_block(block, str(item.status).strip().lower())

    started = time.perf_counter()
    cycle = engine.run_cycle(on_market=on_market)
    elapsed = time.perf_counter() - started

    durations = sorted(cycle.markets, key=lambda item: item.duration_ms, reverse=True)
    avg = sum(item.duration_ms for item in cycle.markets) / len(cycle.markets)
    print(
        f"ROTATION END cycle={cycle.cycle_id} markets={cycle.market_count} "
        f"completed={cycle.completed_markets} timeout={cycle.timeout_markets} "
        f"error={cycle.error_markets} setups={cycle.setup_count} "
        f"total={cycle.total_duration_ms / 1000.0:.3f}s wall={elapsed:.3f}s "
        f"avg={avg / 1000.0:.3f}s max={durations[0].asset}:{durations[0].duration_ms / 1000.0:.3f}s",
        flush=True,
    )
    print("DATA COVERAGE", flush=True)
    for block in SEVEN_BLOCKS:
        bucket = coverage[block]
        covered = sum(count for status, count in bucket.items() if status not in {"unavailable", "error"})
        details = ", ".join(f"{status}={count}" for status, count in sorted(bucket.items())) or "no diagnostics"
        print(f"  {block.upper():14s} covered={covered:03d}/{len(universe.markets):03d} {details}", flush=True)
    print("SLOWEST 10", flush=True)
    for item in durations[:10]:
        print(
            f"  {item.asset} {item.status} {item.duration_ms / 1000.0:.3f}s setups={item.setup_count}",
            flush=True,
        )


if __name__ == "__main__":
    main()
