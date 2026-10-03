"""Autonomous primary-horizon orchestration over the existing AICFA setup engine.

This layer does not implement a second scanner or trading logic. It runs the
existing deterministic FindSetup pipeline for the three primary horizons and
preserves independent setup candidates across horizons and markets.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Sequence

from .data_requirements import TradingMode
from .find_setup import FindSetupRequest, FindSetupResult, find_setup


PRIMARY_TRADING_MODES: tuple[TradingMode, ...] = (
    TradingMode.INTRADAY,
    TradingMode.SWING,
    TradingMode.POSITION,
)


@dataclass(frozen=True)
class HorizonSetup:
    """One setup candidate with the horizon that produced it."""

    mode: TradingMode
    candidate: object


@dataclass(frozen=True)
class MarketHorizonScan:
    """All primary-horizon results for one resolved market."""

    asset: str
    results: tuple[FindSetupResult, ...]
    setups: tuple[HorizonSetup, ...]


@dataclass(frozen=True)
class MultiMarketScan:
    """Independent autonomous scan results for the configured market universe."""

    markets: tuple[MarketHorizonScan, ...]

    @property
    def setups(self) -> tuple[tuple[str, HorizonSetup], ...]:
        return tuple(
            (market.asset, setup)
            for market in self.markets
            for setup in market.setups
        )


def analyze_market_horizons(
    asset: str,
    *,
    provider: object | None = None,
    now_ms: int,
    market_type: str = "spot",
    resolver: Callable[[str, str], str] | None = None,
    modes: Sequence[TradingMode] = PRIMARY_TRADING_MODES,
) -> MarketHorizonScan:
    """Run the existing FindSetup pipeline once per primary horizon.

    No horizon is forced to produce a signal. Only candidates emitted by the
    existing decision/setup pipeline are preserved.
    """
    normalized_modes = tuple(modes)
    if not normalized_modes:
        raise ValueError("at least one trading mode is required")
    if any(mode is TradingMode.SCALPING for mode in normalized_modes):
        raise ValueError("scalping is isolated from the primary horizon scan")

    results: list[FindSetupResult] = []
    setups: list[HorizonSetup] = []
    for mode in normalized_modes:
        result = find_setup(
            FindSetupRequest(asset=asset, market_type=market_type, mode=mode),
            provider=provider,
            now_ms=now_ms,
            resolver=resolver,
        )
        results.append(result)
        candidates = getattr(result.setup_assessment, "candidates", ())
        for candidate in candidates:
            setups.append(HorizonSetup(mode=mode, candidate=candidate))

    resolved_asset = results[0].symbol
    return MarketHorizonScan(
        asset=resolved_asset,
        results=tuple(results),
        setups=tuple(setups),
    )


def scan_markets(
    assets: Sequence[str],
    *,
    provider: object | None = None,
    now_ms: int,
    market_type: str = "spot",
    resolver: Callable[[str, str], str] | None = None,
    modes: Sequence[TradingMode] = PRIMARY_TRADING_MODES,
) -> MultiMarketScan:
    """Scan each configured market independently across the primary horizons."""
    normalized_assets = tuple(asset.strip() for asset in assets if asset.strip())
    if not normalized_assets:
        raise ValueError("at least one market asset is required")

    markets = tuple(
        analyze_market_horizons(
            asset,
            provider=provider,
            now_ms=now_ms,
            market_type=market_type,
            resolver=resolver,
            modes=modes,
        )
        for asset in normalized_assets
    )
    return MultiMarketScan(markets=markets)
