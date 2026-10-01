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
) -> tuple[dict[str, pd.DataFrame], dict[str, int]]:
    """Expand unresolved context until it stops changing or data is exhausted."""
    exhausted: set[str] = set()
    current_limits = dict(limits)
    current_frames = dict(frames)
    current_missing = tuple(missing_context)
    previous_signature: tuple[object, ...] | None = None

    while True:
        unresolved = {
            item.split(":", 1)[0] for item in current_missing if ":" in item
        } - exhausted
        if not unresolved:
            return current_frames, current_limits

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

        analyses = {}
        for timeframe, frame in current_frames.items():
            completed = completed_ohlcv(
                frame, timeframe=timeframe, now_ms=now_ms,
            )
            if not completed.empty:
                analyses[timeframe] = build_features(completed)

        evidence = build_market_evidence_from_frames(
            analyses, asset=symbol, timeframes=timeframes,
        )
        signature = _context_signature(evidence)
        if signature == previous_signature:
            return current_frames, current_limits
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
    if market_evidence.missing_context:
        frames, limits = _expand_missing_context(
            provider,
            symbol=symbol,
            market_type=request.market_type,
            timeframes=timeframes,
            limits=limits,
            frames=frames,
            missing_context=market_evidence.missing_context,
            now_ms=now_ms,
        )
        completed_frames = {}
        analyses = {}
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
            analyses, asset=symbol, timeframes=timeframes,
        )
    evidence_assessment = assess_market_evidence(market_evidence)
    scenario_assessment = assess_scenarios(evidence_assessment)
    setup_assessment = analyze_setups(evidence_assessment, scenario_assessment)
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
        decision=decision_assessment.action.value.upper().replace("_", " "),
        reason="; ".join(decision_assessment.reasons),
    )
