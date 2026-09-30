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
from .decision import decide
from .evidence_reasoning import assess_market_evidence
from .features import build_features
from .market_data import MarketDataProvider, completed_ohlcv
from .market_evidence_adapter import build_market_evidence
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


def find_setup(
    request: FindSetupRequest,
    *,
    provider: MarketDataProvider | None = None,
    now_ms: int,
    limit: int = 1000,
    resolver: Callable[[str, str], str] | None = None,
) -> FindSetupResult:
    """Resolve the requested asset, fetch seven causal timeframes, and run AICFA."""
    provider = provider or BinanceMarketDataProvider()
    if resolver is None:
        if isinstance(provider, BinanceMarketDataProvider):
            resolver = lambda asset, market_type: provider.resolve_symbol(asset, market_type=market_type)
        else:
            resolver = lambda asset, market_type: normalize_asset(asset)
    symbol = normalize_asset(resolver(request.asset, request.market_type))
    frames: dict[str, pd.DataFrame] = {}

    for timeframe in CAUSAL_TIMEFRAMES:
        frames[timeframe] = provider.fetch_ohlcv(
            symbol=symbol,
            market_type=request.market_type,
            timeframe=timeframe,
            since_ms=None,
            limit=limit,
        )

    base = completed_ohlcv(frames["1m"], timeframe="1m", now_ms=now_ms)
    if base.empty:
        raise ValueError("no completed 1m candle available for decision")

    higher = {key: value for key, value in frames.items() if key != "1m"}
    analysis = build_features(base, multi_timeframe_frames=higher)
    if analysis.empty:
        raise ValueError("AICFA analysis produced no rows")

    market_evidence = build_market_evidence(
        analysis,
        asset=symbol,
        timeframes=CAUSAL_TIMEFRAMES,
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
        symbol=request.asset,
        timeframes=CAUSAL_TIMEFRAMES,
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
