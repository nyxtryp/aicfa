"""Stateful recurring autonomous scan loop for the configured AICFA market universe.

This layer owns the long-lived lifecycle state and repeatedly invokes the
existing deterministic market orchestrator. It does not add signal logic,
thresholds, setup limits, or a second scanner.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import signal
import threading
import time
from typing import Callable, Sequence

from .data_requirements import TradingMode
from .public_market_data import build_public_market_data_provider
from .market_orchestrator import (
    PRIMARY_TRADING_MODES,
    MarketHorizonScan,
    MarketScanDiagnostics,
    MultiMarketScan,
    scan_universe,
)
from .market_universe import MarketUniverse
from .setup_analysis import SetupAssessment, SetupDecision
from .setup_lifecycle import ActiveSetup, SetupLifecycle
from .persistent_journal import PersistentJournal
from .setup_registry import SetupRegistry


MAIN_SCAN_INTERVAL_SECONDS = 30
BATCH_SCAN_INTERVAL_SECONDS = 0
DEFAULT_MARKETS_PER_BATCH = 1
# The automatic rotation runs on the process main thread so SIGALRM can enforce
# a real per-market hard deadline. Keep the budget below the 30-second cadence.
DEFAULT_MARKET_TIMEOUT_SECONDS = 25.0
MANUAL_SCAN_PAUSE_SECONDS = 30.0


class MarketExecutionTimeout(TimeoutError):
    """Raised when one market exceeds its whole-market execution budget."""


@contextmanager
def _noop_context():
    yield

@contextmanager
def _market_timeout(seconds: float):
    if seconds <= 0:
        yield
        return
    # SIGALRM is process-wide and Python only permits installing signal
    # handlers from the main thread. The production autonomous worker runs in
    # its own thread, so use provider-level/network timeouts there instead
    # of turning every market into a false scanner error.
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    previous = signal.getsignal(signal.SIGALRM)
    def _handler(_signum, _frame):
        raise MarketExecutionTimeout(f"market exceeded hard execution budget of {seconds:.1f}s")
    signal.signal(signal.SIGALRM, _handler)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0.0)
        signal.signal(signal.SIGALRM, previous)


@dataclass(frozen=True)
class AutonomousScanState:
    """Latest autonomous scan snapshot with live rotation position."""

    scan_number: int
    scanned_at_ms: int
    result: MultiMarketScan
    rotation_id: int = 0
    queue_position: int = 0
    universe_size: int = 0


@dataclass(frozen=True)
class RotationMarketMetric:
    """Measured outcome for one deterministic queue position."""

    cycle_id: int
    queue_position: int
    asset: str
    status: str
    duration_ms: float
    setup_count: int
    error: str = ""


@dataclass(frozen=True)
class RotationCycle:
    """One finite pass over every configured market in deterministic order."""

    cycle_id: int
    started_at_ms: int
    finished_at_ms: int
    total_duration_ms: float
    market_count: int
    completed_markets: int
    timeout_markets: int
    error_markets: int
    setup_count: int
    markets: tuple[RotationMarketMetric, ...]


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
        modes: Sequence[TradingMode] = (
            TradingMode.SCALPING,
            TradingMode.INTRADAY,
            TradingMode.SWING,
            TradingMode.POSITION,
        ),
        clock_ms: Callable[[], int] | None = None,
        market_timeout_seconds: float = DEFAULT_MARKET_TIMEOUT_SECONDS,
        journal: PersistentJournal | None = None,
    ) -> None:
        self.universe = universe
        self.provider = provider or build_public_market_data_provider(timeout_seconds=10.0)
        self.resolver = resolver
        if market_timeout_seconds <= 0:
            raise ValueError("market_timeout_seconds must be greater than zero")
        self.market_timeout_seconds = float(market_timeout_seconds)
        self.journal = journal if journal is not None else PersistentJournal.from_env()
        self.registry = SetupRegistry.from_env()
        self.modes = tuple(modes)
        self.lifecycle = SetupLifecycle()
        if self.registry is not None:
            try:
                restored = self.lifecycle.restore_from_registry(self.registry.read())
                if restored:
                    print(f"AICFA restored {restored} active setup lifecycle(s).", flush=True)
            except Exception as exc:
                print(f"AICFA lifecycle restore error: {type(exc).__name__}: {exc}", flush=True)
        self._clock_ms = clock_ms or (lambda: int(time.time() * 1000))
        self._scan_number = 0
        self._last_state: AutonomousScanState | None = None
        self._cycle_id = 0
        self._last_cycle: RotationCycle | None = None
        # Analysis is allowed to run concurrently across markets. The old
        # process-wide scan lock serialized every 5m/15m/1h event behind one
        # slow market, which made the live scanner appear frozen. State
        # persistence remains serialized separately below.
        self._state_lock = threading.RLock()
        self._market_locks = tuple(threading.RLock() for _ in universe.markets)
        self._manual_pause_until_ms = 0

    def _journal_state(self, state: AutonomousScanState) -> None:
        # Persistence is a projection of scanner state, not a reason to kill
        # the market-analysis worker. A corrupt/locked journal or registry
        # must be visible in logs while the scanner continues to rotate.
        if self.journal is not None:
            try:
                self.journal.record_scan(state)
            except Exception as exc:
                print(
                    f"AICFA journal error: {type(exc).__name__}: {exc}",
                    flush=True,
                )
        if self.registry is not None:
            try:
                self.registry.record_scan(state)
            except Exception as exc:
                print(
                    f"AICFA registry error: {type(exc).__name__}: {exc}",
                    flush=True,
                )

    @property
    def automatic_scan_paused(self) -> bool:
        return self._clock_ms() < self._manual_pause_until_ms

    @property
    def automatic_pause_until_ms(self) -> int:
        return self._manual_pause_until_ms

    def pause_automatic_scanning(self, seconds: float = MANUAL_SCAN_PAUSE_SECONDS) -> int:
        """Pause the automatic queue for a short manual Market Watch scan window."""
        if seconds <= 0:
            raise ValueError("pause duration must be greater than zero")
        # Do not take the scan lock here: a manual click must pause the
        # automatic queue immediately even if an automatic market is currently
        # being analyzed. The running scan is allowed to finish, then the
        # queue observes this deadline before starting another market.
        now_ms = self._clock_ms()
        self._manual_pause_until_ms = max(
            self._manual_pause_until_ms,
            now_ms + int(seconds * 1000.0),
        )
        return self._manual_pause_until_ms

    def monitor_price(self, *, symbol: str, market_type: str, price: float, now_ms: int | None = None) -> tuple:
        """Evaluate active setups against a realtime price without rerunning SMC."""
        if price <= 0:
            raise ValueError("price must be positive")
        timestamp = self._clock_ms() if now_ms is None else int(now_ms)
        wait = SetupAssessment(
            decision=SetupDecision.NEED_MORE_EVIDENCE,
            candidates=(),
            missing_context=("realtime price monitoring",),
            conflicts=(),
            reasons=("price stream updates lifecycle only; it never creates a setup",),
        )
        results = []
        horizons = {
            setup.horizon
            for setup in self.lifecycle.active_setups(
                symbol=symbol, market_type=market_type
            )
        }
        for horizon in horizons:
            results.extend(
                self.lifecycle.evaluate_all(
                    symbol=symbol,
                    market_type=market_type,
                    horizon=horizon,
                    assessment=wait,
                    current_price=float(price),
                    current_high=float(price),
                    current_low=float(price),
                    now_ms=timestamp,
                )
            )
        result_tuple = tuple(results)
        if self.registry is not None and result_tuple:
            try:
                with self._state_lock:
                    self.registry.record_lifecycle_results(result_tuple, now_ms=timestamp)
            except Exception as exc:
                print(f"AICFA registry error: {type(exc).__name__}: {exc}", flush=True)
        if self.journal is not None and result_tuple:
            try:
                with self._state_lock:
                    self.journal.append(
                    "lifecycle_price",
                    timestamp,
                    {"symbol": symbol, "market_type": market_type, "price": float(price), "results": result_tuple},
                )
            except Exception as exc:
                print(f"AICFA journal error: {type(exc).__name__}: {exc}", flush=True)
        return result_tuple

    @property
    def last_state(self) -> AutonomousScanState | None:
        return self._last_state

    @property
    def scan_number(self) -> int:
        return self._scan_number

    @property
    def cycle_id(self) -> int:
        return self._cycle_id

    @property
    def last_cycle(self) -> RotationCycle | None:
        return self._last_cycle

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
        self._journal_state(state)
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
        self._journal_state(state)
        return state


    def _failure_scan(
        self,
        market_index: int,
        *,
        status: str,
        error: str,
        duration_ms: float = 0.0,
    ) -> MultiMarketScan:
        """Turn one-market failures into observable scan results instead of silent skips."""
        market_asset = self.universe.markets[market_index].asset
        failed = MarketHorizonScan(
            asset=market_asset,
            results=(),
            setups=(),
            lifecycle_results=(),
            diagnostics=MarketScanDiagnostics(
                total_duration_ms=duration_ms,
                resolution_duration_ms=0.0,
                snapshot_duration_ms=0.0,
                snapshot_metrics=(),
                horizon_timings=(),
                refetched_between_horizons=False,
                status=status,
                error=error,
            ),
        )
        return MultiMarketScan(markets=(failed,))

    def scan_market(
        self,
        market_index: int,
        *,
        now_ms: int | None = None,
        rotation_id: int = 0,
        queue_position: int = 0,
        journal: bool = True,
        enforce_timeout: bool = True,
        modes: Sequence[TradingMode] | None = None,
    ) -> AutonomousScanState:
        """Run exactly one configured market through the canonical scanner pipeline."""
        if market_index < 0 or market_index >= len(self.universe.markets):
            raise ValueError(
                f"market_index must be between 0 and {len(self.universe.markets) - 1}"
            )

        timestamp = self._clock_ms() if now_ms is None else now_ms
        market = MarketUniverse((self.universe.markets[market_index],))

        # Automatic rotation, manual Market Watch and closed-candle callbacks
        # can request the same market concurrently. SetupLifecycle is stateful:
        # overlapping scans for one asset can race its identity/lifecycle
        # transitions and persist an older snapshot after a newer one. Serialize
        # only per market; unrelated markets still analyze concurrently.
        market_lock = self._market_locks[market_index]
        with market_lock:
            try:
                timeout_context = _market_timeout(self.market_timeout_seconds) if enforce_timeout else _noop_context()
                with timeout_context:
                    result = scan_universe(
                        market,
                        provider=self.provider,
                        now_ms=timestamp,
                        resolver=self.resolver,
                        modes=tuple(modes) if modes is not None else self.modes,
                        lifecycle=self.lifecycle,
                    )
            except MarketExecutionTimeout as exc:
                result = self._failure_scan(
                    market_index,
                    status="timeout",
                    error=str(exc),
                    duration_ms=self.market_timeout_seconds * 1000.0,
                )
            except Exception as exc:
                result = self._failure_scan(
                    market_index,
                    status="error",
                    error=f"{type(exc).__name__}: {exc}",
                )

            # Persist and publish this market's result before another scan of
            # the same market can overwrite its registry/journal projection.
            with self._state_lock:
                self._scan_number += 1
                state = AutonomousScanState(
                    scan_number=self._scan_number,
                    scanned_at_ms=timestamp,
                    result=result,
                    rotation_id=rotation_id,
                    queue_position=queue_position,
                    universe_size=len(self.universe.markets),
                )
                self._last_state = state
                if journal:
                    self._journal_state(state)
                return state

    def run_cycle(
        self,
        *,
        now_ms: int | None = None,
        on_market: Callable[[RotationMarketMetric], None] | None = None,
    ) -> RotationCycle:
        """Run exactly one finite rotation over all configured markets."""
        if not self.universe.markets:
            raise ValueError("market universe must not be empty")

        started_at_ms = self._clock_ms() if now_ms is None else now_ms
        started = time.perf_counter()
        self._cycle_id += 1
        cycle_id = self._cycle_id
        metrics: list[RotationMarketMetric] = []

        for queue_position, market in enumerate(self.universe.markets, start=1):
            market_started = time.perf_counter()
            try:
                state = self.scan_market(queue_position - 1, now_ms=started_at_ms)
                scan = state.result.markets[0]
                diagnostics = scan.diagnostics
                status = str(diagnostics.status).strip().lower() if diagnostics is not None else "completed"
                error = diagnostics.error if diagnostics is not None else ""
                setup_count = len(scan.setups)
            except Exception as exc:
                status = "error"
                error = f"{type(exc).__name__}: {exc}"
                setup_count = 0

            metric = RotationMarketMetric(
                cycle_id=cycle_id,
                queue_position=queue_position,
                asset=market.asset,
                status=status,
                duration_ms=(time.perf_counter() - market_started) * 1000.0,
                setup_count=setup_count,
                error=error,
            )
            metrics.append(metric)
            if on_market is not None:
                on_market(metric)

        finished_at_ms = self._clock_ms()
        timeout_markets = sum(item.status == "timeout" for item in metrics)
        error_markets = sum(item.status == "error" for item in metrics)
        cycle = RotationCycle(
            cycle_id=cycle_id,
            started_at_ms=started_at_ms,
            finished_at_ms=finished_at_ms,
            total_duration_ms=(time.perf_counter() - started) * 1000.0,
            market_count=len(metrics),
            completed_markets=sum(item.status == "completed" for item in metrics),
            timeout_markets=timeout_markets,
            error_markets=error_markets,
            setup_count=sum(item.setup_count for item in metrics),
            markets=tuple(metrics),
        )
        self._last_cycle = cycle
        if self.journal is not None:
            self.journal.record_cycle(cycle)
        return cycle

    def run_forever_batches(
        self, *, interval_seconds: float = BATCH_SCAN_INTERVAL_SECONDS,
        batch_size: int = DEFAULT_MARKETS_PER_BATCH,
        on_scan: Callable[[AutonomousScanState], None] | None = None,
        on_error: Callable[[str, Exception], None] | None = None,
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
        rotation_id = 1
        universe_size = len(self.universe.markets)

        def report_error(asset: str, exc: Exception) -> None:
            # Observability hooks must never become a single point of failure
            # for the 24/7 rotation. Keep scanning even if a logger/consumer
            # callback itself is broken.
            if on_error is None:
                print(f"AICFA rotation error: {asset}: {type(exc).__name__}: {exc}", flush=True)
                return
            try:
                on_error(asset, exc)
            except Exception as callback_exc:
                print(
                    f"AICFA error callback failed for {asset}: "
                    f"{type(callback_exc).__name__}: {callback_exc}",
                    flush=True,
                )

        while True:
            if should_stop is not None and should_stop():
                return
            if self.automatic_scan_paused:
                remaining_ms = max(1, self.automatic_pause_until_ms - self._clock_ms())
                sleep(min(1.0, remaining_ms / 1000.0))
                continue
            asset = self.universe.markets[market_index].asset
            queue_position = market_index + 1
            # The interval is a start-to-start cadence, not an extra delay after
            # analysis. A 12-second scan therefore sleeps 18 seconds at a
            # 30-second cadence; a timed-out 25-second scan sleeps at most 5.
            scan_started = time.monotonic()
            try:
                state = self.scan_market(market_index, rotation_id=rotation_id, queue_position=queue_position)
            except Exception as exc:
                report_error(asset, exc)
                state = None
            if state is not None and on_scan is not None:
                try:
                    on_scan(state)
                except Exception as exc:
                    # A UI/logging callback failure is not a market-analysis
                    # failure and must not terminate the perpetual worker.
                    report_error(asset, exc)
            if should_stop is not None and should_stop():
                return
            market_index = (market_index + 1) % universe_size
            if market_index == 0:
                rotation_id += 1
            remaining = interval_seconds - (time.monotonic() - scan_started)
            if remaining > 0:
                sleep(remaining)
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


__all__ = ["AutonomousScanEngine", "AutonomousScanState", "BATCH_SCAN_INTERVAL_SECONDS", "DEFAULT_MARKET_TIMEOUT_SECONDS", "MANUAL_SCAN_PAUSE_SECONDS", "DEFAULT_MARKETS_PER_BATCH", "MAIN_SCAN_INTERVAL_SECONDS", "MarketExecutionTimeout", "RotationCycle", "RotationMarketMetric"]
