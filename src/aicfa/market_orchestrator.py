"""Autonomous primary-horizon orchestration over the existing AICFA setup engine.

This layer does not implement a second scanner or trading logic. It runs the
existing deterministic FindSetup pipeline for the three primary horizons and
preserves independent setup candidates across horizons and markets.
"""
from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Callable, Sequence

from .analysis_depth import resolve_analysis_depth
from .data_requirements import TradingMode, default_setup_requirements, mode_timeframe_profile
from .public_market_data import build_public_market_data_provider
from .market_data_router import FallbackMarketDataProvider, SharedSnapshotMarketDataProvider
from .find_setup import FindSetupRequest, FindSetupResult, find_setup
from .market_data import completed_ohlcv
from .features import build_features
from .derivatives_market_data import FallbackDerivativesProvider
from .market_universe import MarketUniverse
from .setup_lifecycle import SetupIdentity, SetupLifecycle, SetupLifecycleResult
from .trade_description import TradeDescription, build_trade_description


PRIMARY_TRADING_MODES: tuple[TradingMode, ...] = (
    TradingMode.INTRADAY,
    TradingMode.SWING,
    TradingMode.POSITION,
)


@dataclass(frozen=True)
class HorizonTiming:
    mode: TradingMode
    duration_ms: float
    setup_count: int
    decision: str


@dataclass(frozen=True)
class MarketScanDiagnostics:
    total_duration_ms: float
    resolution_duration_ms: float
    snapshot_duration_ms: float
    snapshot_metrics: tuple[object, ...]
    horizon_timings: tuple[HorizonTiming, ...]
    refetched_between_horizons: bool
    block_timings: tuple[object, ...] = ()
    feature_duration_ms: float = 0.0
    evidence_duration_ms: float = 0.0
    setup_duration_ms: float = 0.0
    lifecycle_event_count: int = 0
    status: str = "completed"
    error: str = ""


@dataclass(frozen=True)
class HorizonSetup:
    """One setup candidate with identity and current lifecycle projection."""

    mode: TradingMode
    candidate: object
    description: TradeDescription
    identity: SetupIdentity | None = None
    lifecycle_result: SetupLifecycleResult | None = None
    evidence_concepts: tuple[str, ...] = ()
    decision_action: str = "wait"


@dataclass(frozen=True)
class MarketHorizonScan:
    """All primary-horizon results for one resolved market."""

    asset: str
    results: tuple[FindSetupResult, ...]
    setups: tuple[HorizonSetup, ...]
    lifecycle_results: tuple[SetupLifecycleResult, ...] = ()
    diagnostics: MarketScanDiagnostics | None = None


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


def _shared_provider(provider: object | None) -> SharedSnapshotMarketDataProvider:
    """Normalize one provider into the request-scoped shared MTF provider."""
    if provider is None:
        provider = build_public_market_data_provider(timeout_seconds=10.0)
    if isinstance(provider, SharedSnapshotMarketDataProvider):
        return provider
    if isinstance(provider, FallbackMarketDataProvider):
        return SharedSnapshotMarketDataProvider(provider, ttl_seconds=60.0)
    return SharedSnapshotMarketDataProvider(
        FallbackMarketDataProvider([provider]), ttl_seconds=60.0
    )


def _primary_snapshot_limits(modes: Sequence[TradingMode]) -> dict[str, int]:
    """Take the maximum role-aware history depth required by any primary horizon."""
    merged: dict[str, int] = {}
    for mode in modes:
        plan = default_setup_requirements("AICFA", mode=mode)
        depth = resolve_analysis_depth(plan, timeframes=plan.required_timeframes)
        for timeframe, requirement in depth.items():
            merged[timeframe] = max(merged.get(timeframe, 0), requirement.minimum_rows)
    return merged


def _acquire_primary_snapshot(
    provider: object | None,
    *,
    asset: str,
    market_type: str,
    modes: Sequence[TradingMode],
    resolver: Callable[[str, str], str] | None,
) -> tuple[SharedSnapshotMarketDataProvider, str, dict[str, object]]:
    """Resolve once and acquire the full primary MTF OHLCV snapshot once."""
    shared = _shared_provider(provider)
    symbol = str(resolver(asset, market_type)) if resolver is not None else str(
        shared.resolve_symbol(asset, market_type=market_type)
    )
    limits = _primary_snapshot_limits(modes)
    primary_timeframes = ("1w", "1d", "4h", "1h", "15m", "5m")
    timeframes = tuple(timeframe for timeframe in primary_timeframes if timeframe in limits)
    snapshot = shared.fetch_ohlcv_snapshot(
        symbol=symbol,
        market_type=market_type,
        timeframes=timeframes,
        since_ms=None,
        limits={timeframe: limits[timeframe] for timeframe in timeframes},
        data_profile="primary-mtf",
    )
    return shared, symbol, {timeframe: item.frame for timeframe, item in snapshot.items()}


def _latest_execution_price(result: FindSetupResult, mode: TradingMode) -> float:
    """Read the latest completed execution close used by lifecycle evaluation."""
    timeframe = mode_timeframe_profile(mode).execution_timeframe
    frame = result.frames.get(timeframe)
    if frame is None or frame.empty or "close" not in frame.columns:
        raise ValueError(
            f"execution timeframe {timeframe} has no close data for lifecycle evaluation"
        )
    return float(frame["close"].iloc[-1])


def analyze_market_horizons(
    asset: str,
    *,
    provider: object | None = None,
    now_ms: int,
    market_type: str = "spot",
    resolver: Callable[[str, str], str] | None = None,
    modes: Sequence[TradingMode] = PRIMARY_TRADING_MODES,
    lifecycle: SetupLifecycle | None = None,
    venue_symbols: tuple[tuple[str, str], ...] = (),
    derivatives_provider: FallbackDerivativesProvider | None = None,
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

    market_started = time.perf_counter()
    acquisition_started = time.perf_counter()
    shared_provider, symbol, prefetched_frames = _acquire_primary_snapshot(
        provider,
        asset=asset,
        market_type=market_type,
        modes=normalized_modes,
        resolver=resolver,
    )
    acquisition_elapsed = (time.perf_counter() - acquisition_started) * 1000.0
    snapshot_metrics = tuple(getattr(shared_provider, "last_snapshot_metrics", ()))
    snapshot_elapsed = sum(getattr(item, "duration_ms", 0.0) for item in snapshot_metrics)
    resolution_elapsed = max(0.0, acquisition_elapsed - snapshot_elapsed)
    resolved = lambda _asset, _market_type: symbol
    # The six primary MTF frames are shared by all three horizons. Compute
    # their deterministic features once and reuse them instead of rebuilding
    # the same overlapping context for each horizon.
    feature_started = time.perf_counter()
    prefetched_analyses: dict[str, object] = {}
    for timeframe, frame in prefetched_frames.items():
        completed = completed_ohlcv(frame, timeframe=timeframe, now_ms=now_ms)
        if completed.empty:
            continue
        analysis = build_features(completed)
        if not analysis.empty:
            prefetched_analyses[timeframe] = analysis
    shared_feature_elapsed = (time.perf_counter() - feature_started) * 1000.0
    shared_derivatives_provider = derivatives_provider
    if market_type == "futures" and shared_derivatives_provider is None:
        shared_derivatives_provider = FallbackDerivativesProvider()

    results: list[FindSetupResult] = []
    horizon_timings: list[HorizonTiming] = []
    block_timings: list[object] = []
    feature_duration_ms = shared_feature_elapsed
    evidence_duration_ms = 0.0
    setup_duration_ms = 0.0
    refetched_timeframes: set[str] = set()
    setups: list[HorizonSetup] = []
    lifecycle_results: list[SetupLifecycleResult] = []
    for mode in normalized_modes:
        horizon_started = time.perf_counter()
        result = find_setup(
            FindSetupRequest(asset=asset, market_type=market_type, mode=mode),
            provider=shared_provider,
            now_ms=now_ms,
            resolver=resolved,
            prefetched_frames=prefetched_frames,
            prefetched_analyses=prefetched_analyses,
            derivatives_provider=shared_derivatives_provider,
            derivatives_venue_symbols=venue_symbols,
        )
        results.append(result)
        pipeline_diagnostics = getattr(result, "diagnostics", None)
        if pipeline_diagnostics is not None:
            block_timings.extend(getattr(pipeline_diagnostics, "block_timings", ()))
            feature_duration_ms += getattr(pipeline_diagnostics, "feature_duration_ms", 0.0)
            evidence_duration_ms += getattr(pipeline_diagnostics, "evidence_duration_ms", 0.0)
            setup_duration_ms += getattr(pipeline_diagnostics, "setup_duration_ms", 0.0)
            refetched_timeframes.update(getattr(pipeline_diagnostics, "refetched_timeframes", ()))
        horizon_timings.append(HorizonTiming(
            mode=mode,
            duration_ms=(time.perf_counter() - horizon_started) * 1000.0,
            setup_count=len(getattr(result.setup_assessment, "candidates", ())),
            decision=str(result.decision),
        ))
        candidates = getattr(result.setup_assessment, "candidates", ())

        mode_lifecycle: tuple[SetupLifecycleResult, ...] = ()
        if lifecycle is not None and str(result.decision_assessment.action.value) in {"long", "short"}:
            mode_lifecycle = lifecycle.evaluate_all(
                symbol=result.symbol,
                market_type=market_type,
                horizon=mode,
                assessment=result.setup_assessment,
                current_price=_latest_execution_price(result, mode),
                now_ms=now_ms,
            )
            lifecycle_results.extend(mode_lifecycle)

        lifecycle_by_identity = {
            item.identity: item
            for item in mode_lifecycle
            if item.identity is not None
        }
        if str(result.decision_assessment.action.value) not in {"long", "short"}:
            continue

        evidence_concepts = tuple(
            dict.fromkeys(
                item.concept_id
                for item in getattr(result.evidence_assessment, "observations", ())
                if item.state == "observed" and item.confidence >= 0.5
            )
        )
        for candidate in candidates:
            description = build_trade_description(result, candidate, now_ms=now_ms)
            identity = (
                lifecycle.identity(
                    symbol=result.symbol,
                    market_type=market_type,
                    horizon=mode,
                    candidate=candidate,
                )
                if lifecycle is not None
                else None
            )
            setups.append(
                HorizonSetup(
                    mode=mode,
                    candidate=candidate,
                    description=description,
                    identity=identity,
                    lifecycle_result=(
                        lifecycle_by_identity.get(identity) if identity is not None else None
                    ),
                    evidence_concepts=evidence_concepts,
                    decision_action=str(result.decision_assessment.action.value),
                )
            )

    resolved_asset = results[0].symbol
    return MarketHorizonScan(
        asset=resolved_asset,
        results=tuple(results),
        setups=tuple(setups),
        lifecycle_results=tuple(lifecycle_results),
        diagnostics=MarketScanDiagnostics(
            total_duration_ms=(time.perf_counter() - market_started) * 1000.0,
            resolution_duration_ms=resolution_elapsed,
            snapshot_duration_ms=snapshot_elapsed,
            snapshot_metrics=snapshot_metrics,
            horizon_timings=tuple(horizon_timings),
            refetched_between_horizons=bool(refetched_timeframes),
            block_timings=tuple(block_timings),
            feature_duration_ms=feature_duration_ms,
            evidence_duration_ms=evidence_duration_ms,
            setup_duration_ms=setup_duration_ms,
            lifecycle_event_count=len(lifecycle_results),
        ),
    )


def scan_markets(
    assets: Sequence[str],
    *,
    provider: object | None = None,
    now_ms: int,
    market_type: str = "spot",
    resolver: Callable[[str, str], str] | None = None,
    modes: Sequence[TradingMode] = PRIMARY_TRADING_MODES,
    lifecycle: SetupLifecycle | None = None,
    venue_symbols_by_asset: dict[str, tuple[tuple[str, str], ...]] | None = None,
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
            lifecycle=lifecycle,
            venue_symbols=(venue_symbols_by_asset or {}).get(asset, ()),
        )
        for asset in normalized_assets
    )
    return MultiMarketScan(markets=markets)


def scan_universe(
    universe: MarketUniverse,
    *,
    provider: object | None = None,
    now_ms: int,
    resolver: Callable[[str, str], str] | None = None,
    modes: Sequence[TradingMode] = PRIMARY_TRADING_MODES,
    lifecycle: SetupLifecycle | None = None,
) -> MultiMarketScan:
    """Scan the durable configured universe without hardcoding any asset."""
    register = getattr(provider, "register_market_symbols", None)
    if register is not None:
        for market in universe.markets:
            if market.venue_symbols:
                register(
                    market.asset,
                    market.venue_symbols,
                    market_type=market.market_type,
                )

    markets = tuple(
        analyze_market_horizons(
            market.asset,
            provider=provider,
            now_ms=now_ms,
            market_type=market.market_type,
            resolver=resolver,
            modes=modes,
            lifecycle=lifecycle,
            venue_symbols=market.venue_symbols,
        )
        for market in universe.markets
    )
    return MultiMarketScan(markets=markets)
