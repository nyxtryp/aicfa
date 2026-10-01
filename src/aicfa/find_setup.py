"""Single-command FindSetup orchestration for AICFA.

This module is the deterministic bridge from a user-named asset to the
existing market-data and reasoning core. It does not use an LLM and does not
place orders.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Callable

import pandas as pd

from .binance_market_data import BinanceMarketDataProvider
from .bybit_market_data import BybitMarketDataProvider
from .analysis_depth import resolve_analysis_depth
from .data_requirements import default_setup_requirements
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
from .scenario_reasoning import assess_scenarios
from .setup_analysis import analyze_setups

CAUSAL_TIMEFRAMES = ("1m", "5m", "15m", "1h", "4h", "1d", "1w")


@dataclass(frozen=True)
class FindSetupRequest:
    """Normalized single-command request."""

    asset: str
    market_type: str = "spot"

    def __post_init__(self) -> None:
        if not self.asset.strip():
            raise ValueError("asset must not be empty")
        if self.market_type not in {"spot", "futures"}:
            raise ValueError("market_type must be spot or futures")


@dataclass(frozen=True)
class FindSetupResult:
    """Complete deterministic result for one requested asset."""

    request: FindSetupRequest
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
    order_book_provider: str
    decision: str
    reason: str


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
) -> FindSetupResult:
    """Resolve the asset, collect knowledge-required context, and run AICFA."""
    if provider is None:
        provider = FallbackMarketDataProvider(
            (BinanceMarketDataProvider(), BybitMarketDataProvider())
        )
    if isinstance(provider, FallbackMarketDataProvider):
        provider = SharedSnapshotMarketDataProvider(provider, ttl_seconds=60.0)
    if resolver is None:
        resolver = lambda asset, market_type: provider.resolve_symbol(
            asset, market_type=market_type
        )
    symbol = normalize_asset(resolver(request.asset, request.market_type))

    requirements = default_setup_requirements(symbol)
    timeframes = requirements.required_timeframes
    if not timeframes:
        raise ValueError("knowledge requirements produced no timeframes")
    depth = resolve_analysis_depth(requirements, timeframes=timeframes)
    limits = {timeframe: requirement.minimum_rows for timeframe, requirement in depth.items()}
    if limit is not None:
        limits = {timeframe: int(limit) for timeframe in timeframes}

    frames = _fetch_frames(
        provider, symbol=symbol, market_type=request.market_type,
        timeframes=timeframes, limits=limits,
    )

    base = completed_ohlcv(frames["1m"], timeframe="1m", now_ms=now_ms)
    if base.empty:
        raise ValueError("no completed 1m candle available for decision")

    completed_frames: dict[str, pd.DataFrame] = {}
    analyses: dict[str, pd.DataFrame] = {}
    for timeframe, frame in frames.items():
        completed = completed_ohlcv(frame, timeframe=timeframe, now_ms=now_ms)
        if completed.empty:
            continue
        completed_frames[timeframe] = completed
        timeframe_analysis = build_features(completed)
        if not timeframe_analysis.empty:
            analyses[timeframe] = timeframe_analysis

    base_analysis = analyses.get("1m")
    if base_analysis is None:
        raise ValueError("AICFA analysis produced no completed 1m rows")
    analysis = base_analysis

    market_evidence = build_market_evidence_from_frames(
        analyses,
        asset=symbol,
        timeframes=timeframes,
    )
    if market_evidence.missing_context and limit is None:
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
        base_analysis = analyses.get("1m")
        if base_analysis is None:
            raise ValueError("AICFA analysis produced no completed 1m rows")
        analysis = base_analysis
        market_evidence = build_market_evidence_from_frames(
            analyses, asset=symbol, timeframes=timeframes,
        )
    trade_fetch = getattr(provider, "fetch_trades_with_source", None)
    book_fetch = getattr(provider, "fetch_order_book_with_source", None)

    trade_limit = 60
    if trade_fetch is not None:
        trade_result = trade_fetch(
            symbol=symbol, market_type=request.market_type, limit=trade_limit
        )
        trades = trade_result.frame
        trades_provider = trade_result.provider
    else:
        trades = provider.fetch_trades(
            symbol=symbol, market_type=request.market_type, limit=trade_limit
        )
        trades_provider = provider.__class__.__name__

    if trades.empty:
        raise ValueError("no trade data available for microstructure analysis")

    history_fetch = getattr(provider, "fetch_order_book_history_with_source", None)
    if history_fetch is not None:
        history_result = history_fetch(
            symbol=symbol,
            market_type=request.market_type,
            snapshots=8,
            interval_seconds=1.0,
        )
        order_book_history = history_result.frame
        order_book_history_provider = history_result.provider
    else:
        order_book_history = pd.DataFrame()
        order_book_history_provider = ""
    if book_fetch is not None:
        book_result = book_fetch(
            symbol=symbol, market_type=request.market_type, limit=1
        )
        order_book = book_result.frame
        order_book_provider = book_result.provider
    else:
        order_book = provider.fetch_order_book(
            symbol=symbol, market_type=request.market_type, limit=1
        )
        order_book_provider = provider.__class__.__name__

    trade_work = trades.copy()
    trade_work["timestamp"] = pd.to_datetime(trade_work["timestamp"], unit="ms", utc=True)
    latest_trade_timestamp = trade_work["timestamp"].max()
    history_work = order_book_history.copy()
    if not history_work.empty:
        history_work["timestamp"] = pd.to_datetime(history_work["timestamp"], unit="ms", utc=True)
        for column in ("bid_price", "bid_size", "ask_price", "ask_size"):
            history_work[column] = pd.to_numeric(history_work[column], errors="raise")
        latest_book_timestamp = history_work["timestamp"].max()
    else:
        latest_book_timestamp = latest_trade_timestamp
    observation_timestamp = min(latest_trade_timestamp, latest_book_timestamp)
    flow_base = pd.DataFrame({"timestamp": [observation_timestamp]})
    order_flow_analysis = build_trade_order_flow(
        flow_base,
        trades,
        baseline_window=24,
        event_window=60,
    )

    book_work = order_book.copy()
    book_work["timestamp"] = pd.to_datetime(book_work["timestamp"], unit="ms", utc=True)
    order_book_analysis = build_order_book(
        pd.DataFrame({"timestamp": book_work["timestamp"]}), order_book
    )
    cvd_analysis = build_trade_cvd(
        pd.DataFrame({"timestamp": [observation_timestamp]}), trades
    )

    if not history_work.empty:
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
        absorption_base = price_frame[["timestamp", "open", "high", "low", "close"]]
        absorption_flow = build_trade_order_flow(
            flow_base,
            trades,
            baseline_window=24,
            event_window=60,
        )
        absorption_analysis = build_absorption(
            absorption_base,
            absorption_flow,
            levels,
        )
    else:
        absorption_analysis = pd.DataFrame()

    evidence_assessment = assess_market_evidence(market_evidence)
    scenario_assessment = assess_scenarios(evidence_assessment)
    setup_assessment = analyze_setups(
        evidence_assessment,
        scenario_assessment,
        observations=evidence_assessment.observations,
        analyses=analyses,
        timeframes=timeframes,
    )
    decision_assessment = decide(
        setup_assessment,
        observations=evidence_assessment.observations,
    )

    return FindSetupResult(
        request=request,
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
        decision=decision_assessment.action.value.upper().replace("_", " "),
        reason="; ".join(decision_assessment.reasons),
    )
