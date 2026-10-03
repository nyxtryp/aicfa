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
    """One user-configured market to monitor.

    asset is AICFA's canonical identifier. TradFi entries may additionally
    carry an asset class/category, instrument type, and verified venue-native
    symbols. Crypto entries remain backward-compatible with only asset and
    market_type.
    """

    asset: str
    market_type: str = "spot"
    asset_class: str = "crypto"
    category: str = "crypto"
    instrument_type: str | None = None
    venue_symbols: tuple[tuple[str, str], ...] = ()

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
        asset_class = self.asset_class.strip().lower()
        if asset_class not in {"crypto", "tradfi"}:
            raise ValueError("asset_class must be crypto or tradfi")
        category = self.category.strip().lower()
        if not category:
            raise ValueError("category must not be empty")
        if self.instrument_type is not None and not self.instrument_type.strip():
            raise ValueError("instrument_type must not be empty when provided")

        normalized_venues: list[tuple[str, str]] = []
        seen_venues: set[str] = set()
        for venue, symbol in self.venue_symbols:
            venue_name = str(venue).strip().lower()
            native_symbol = str(symbol).strip()
            if not venue_name or not native_symbol:
                raise ValueError("venue_symbols must contain non-empty venue/symbol pairs")
            if venue_name in seen_venues:
                raise ValueError("venue_symbols contains duplicate venues")
            seen_venues.add(venue_name)
            normalized_venues.append((venue_name, native_symbol))

        object.__setattr__(self, "asset", f"{base}/{quote}")
        object.__setattr__(self, "asset_class", asset_class)
        object.__setattr__(self, "category", category)
        object.__setattr__(self, "instrument_type", (
            self.instrument_type.strip().lower()
            if self.instrument_type is not None else None
        ))
        object.__setattr__(self, "venue_symbols", tuple(normalized_venues))


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
                asset_class=str(item.get("asset_class", "crypto")),
                category=str(item.get("category", "crypto")),
                instrument_type=(
                    str(item["instrument_type"])
                    if item.get("instrument_type") is not None else None
                ),
                venue_symbols=tuple(
                    (str(venue), str(symbol))
                    for venue, symbol in dict(item.get("venue_symbols", {})).items()
                ),
            )
        )
    return MarketUniverse(tuple(markets))
