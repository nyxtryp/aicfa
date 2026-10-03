"""Configurable market universe for autonomous AICFA monitoring.

The universe contains only user-selected assets/market types. It deliberately
does not contain trading logic, timeframes, or setup thresholds.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class MonitoredMarket:
    """One user-configured market to monitor."""

    asset: str
    market_type: str = "spot"

    def __post_init__(self) -> None:
        normalized_asset = self.asset.strip().upper().replace("-", "/").replace("_", "/")
        if not normalized_asset:
            raise ValueError("asset must not be empty")
        if "/" not in normalized_asset:
            raise ValueError("asset must contain a base/quote pair")
        base, quote = (part.strip() for part in normalized_asset.split("/", 1))
        if not base or not quote:
            raise ValueError("asset must contain non-empty base and quote")
        if self.market_type not in {"spot", "futures"}:
            raise ValueError("market_type must be spot or futures")
        object.__setattr__(self, "asset", f"{base}/{quote}")


@dataclass(frozen=True)
class MarketUniverse:
    """Immutable configured set of monitored markets."""

    markets: tuple[MonitoredMarket, ...]

    def __post_init__(self) -> None:
        if not self.markets:
            raise ValueError("market universe must not be empty")
        if len(set(self.markets)) != len(self.markets):
            raise ValueError("market universe contains duplicate markets")

    @classmethod
    def from_assets(
        cls,
        assets: Iterable[str],
        *,
        market_type: str = "spot",
    ) -> "MarketUniverse":
        markets = tuple(
            MonitoredMarket(asset=asset, market_type=market_type)
            for asset in assets
            if asset.strip()
        )
        return cls(markets)

    @property
    def assets(self) -> tuple[str, ...]:
        return tuple(market.asset for market in self.markets)

    @property
    def market_types(self) -> tuple[str, ...]:
        return tuple(market.market_type for market in self.markets)


def load_market_universe(path: str | Path) -> MarketUniverse:
    """Load a universe from JSON: {"markets": [{"asset": "BTC/USDT"}, ...]}."""
    config_path = Path(path)
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"market universe file not found: {config_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid market universe JSON: {config_path}") from exc

    if not isinstance(payload, dict) or not isinstance(payload.get("markets"), list):
        raise ValueError("market universe JSON must contain a 'markets' list")

    markets = []
    for item in payload["markets"]:
        if not isinstance(item, dict):
            raise ValueError("each market entry must be an object")
        if "asset" not in item:
            raise ValueError("each market entry must contain 'asset'")
        markets.append(
            MonitoredMarket(
                asset=str(item["asset"]),
                market_type=str(item.get("market_type", "spot")),
            )
        )
    return MarketUniverse(tuple(markets))
