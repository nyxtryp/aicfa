"""Check configured market coverage across the production public source chain."""
from __future__ import annotations

import json
from pathlib import Path

from aicfa.public_market_data import build_public_market_data_provider

def main() -> None:
    path = Path("config/market_universe.json")
    payload = json.loads(path.read_text())
    assets = [item["asset"] for item in payload["markets"]]
    provider = build_public_market_data_provider(timeout_seconds=10.0)
    print(f"Configured markets: {len(assets)}")
    print("Providers:", ", ".join(getattr(p, "exchange", p.__class__.__name__) for p in provider.providers))
    covered = 0
    for asset in assets:
        try:
            symbol = provider.resolve_symbol(asset, market_type="spot")
            resolved = provider._resolved[(asset.upper(), "spot")]
            print(f"{asset} -> {resolved.provider} ({symbol})")
            covered += 1
        except Exception as exc:
            print(f"{asset} -> MISSING | {exc}")
    print(f"Coverage: {covered}/{len(assets)}")
    print(f"Missing: {len(assets) - covered}")

if __name__ == "__main__":
    main()
