"""Check configured market coverage across the production public source chain."""
from __future__ import annotations

import json
import time
from pathlib import Path

from aicfa.public_market_data import build_public_market_data_provider


def main() -> None:
    path = Path("config/market_universe.json")
    payload = json.loads(path.read_text())
    markets = payload["markets"]
    provider = build_public_market_data_provider(timeout_seconds=10.0)

    print(f"Configured markets: {len(markets)}", flush=True)
    print(
        "Providers:",
        ", ".join(getattr(p, "exchange", p.__class__.__name__) for p in provider.providers),
        flush=True,
    )

    covered = 0
    timings: list[float] = []
    total_start = time.perf_counter()

    for index, item in enumerate(markets, start=1):
        asset = item["asset"]
        market_type = item.get("market_type", "spot")
        venue_symbols = tuple(
            (str(pair[0]), str(pair[1]))
            for pair in item.get("venue_symbols", [])
            if isinstance(pair, (list, tuple)) and len(pair) == 2
        )

        if venue_symbols:
            provider.register_market_symbols(
                asset,
                venue_symbols,
                market_type=market_type,
            )

        start = time.perf_counter()
        try:
            symbol = provider.resolve_symbol(asset, market_type=market_type)
            elapsed = time.perf_counter() - start
            timings.append(elapsed)
            resolved = provider._resolved[(asset.upper(), market_type)]
            print(
                f"[{index:03d}/{len(markets)}] {asset} [{market_type}] -> "
                f"{resolved.provider} ({symbol}) | {elapsed:.3f}s",
                flush=True,
            )
            covered += 1
        except Exception as exc:
            elapsed = time.perf_counter() - start
            timings.append(elapsed)
            print(
                f"[{index:03d}/{len(markets)}] {asset} [{market_type}] -> MISSING | "
                f"{elapsed:.3f}s | {exc}",
                flush=True,
            )

    total_elapsed = time.perf_counter() - total_start
    average = sum(timings) / len(timings) if timings else 0.0
    minimum = min(timings, default=0.0)
    maximum = max(timings, default=0.0)

    print(f"Coverage: {covered}/{len(markets)}", flush=True)
    print(f"Missing: {len(markets) - covered}", flush=True)
    print(
        f"Timing: total={total_elapsed:.3f}s | "
        f"avg={average:.3f}s | min={minimum:.3f}s | max={maximum:.3f}s",
        flush=True,
    )


if __name__ == "__main__":
    main()
