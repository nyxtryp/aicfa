"""Single-command FindSetup orchestration for AICFA.

This module is the deterministic bridge from a user-named asset to the
existing market-data and reasoning core. It does not use an LLM and does not
place orders.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
import time
from typing import Callable

import pandas as pd

from .binance_market_data import BinanceMarketDataProvider
from .bybit_market_data import BybitMarketDataProvider
from .public_market_data import build_public_market_data_provider
from .analysis_depth import resolve_analysis_depth
from .data_requirements import DataKind, TradingMode, default_setup_requirements, mode_timeframe_profile, normalize_trading_mode
from .decision import decide
from .evidence_reasoning import assess_market_evidence
from .features import build_features
from .market_data import MarketDataProvider, completed_ohlcv
from .market_data_router import FallbackMarketDataProvider, SharedSnapshotMarketDataProvider
from .order_flow import build_trade_order_flow
from .cvd import build_trade_cvd
from .order_book import build_order_book
from .absorption import build_absorption
from .market_evidence_adapter import build_market_evidence_from_frames
from .market_context_evidence import append_market_context_evidence
from .scenario_reasoning import assess_scenarios
from .setup_analysis import analyze_setups
from .derivatives import build_derivatives
from .derivatives_evidence import append_derivatives_evidence
from .derivatives_market_data import FallbackDerivativesProvider

CAUSAL_TIMEFRAMES = ("1m", "5m", "15m", "1h", "4h", "1d", "1w")


def _safe_optional_call(call, **kwargs):
    """Best-effort enrichment: optional feed failure never blocks structural analysis."""
    try:
        return call(**kwargs)
    except Exception as exc:
        # The whole-market execution budget must propagate through optional
        # enrichment instead of being swallowed by its best-effort boundary.
        if exc.__class__.__name__ == "MarketExecutionTimeout":
            raise
        return None, exc


@dataclass(frozen=True)
class FindSetupRequest:
    """Normalized single-command request."""

    asset: str
    market_type: str = "spot"
    mode: TradingMode | str = TradingMode.INTRADAY

    def __post_init__(self) -> None:
        if not self.asset.strip():
            raise ValueError("asset must not be empty")
        if self.market_type not in {"spot", "futures"}:
            raise ValueError("market_type must be spot or futures")
        object.__setattr__(self, "mode", normalize_trading_mode(self.mode))


@dataclass(frozen=True)
class DataBlockTiming:
    block: str
    status: str
    duration_ms: float
    rows: int = 0
    provider: str = ""
    reason: str = ""


@dataclass(frozen=True)
class FindSetupDiagnostics:
    block_timings: tuple[DataBlockTiming, ...] = ()
    feature_duration_ms: float = 0.0
    evidence_duration_ms: float = 0.0
    setup_duration_ms: float = 0.0
    decision_duration_ms: float = 0.0
    refetched_timeframes: tuple[str, ...] = ()


@dataclass(frozen=True)
class FindSetupResult:
    """Complete deterministic result for one requested asset."""

    request: FindSetupRequest
    mode: TradingMode
    symbol: str
    timeframes: tuple[str, ...]
    frames: dict[str, pd.DataFrame]
    analysis: pd.DataFrame
    evidence: object
    evidence_assessment: object
    scenario_assessment: object
    setup_assessment: object
    decision_assessment: object
    trades: pd.DataFrame
    order_book: pd.DataFrame
    order_flow_analysis: pd.DataFrame
    order_book_analysis: pd.DataFrame
    cvd_analysis: pd.DataFrame
    absorption_analysis: pd.DataFrame
    order_book_history: pd.DataFrame
    order_book_history_provider: str
    trades_provider: str
    derivatives: pd.DataFrame
    derivatives_analysis: pd.DataFrame
    derivatives_provider: str
    order_book_provider: str
    decision: str
    reason: str
    diagnostics: FindSetupDiagnostics = FindSetupDiagnostics()


_ASSET_RE = re.compile(r"\b([A-Za-z0-9]{2,20}(?:[/_-][A-Za-z0-9]{2,20})?)\b")


def normalize_asset(asset: str) -> str:
    """Normalize common crypto notation without guessing a quote currency."""
    value = asset.strip().upper().replace("-", "/").replace("_", "/")
    if "/" in value:
        base, quote = (part.strip() for part in value.split("/", 1))
        if not base or not quote:
            raise ValueError("asset must contain non-empty base and quote")
        return f"{base}/{quote}"
    return value


def parse_find_setup(text: str) -> FindSetupRequest:
    """Parse 'Найди сетап <asset>' or an equivalent concise command."""
    value = text.strip()
    if not value:
        raise ValueError("request text must not be empty")

    match = re.search(r"(?:найди\s+сетап|find\s+setup)\s+(.+)$", value, re.IGNORECASE)
    asset_text = match.group(1).strip() if match else value
    asset_match = _ASSET_RE.search(asset_text)
    if not asset_match:
        raise ValueError("could not extract asset from request")
    return FindSetupRequest(asset=normalize_asset(asset_match.group(1)))


def _fetch_frames(
    provider: MarketDataProvider,
    *,
    symbol: str,
    market_type: str,
    timeframes: tuple[str, ...],
    limits: dict[str, int],
) -> dict[str, pd.DataFrame]:
    """Fetch one temporary request snapshot at the supplied per-TF depths."""
    if isinstance(provider, SharedSnapshotMarketDataProvider):
        snapshot = provider.fetch_ohlcv_snapshot(
            symbol=symbol, market_type=market_type, timeframes=timeframes,
            since_ms=None, limits=limits,
        )
        return {timeframe: result.frame for timeframe, result in snapshot.items()}
    return {
        timeframe: (result.frame if hasattr(result, "frame") else result)
        for timeframe in timeframes
        for result in (provider.fetch_ohlcv(
            symbol=symbol, market_type=market_type, timeframe=timeframe,
            since_ms=None, limit=limits[timeframe],
        ),)
    }


def _context_signature(evidence: object) -> tuple[object, ...]:
    """Return only causal context state relevant to expansion progress."""
    observations = getattr(evidence, "observations", ())
    return (
        tuple(
            (
                item.concept_id,
                item.timeframe,
                item.state,
                item.direction,
                tuple(item.evidence),
            )
            for item in observations
        ),
        tuple(getattr(evidence, "missing_context", ())),
        tuple(getattr(evidence, "conflicts", ())),
    )


def _expand_missing_context(
    provider: MarketDataProvider,
    *,
    symbol: str,
    market_type: str,
    timeframes: tuple[str, ...],
    limits: dict[str, int],
    frames: dict[str, pd.DataFrame],
    missing_context: tuple[str, ...],
    now_ms: int,
    analyses: dict[str, pd.DataFrame],
) -> tuple[dict[str, pd.DataFrame], dict[str, int], dict[str, pd.DataFrame]]:
    """Expand unresolved context until it stops changing or data is exhausted."""
    exhausted: set[str] = set()
    current_limits = dict(limits)
    current_frames = dict(frames)
    current_missing = tuple(missing_context)
    previous_signature: tuple[object, ...] | None = None
    expansion_passes = 0
    max_expansion_passes = 2
    current_analyses = dict(analyses)

    while True:
        unresolved = {
            item.split(":", 1)[0] for item in current_missing if ":" in item
        } - exhausted
        if not unresolved:
            return current_frames, current_limits, current_analyses

        requested = {
            timeframe: current_limits[timeframe] * 2
            for timeframe in unresolved
        }
        fetched = _fetch_frames(
            provider, symbol=symbol, market_type=market_type,
            timeframes=tuple(sorted(unresolved, key=timeframes.index)),
            limits=requested,
        )
        for timeframe in unresolved:
            rows = len(fetched[timeframe])
            current_frames[timeframe] = fetched[timeframe]
            current_limits[timeframe] = requested[timeframe]
            if rows < requested[timeframe]:
                exhausted.add(timeframe)

        for timeframe in unresolved:
            frame = current_frames[timeframe]
            completed = completed_ohlcv(
                frame, timeframe=timeframe, now_ms=now_ms,
            )
            if completed.empty:
                current_analyses.pop(timeframe, None)
                continue
            timeframe_analysis = build_features(completed)
            if timeframe_analysis.empty:
                current_analyses.pop(timeframe, None)
            else:
                current_analyses[timeframe] = timeframe_analysis

        evidence = build_market_evidence_from_frames(
            current_analyses, asset=symbol, timeframes=timeframes,
        )
        signature = _context_signature(evidence)
        expansion_passes += 1
        if signature == previous_signature or expansion_passes >= max_expansion_passes:
            return current_frames, current_limits, current_analyses
        previous_signature = signature
        current_missing = evidence.missing_context

def find_setup(
    request: FindSetupRequest,
    *,
    provider: MarketDataProvider | None = None,
    now_ms: int,
    limit: int | None = None,
    resolver: Callable[[str, str], str] | None = None,
    derivatives_provider: object | None = None,
    derivatives_venue_symbols: tuple[tuple[str, str], ...] = (),
    prefetched_frames: dict[str, pd.DataFrame] | None = None,
    prefetched_analyses: dict[str, pd.DataFrame] | None = None,
) -> FindSetupResult:
    """Resolve the asset, collect knowledge-required context, and run AICFA."""
    use_live_derivatives = provider is None
    # Futures are derivative instruments: collect the existing causal
    # derivatives evidence layer automatically for live FindSetup requests.
    # Spot/TradFi requests do not pay this cost unless explicitly requested.
    if use_live_derivatives and request.market_type == "futures" and derivatives_provider is None:
        derivatives_provider = FallbackDerivativesProvider()
    if provider is None:
        provider = build_public_market_data_provider(timeout_seconds=10.0)
    if isinstance(provider, FallbackMarketDataProvider):
        provider = SharedSnapshotMarketDataProvider(provider, ttl_seconds=60.0)
    if resolver is None:
        resolver = lambda asset, market_type: provider.resolve_symbol(
            asset, market_type=market_type
        )
    symbol = normalize_asset(resolver(request.asset, request.market_type))

    profile = mode_timeframe_profile(request.mode)
    requirements = default_setup_requirements(symbol, mode=request.mode)
    timeframes = requirements.required_timeframes
    if not timeframes:
        raise ValueError("knowledge requirements produced no timeframes")
    depth = resolve_analysis_depth(requirements, timeframes=timeframes)
    limits = {timeframe: requirement.minimum_rows for timeframe, requirement in depth.items()}
    if limit is not None:
        limits = {timeframe: int(limit) for timeframe in timeframes}

    block_timings: list[DataBlockTiming] = []
    if prefetched_frames is not None:
        missing = [timeframe for timeframe in timeframes if timeframe not in prefetched_frames]
        if missing:
            raise ValueError(f"prefetched OHLCV snapshot is missing timeframes: {missing}")
        frames = {timeframe: prefetched_frames[timeframe].copy(deep=True) for timeframe in timeframes}
        block_timings.extend(
            DataBlockTiming(f"ohlcv:{tf}", "prefetched", 0.0, len(frames[tf]))
            for tf in timeframes
        )
    else:
        fetch_started = time.perf_counter()
        frames = _fetch_frames(
            provider, symbol=symbol, market_type=request.market_type,
            timeframes=timeframes, limits=limits,
        )
        elapsed = (time.perf_counter() - fetch_started) * 1000.0
        block_timings.extend(
            DataBlockTiming(f"ohlcv:{tf}", "fetched", elapsed, len(frames[tf]))
            for tf in timeframes
        )

    execution_timeframe = profile.execution_timeframe
    base = completed_ohlcv(
        frames[execution_timeframe], timeframe=execution_timeframe, now_ms=now_ms
    )
    if base.empty:
        raise ValueError(f"no completed {execution_timeframe} candle available for decision")

    completed_frames: dict[str, pd.DataFrame] = {}
    analyses: dict[str, pd.DataFrame] = {}
    if prefetched_analyses is not None:
        missing_analyses = [timeframe for timeframe in timeframes if timeframe not in prefetched_analyses]
        if missing_analyses:
            raise ValueError(f"prefetched feature analysis is missing timeframes: {missing_analyses}")
        for timeframe in timeframes:
            completed = completed_ohlcv(frames[timeframe], timeframe=timeframe, now_ms=now_ms)
            if completed.empty:
                continue
            completed_frames[timeframe] = completed
            analyses[timeframe] = prefetched_analyses[timeframe].copy(deep=True)
        feature_duration_ms = 0.0
    else:
        feature_started = time.perf_counter()
        for timeframe, frame in frames.items():
            completed = completed_ohlcv(frame, timeframe=timeframe, now_ms=now_ms)
            if completed.empty:
                continue
            completed_frames[timeframe] = completed
            timeframe_analysis = build_features(completed)
            if not timeframe_analysis.empty:
                analyses[timeframe] = timeframe_analysis
        feature_duration_ms = (time.perf_counter() - feature_started) * 1000.0

    base_analysis = analyses.get(execution_timeframe)
    if base_analysis is None:
        raise ValueError(f"AICFA analysis produced no completed {execution_timeframe} rows")
    analysis = base_analysis

    evidence_started = time.perf_counter()
    market_evidence = build_market_evidence_from_frames(
        analyses,
        asset=symbol,
        timeframes=timeframes,
    )
    evidence_duration_ms = (time.perf_counter() - evidence_started) * 1000.0
    refetched_timeframes: list[str] = []
    if market_evidence.missing_context and limit is None:
        refetched_timeframes = sorted(
            {item.split(":", 1)[0] for item in market_evidence.missing_context if ":" in item},
            key=timeframes.index,
        )
        refetch_started = time.perf_counter()
        frames, limits, analyses = _expand_missing_context(
            provider,
            symbol=symbol,
            market_type=request.market_type,
            timeframes=timeframes,
            limits=limits,
            frames=frames,
            missing_context=market_evidence.missing_context,
            now_ms=now_ms,
            analyses=analyses,
        )
        refetch_elapsed = (time.perf_counter() - refetch_started) * 1000.0
        for timeframe in refetched_timeframes:
            block_timings.append(
                DataBlockTiming(
                    f"ohlcv:{timeframe}",
                    "refetched",
                    refetch_elapsed,
                    len(frames[timeframe]),
                    reason="missing_context expansion",
                )
            )
        base_analysis = analyses.get(execution_timeframe)
        if base_analysis is None:
            raise ValueError(f"AICFA analysis produced no completed {execution_timeframe} rows")
        analysis = base_analysis
        evidence_started = time.perf_counter()
        market_evidence = build_market_evidence_from_frames(
            analyses, asset=symbol, timeframes=timeframes,
        )
        evidence_duration_ms += (time.perf_counter() - evidence_started) * 1000.0
    derivatives_frame = pd.DataFrame()
    derivatives_analysis = pd.DataFrame()
    derivatives_source = ""
    if requirements.requires(DataKind.FUNDING) or derivatives_provider is not None:
        derivatives_started = time.perf_counter()
        try:
            derivatives_source_provider = derivatives_provider or FallbackDerivativesProvider()
            try:
                derivatives_frame, derivatives_source = derivatives_source_provider.fetch_derivatives(
                    symbol=symbol,
                    limit=200,
                    venue_symbols=derivatives_venue_symbols,
                )
            except TypeError:
                derivatives_frame, derivatives_source = derivatives_source_provider.fetch_derivatives(
                    symbol=symbol,
                    limit=200,
                )
            derivatives_analysis = build_derivatives(
                base,
                derivatives_frame,
                baseline_window=24,
            )
        except Exception as exc:
            if exc.__class__.__name__ == "MarketExecutionTimeout":
                raise
            derivatives_frame = pd.DataFrame()
            derivatives_analysis = pd.DataFrame()
            derivatives_source = f"unavailable: {exc}"

        derivatives_elapsed = (time.perf_counter() - derivatives_started) * 1000.0
        block_timings.append(
            DataBlockTiming(
                "derivatives",
                "complete" if not derivatives_frame.empty else "unavailable",
                derivatives_elapsed,
                len(derivatives_frame),
                provider=derivatives_source,
                reason="" if not derivatives_frame.empty else derivatives_source,
            )
        )
        for block_name, column in (
            ("funding", "funding_rate"),
            ("open_interest", "open_interest"),
            ("mark_price", "mark_price"),
        ):
            covered = (
                not derivatives_frame.empty
                and column in derivatives_frame.columns
                and derivatives_frame[column].notna().any()
            )
            block_timings.append(
                DataBlockTiming(
                    block_name,
                    "complete" if covered else "unavailable",
                    derivatives_elapsed,
                    int(derivatives_frame[column].notna().sum()) if column in derivatives_frame.columns else 0,
                    provider=derivatives_source,
                    reason="" if covered else f"missing {column}",
                )
            )
        liquidation_column = "liquidation_volume"
        liquidation_events = (
            int(derivatives_frame[liquidation_column].notna().sum())
            if liquidation_column in derivatives_frame.columns and not derivatives_frame.empty
            else 0
        )
        block_timings.append(
            DataBlockTiming(
                "liquidations",
                "complete" if liquidation_events else "no_events",
                derivatives_elapsed,
                liquidation_events,
                provider=derivatives_source,
                reason="" if liquidation_events else "no liquidation events observed in provider window",
            )
        )
        market_evidence = append_derivatives_evidence(
            market_evidence,
            derivatives_frame,
            timeframe=profile.context_timeframe,
        )

    # The seven data blocks are independent enrichments. Fetch the slow
    # optional feeds concurrently so a slow order-book history request does
    # not serialize derivatives and trades behind it.
    #
    # Keep the structural OHLCV/SMC path synchronous; this only changes
    # acquisition of optional futures enrichment.
    trades = pd.DataFrame()
    order_book = pd.DataFrame()
    order_flow_analysis = pd.DataFrame()
    order_book_analysis = pd.DataFrame()
    cvd_analysis = pd.DataFrame()
    absorption_analysis = pd.DataFrame()
    order_book_history = pd.DataFrame()
    order_book_history_provider = ""
    trades_provider = ""
    order_book_provider = ""

    # Collect auxiliary market feeds only when the active knowledge plan
    # explicitly requires them. Core chart/SMC analysis does not pay the
    # collection/storage cost for feeds it does not need.
    if request.market_type == "futures" or requirements.requires(DataKind.TRADES):
        trade_started = time.perf_counter()
        trade_fetch = getattr(provider, "fetch_trades_with_source", None)
        trade_limit = 60
        if trade_fetch is not None:
            trade_result = _safe_optional_call(
                trade_fetch,
                symbol=symbol, market_type=request.market_type, limit=trade_limit,
            )
            if isinstance(trade_result, tuple) and len(trade_result) == 2 and isinstance(trade_result[1], Exception):
                trades_provider = f"unavailable: {trade_result[1]}"
            else:
                trades = trade_result.frame
                trades_provider = trade_result.provider
        else:
            trade_result = _safe_optional_call(
                provider.fetch_trades,
                symbol=symbol, market_type=request.market_type, limit=trade_limit,
            )
            if isinstance(trade_result, tuple) and len(trade_result) == 2 and isinstance(trade_result[1], Exception):
                trades_provider = f"unavailable: {trade_result[1]}"
            else:
                trades = trade_result
                trades_provider = provider.__class__.__name__

        block_timings.append(
            DataBlockTiming(
                "trades",
                "complete" if not trades.empty else "unavailable",
                (time.perf_counter() - trade_started) * 1000.0,
                len(trades),
                provider=trades_provider,
                reason="" if not trades.empty else trades_provider,
            )
        )
        if not trades.empty:
            trade_work = trades.copy()
            trade_work["timestamp"] = pd.to_datetime(trade_work["timestamp"], unit="ms", utc=True)
            latest_trade_timestamp = trade_work["timestamp"].max()
            flow_base = pd.DataFrame({"timestamp": [latest_trade_timestamp]})
            order_flow_analysis = build_trade_order_flow(
                flow_base, trades, baseline_window=24, event_window=60
            )
            cvd_analysis = build_trade_cvd(
                pd.DataFrame({"timestamp": [latest_trade_timestamp]}), trades
            )

    if request.market_type == "futures" or requirements.requires(DataKind.ORDER_BOOK):
        order_book_started = time.perf_counter()
        history_fetch = getattr(provider, "fetch_order_book_history_with_source", None)
        if history_fetch is not None:
            history_result = _safe_optional_call(
                history_fetch,
                symbol=symbol,
                market_type=request.market_type,
                snapshots=8,
                interval_seconds=0.25,
            )
            if isinstance(history_result, tuple) and len(history_result) == 2 and isinstance(history_result[1], Exception):
                order_book_history_provider = f"unavailable: {history_result[1]}"
            else:
                order_book_history = history_result.frame
                order_book_history_provider = history_result.provider

        # The final history snapshot is already a current order-book snapshot.
        # Reuse it when available instead of issuing a ninth REST request.
        book_result = None
        if not order_book_history.empty:
            order_book = order_book_history.tail(1).copy(deep=True)
            order_book_provider = order_book_history_provider
        else:
            book_fetch = getattr(provider, "fetch_order_book_with_source", None)
            if book_fetch is not None:
                book_result = _safe_optional_call(
                    book_fetch,
                    symbol=symbol, market_type=request.market_type, limit=1,
                )
                if isinstance(book_result, tuple) and len(book_result) == 2 and isinstance(book_result[1], Exception):
                    order_book_provider = f"unavailable: {book_result[1]}"
                else:
                    order_book = book_result.frame
                    order_book_provider = book_result.provider
            else:
                book_result = _safe_optional_call(
                    provider.fetch_order_book,
                    symbol=symbol, market_type=request.market_type, limit=1,
                )
                if isinstance(book_result, tuple) and len(book_result) == 2 and isinstance(book_result[1], Exception):
                    order_book_provider = f"unavailable: {book_result[1]}"
                else:
                    order_book = book_result
                    order_book_provider = provider.__class__.__name__

        block_timings.append(
            DataBlockTiming(
                "order_book",
                "complete" if not order_book.empty else "unavailable",
                (time.perf_counter() - order_book_started) * 1000.0,
                len(order_book),
                provider=order_book_provider,
                reason="" if not order_book.empty else order_book_provider,
            )
        )
        if not order_book.empty:
            book_work = order_book.copy()
            book_work["timestamp"] = pd.to_datetime(book_work["timestamp"], unit="ms", utc=True)
            order_book_analysis = build_order_book(
                pd.DataFrame({"timestamp": book_work["timestamp"]}), order_book
            )

        block_timings.append(
            DataBlockTiming(
                "order_book_history",
                "complete" if not order_book_history.empty else "unavailable",
                (time.perf_counter() - order_book_started) * 1000.0,
                len(order_book_history),
                provider=order_book_history_provider,
                reason="" if not order_book_history.empty else order_book_history_provider,
            )
        )
        if not order_book_history.empty and not trades.empty:
            history_work = order_book_history.copy()
            history_work["timestamp"] = pd.to_datetime(history_work["timestamp"], unit="ms", utc=True)
            for column in ("bid_price", "bid_size", "ask_price", "ask_size"):
                history_work[column] = pd.to_numeric(history_work[column], errors="raise")

            levels = pd.concat(
                [
                    history_work[["timestamp", "bid_price", "bid_size"]].rename(
                        columns={"bid_price": "price", "bid_size": "size"}
                    ).assign(side="bid"),
                    history_work[["timestamp", "ask_price", "ask_size"]].rename(
                        columns={"ask_price": "price", "ask_size": "size"}
                    ).assign(side="ask"),
                ],
                ignore_index=True,
            )
            mids = (history_work["bid_price"] + history_work["ask_price"]) / 2.0
            price_frame = pd.DataFrame({"timestamp": history_work["timestamp"], "mid": mids})
            price_frame = price_frame.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)
            price_frame["open"] = price_frame["mid"].shift(1).fillna(price_frame["mid"])
            price_frame["close"] = price_frame["mid"]
            price_frame["high"] = price_frame[["open", "close"]].max(axis=1)
            price_frame["low"] = price_frame[["open", "close"]].min(axis=1)
            absorption_analysis = build_absorption(
                price_frame[["timestamp", "open", "high", "low", "close"]],
                order_flow_analysis,
                levels,
            )

    # Feed every collected microstructure/context layer into the same causal
    # evidence graph used by scenario, setup and final decision reasoning.
    market_evidence = append_market_context_evidence(
        market_evidence,
        timeframe=profile.execution_timeframe,
        trades=trades,
        order_flow=order_flow_analysis,
        cvd=cvd_analysis,
        order_book=order_book_analysis,
        absorption=absorption_analysis,
        analysis=base_analysis,
        derivatives=derivatives_frame,
    )

    reasoning_started = time.perf_counter()
    evidence_assessment = assess_market_evidence(market_evidence)
    evidence_duration_ms += (time.perf_counter() - reasoning_started) * 1000.0
    scenario_assessment = assess_scenarios(evidence_assessment)
    setup_started = time.perf_counter()
    setup_assessment = analyze_setups(
        evidence_assessment,
        scenario_assessment,
        observations=evidence_assessment.observations,
        analyses=analyses,
        timeframes=timeframes,
        mode=request.mode,
    )
    setup_duration_ms = (time.perf_counter() - setup_started) * 1000.0
    decision_started = time.perf_counter()
    decision_assessment = decide(
        setup_assessment,
        observations=evidence_assessment.observations,
        current_price=float(base_analysis["close"].iloc[-1]) if "close" in base_analysis.columns else None,
    )
    decision_duration_ms = (time.perf_counter() - decision_started) * 1000.0

    return FindSetupResult(
        request=request,
        mode=request.mode,
        symbol=symbol,
        timeframes=timeframes,
        frames=frames,
        analysis=analysis,
        evidence=market_evidence,
        evidence_assessment=evidence_assessment,
        scenario_assessment=scenario_assessment,
        setup_assessment=setup_assessment,
        decision_assessment=decision_assessment,
        trades=trades,
        order_book=order_book,
        order_flow_analysis=order_flow_analysis,
        order_book_analysis=order_book_analysis,
        cvd_analysis=cvd_analysis,
        absorption_analysis=absorption_analysis,
        order_book_history=order_book_history,
        order_book_history_provider=order_book_history_provider,
        trades_provider=trades_provider,
        order_book_provider=order_book_provider,
        derivatives=derivatives_frame,
        derivatives_analysis=derivatives_analysis,
        derivatives_provider=derivatives_source,
        decision=decision_assessment.action.value.upper().replace("_", " "),
        reason="; ".join(decision_assessment.reasons),
        diagnostics=FindSetupDiagnostics(
            block_timings=tuple(block_timings),
            feature_duration_ms=feature_duration_ms,
            evidence_duration_ms=evidence_duration_ms,
            setup_duration_ms=setup_duration_ms,
            decision_duration_ms=decision_duration_ms,
            refetched_timeframes=tuple(refetched_timeframes),
        ),
    )
