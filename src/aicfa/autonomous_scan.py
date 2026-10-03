"""Stateful recurring autonomous scan loop for the configured AICFA market universe.

This layer owns the long-lived lifecycle state and repeatedly invokes the
existing deterministic market orchestrator. It does not add signal logic,
thresholds, setup limits, or a second scanner.
"""
from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Callable, Sequence

from .data_requirements import TradingMode
from .market_orchestrator import (
    PRIMARY_TRADING_MODES,
    MarketHorizonScan,
    MultiMarketScan,
    scan_universe,
)
from .market_universe import MarketUniverse
from .setup_lifecycle import ActiveSetup, SetupLifecycle


MAIN_SCAN_INTERVAL_SECONDS = 300
BATCH_SCAN_INTERVAL_SECONDS = 0
DEFAULT_MARKETS_PER_BATCH = 1


@dataclass(frozen=True)
class AutonomousScanState:
    """Latest autonomous scan snapshot."""

    scan_number: int
    scanned_at_ms: int
    result: MultiMarketScan


class AutonomousScanEngine:
    """Continuously scan one configured universe with persistent in-process state.

    The same SetupLifecycle instance is reused across scans, so an identical
    setup keeps its identity while independent geometries remain independent.
    The configured MarketUniverse is the only source of monitored markets.
    """

    def __init__(
        self,
        universe: MarketUniverse,
        *,
        provider: object | None = None,
        resolver: Callable[[str, str], str] | None = None,
        modes: Sequence[TradingMode] = PRIMARY_TRADING_MODES,
        clock_ms: Callable[[], int] | None = None,
    ) -> None:
        self.universe = universe
        self.provider = provider
        self.resolver = resolver
        self.modes = tuple(modes)
        self.lifecycle = SetupLifecycle()
        self._clock_ms = clock_ms or (lambda: int(time.time() * 1000))
        self._scan_number = 0
        self._last_state: AutonomousScanState | None = None

    @property
    def last_state(self) -> AutonomousScanState | None:
        return self._last_state

    @property
    def scan_number(self) -> int:
        return self._scan_number

    def active_setups(
        self,
        *,
        symbol: str | None = None,
        market_type: str | None = None,
        horizon: TradingMode | str | None = None,
    ) -> tuple[ActiveSetup, ...]:
        """Return all currently active independent setup lifecycles."""
        return self.lifecycle.active_setups(
            symbol=symbol,
            market_type=market_type,
            horizon=horizon,
        )


    def _market_batch(self, batch_index: int, batch_size: int) -> MarketUniverse:
        if batch_size <= 0:
            raise ValueError("batch_size must be greater than zero")
        markets = self.universe.markets
        if not markets:
            raise ValueError("market universe must not be empty")
        batch_count = (len(markets) + batch_size - 1) // batch_size
        if batch_index < 0 or batch_index >= batch_count:
            raise ValueError(f"batch_index must be between 0 and {batch_count - 1}")
        start = batch_index * batch_size
        return MarketUniverse(markets[start : start + batch_size])

    def scan_batch(
        self,
        batch_index: int,
        *,
        batch_size: int = DEFAULT_MARKETS_PER_BATCH,
        now_ms: int | None = None,
    ) -> AutonomousScanState:
        """Run one configured market batch, preserving lifecycle across batches."""
        timestamp = self._clock_ms() if now_ms is None else now_ms
        batch = self._market_batch(batch_index, batch_size)
        result = scan_universe(
            batch,
            provider=self.provider,
            now_ms=timestamp,
            resolver=self.resolver,
            modes=self.modes,
            lifecycle=self.lifecycle,
        )
        self._scan_number += 1
        state = AutonomousScanState(
            scan_number=self._scan_number,
            scanned_at_ms=timestamp,
            result=result,
        )
        self._last_state = state
        return state

    def scan_once(self, *, now_ms: int | None = None) -> AutonomousScanState:
        """Run exactly one autonomous scan over the configured universe."""
        timestamp = self._clock_ms() if now_ms is None else now_ms
        result = scan_universe(
            self.universe,
            provider=self.provider,
            now_ms=timestamp,
            resolver=self.resolver,
            modes=self.modes,
            lifecycle=self.lifecycle,
        )
        self._scan_number += 1
        state = AutonomousScanState(
            scan_number=self._scan_number,
            scanned_at_ms=timestamp,
            result=result,
        )
        self._last_state = state
        return state


    def scan_market(self, market_index: int, *, now_ms: int | None = None) -> AutonomousScanState:
        """Run exactly one configured market and preserve lifecycle state."""
        if market_index < 0 or market_index >= len(self.universe.markets):
            raise ValueError(f"market_index must be between 0 and {len(self.universe.markets) - 1}")
        timestamp = self._clock_ms() if now_ms is None else now_ms
        market = MarketUniverse((self.universe.markets[market_index],))
        result = scan_universe(
            market, provider=self.provider, now_ms=timestamp, resolver=self.resolver,
            modes=self.modes, lifecycle=self.lifecycle,
        )
        self._scan_number += 1
        state = AutonomousScanState(scan_number=self._scan_number, scanned_at_ms=timestamp, result=result)
        self._last_state = state
        return state

    def run_forever_batches(
        self, *, interval_seconds: float = BATCH_SCAN_INTERVAL_SECONDS,
        batch_size: int = DEFAULT_MARKETS_PER_BATCH,
        on_scan: Callable[[AutonomousScanState], None] | None = None,
        should_stop: Callable[[], bool] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Continuously scan one market after another in configured order."""
        if interval_seconds < 0:
            raise ValueError("interval_seconds must be non-negative")
        if batch_size != 1:
            raise ValueError("batch_size must be 1; autonomous scanning is sequential")
        if not self.universe.markets:
            raise ValueError("market universe must not be empty")
        market_index = 0
        while True:
            if should_stop is not None and should_stop():
                return
            state = self.scan_market(market_index)
            if on_scan is not None:
                on_scan(state)
            if should_stop is not None and should_stop():
                return
            market_index = (market_index + 1) % len(self.universe.markets)
            if interval_seconds:
                sleep(interval_seconds)
    def run_forever(
        self,
        *,
        interval_seconds: float,
        on_scan: Callable[[AutonomousScanState], None] | None = None,
        should_stop: Callable[[], bool] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Run recurring scans until the supplied stop predicate becomes true."""
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be greater than zero")

        while True:
            if should_stop is not None and should_stop():
                return
            state = self.scan_once()
            if on_scan is not None:
                on_scan(state)
            if should_stop is not None and should_stop():
                return
            sleep(interval_seconds)


__all__ = ["AutonomousScanEngine", "AutonomousScanState", "BATCH_SCAN_INTERVAL_SECONDS", "DEFAULT_MARKETS_PER_BATCH", "MAIN_SCAN_INTERVAL_SECONDS"]
