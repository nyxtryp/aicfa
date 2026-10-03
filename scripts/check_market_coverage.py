"""Check configured market coverage across the production public source chain."""
from __future__ import annotations

import json
import time
from pathlib import Path

from aicfa.public_market_data import build_public_market_data_provider


def main() -> None:
    path = Path("config/market_universe.json")
    payload = json.loads(path.read_text())
    assets = [item["asset"] for item in payload["markets"]]
    provider = build_public_market_data_provider(timeout_seconds=10.0)

    print(f"Configured markets: {len(assets)}", flush=True)
    print(
        "Providers:",
        ", ".join(getattr(p, "exchange", p.__class__.__name__) for p in provider.providers),
        flush=True,
    )

    covered = 0
    timings: list[float] = []
    total_start = time.perf_counter()

    for index, asset in enumerate(assets, start=1):
        start = time.perf_counter()
        try:
            symbol = provider.resolve_symbol(asset, market_type="spot")
            elapsed = time.perf_counter() - start
            timings.append(elapsed)
            resolved = provider._resolved[(asset.upper(), "spot")]
            print(
                f"[{index:03d}/{len(assets)}] {asset} -> "
                f"{resolved.provider} ({symbol}) | {elapsed:.3f}s",
                flush=True,
            )
            covered += 1
        except Exception as exc:
            elapsed = time.perf_counter() - start
            timings.append(elapsed)
            print(
                f"[{index:03d}/{len(assets)}] {asset} -> MISSING | "
                f"{elapsed:.3f}s | {exc}",
                flush=True,
            )

    total_elapsed = time.perf_counter() - total_start
    average = sum(timings) / len(timings) if timings else 0.0
    minimum = min(timings, default=0.0)
    maximum = max(timings, default=0.0)

    print(f"Coverage: {covered}/{len(assets)}", flush=True)
    print(f"Missing: {len(assets) - covered}", flush=True)
    print(
        f"Timing: total={total_elapsed:.3f}s | "
        f"avg={average:.3f}s | min={minimum:.3f}s | max={maximum:.3f}s",
        flush=True,
    )


if __name__ == "__main__":
    main()
