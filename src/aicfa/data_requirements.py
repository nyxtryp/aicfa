"""Knowledge-driven, request-scoped market-data requirements.

The knowledge base describes what evidence a setup hypothesis needs. This module
turns that knowledge into a semantic collection contract. It deliberately does
not contain candle counts or exchange-specific fetching logic; those belong to
the requirement resolver/provider layer.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from .knowledge_base import KnowledgeEntry, KNOWLEDGE_BASE_V1, get_knowledge


class DataKind(str, Enum):
    OHLCV = "ohlcv"
    TRADES = "trades"
    ORDER_BOOK = "order_book"
    FUNDING = "funding"
    OPEN_INTEREST = "open_interest"
    LIQUIDATIONS = "liquidations"
    MARK_PRICE = "mark_price"


class ContextNeed(str, Enum):
    STRUCTURAL_ANCHORS = "structural_anchors"
    RECENT_EVENTS = "recent_events"
    ACTIVE_ZONES = "active_zones"
    CROSS_TIMEFRAME_CONTEXT = "cross_timeframe_context"
    CONFIRMATION_RESPONSE = "confirmation_response"
    POSITIONING_CONTEXT = "positioning_context"


class TradingMode(str, Enum):
    SCALPING = "scalping"
    INTRADAY = "intraday"
    SWING = "swing"
    POSITION = "position"


@dataclass(frozen=True)
class ModeTimeframeProfile:
    mode: TradingMode
    timeframes: tuple[str, ...]
    roles: tuple[tuple[str, "TimeframeRole"], ...]

    @property
    def context_timeframe(self) -> str:
        return self.roles[0][0]

    @property
    def structure_timeframe(self) -> str:
        return self.roles[1][0]

    @property
    def refinement_timeframe(self) -> str | None:
        return self.roles[2][0] if len(self.roles) > 2 else None

    @property
    def execution_timeframe(self) -> str:
        return self.roles[-1][0]


class TimeframeRole(str, Enum):
    EXECUTION = "execution"
    LOWER_CONFIRMATION = "lower_confirmation"
    HIGHER_STRUCTURE = "higher_structure"
    BROADER_CONTEXT = "broader_context"


@dataclass(frozen=True)
class KnowledgeRequirement:
    """Evidence requirements expressed by one knowledge concept."""

    concept_id: str
    data_kinds: frozenset[DataKind]
    context_needs: frozenset[ContextNeed]
    timeframe_roles: frozenset[TimeframeRole]


@dataclass(frozen=True)
class DataRequirementPlan:
    """Merged request-scoped requirements for one analysis request."""

    asset: str
    concepts: tuple[str, ...]
    data_kinds: frozenset[DataKind]
    context_needs: frozenset[ContextNeed]
    timeframe_roles: frozenset[TimeframeRole]
    requirements: tuple[KnowledgeRequirement, ...]
    mode: TradingMode | None = None

    def requires(self, kind: DataKind) -> bool:
        return kind in self.data_kinds

    def needs(self, context: ContextNeed) -> bool:
        return context in self.context_needs

    def needs_timeframe_role(self, role: TimeframeRole) -> bool:
        return role in self.timeframe_roles

    @property
    def required_timeframes(self) -> tuple[str, ...]:
        if self.mode is not None:
            return mode_timeframe_profile(self.mode).timeframes
        role_timeframes = {
            TimeframeRole.EXECUTION: ("1m",),
            TimeframeRole.LOWER_CONFIRMATION: ("5m", "15m"),
            TimeframeRole.HIGHER_STRUCTURE: ("1h", "4h"),
            TimeframeRole.BROADER_CONTEXT: ("1d", "1w"),
        }
        selected = {timeframe for role in self.timeframe_roles for timeframe in role_timeframes[role]}
        causal_order = ("1m", "5m", "15m", "1h", "4h", "1d", "1w")
        return tuple(timeframe for timeframe in causal_order if timeframe in selected)


_MODE_PROFILES = {
    TradingMode.SCALPING: ModeTimeframeProfile(
        TradingMode.SCALPING,
        ("1h", "15m", "5m", "1m"),
        (("1h", TimeframeRole.BROADER_CONTEXT), ("15m", TimeframeRole.HIGHER_STRUCTURE), ("5m", TimeframeRole.LOWER_CONFIRMATION), ("1m", TimeframeRole.EXECUTION)),
    ),
    TradingMode.INTRADAY: ModeTimeframeProfile(
        TradingMode.INTRADAY,
        ("4h", "1h", "5m", "15m"),
        (("4h", TimeframeRole.BROADER_CONTEXT), ("1h", TimeframeRole.HIGHER_STRUCTURE), ("5m", TimeframeRole.LOWER_CONFIRMATION), ("15m", TimeframeRole.EXECUTION)),
    ),
    TradingMode.SWING: ModeTimeframeProfile(
        TradingMode.SWING,
        ("1d", "4h", "1h"),
        (("1d", TimeframeRole.BROADER_CONTEXT), ("4h", TimeframeRole.HIGHER_STRUCTURE), ("1h", TimeframeRole.EXECUTION)),
    ),
    TradingMode.POSITION: ModeTimeframeProfile(
        TradingMode.POSITION,
        ("1w", "1d", "4h"),
        (("1w", TimeframeRole.BROADER_CONTEXT), ("1d", TimeframeRole.HIGHER_STRUCTURE), ("4h", TimeframeRole.EXECUTION)),
    ),
}


def normalize_trading_mode(mode: TradingMode | str) -> TradingMode:
    if isinstance(mode, TradingMode):
        return mode
    try:
        return TradingMode(str(mode).strip().lower())
    except ValueError as exc:
        raise ValueError("mode must be scalping, intraday, swing, or position") from exc


def mode_timeframe_profile(mode: TradingMode | str) -> ModeTimeframeProfile:
    return _MODE_PROFILES[normalize_trading_mode(mode)]


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _knowledge_requirement(entry: KnowledgeEntry) -> KnowledgeRequirement:
    """Derive collection needs from observable evidence and relationships."""
    evidence = set(entry.observable_evidence)
    relationships = set(entry.relationships)

    data_kinds = {DataKind.OHLCV}
    context_needs = {
        ContextNeed.STRUCTURAL_ANCHORS,
        ContextNeed.RECENT_EVENTS,
    }
    timeframe_roles = {
        TimeframeRole.EXECUTION,
        TimeframeRole.HIGHER_STRUCTURE,
    }

    if entry.domain == "microstructure":
        if "trades" in evidence or "aggressor side" in evidence or "signed volume" in evidence:
            data_kinds.add(DataKind.TRADES)
        if "order book" in evidence or "best bid/ask" in evidence:
            data_kinds.add(DataKind.ORDER_BOOK)

    if entry.domain == "derivatives" or "funding" in relationships or "liquidations" in relationships:
        data_kinds.update({
            DataKind.FUNDING,
            DataKind.OPEN_INTEREST,
            DataKind.LIQUIDATIONS,
            DataKind.MARK_PRICE,
        })
        context_needs.add(ContextNeed.POSITIONING_CONTEXT)

    if entry.domain in {"liquidity", "imbalance", "order_block", "premium_discount", "price_action"}:
        context_needs.add(ContextNeed.ACTIVE_ZONES)

    if entry.domain in {"market_structure", "liquidity", "wyckoff"}:
        context_needs.add(ContextNeed.CROSS_TIMEFRAME_CONTEXT)
        timeframe_roles.add(TimeframeRole.BROADER_CONTEXT)

    if entry.domain in {"price_action", "liquidity"}:
        context_needs.add(ContextNeed.CONFIRMATION_RESPONSE)
        timeframe_roles.add(TimeframeRole.LOWER_CONFIRMATION)

    if {"volume", "trades", "order_flow"} & evidence:
        data_kinds.add(DataKind.TRADES)

    if {"order_book", "book", "microstructure"} & evidence:
        data_kinds.add(DataKind.ORDER_BOOK)

    if {"funding", "open interest", "liquidations", "mark price"} & evidence:
        data_kinds.update({
            DataKind.FUNDING,
            DataKind.OPEN_INTEREST,
            DataKind.LIQUIDATIONS,
            DataKind.MARK_PRICE,
        })
        context_needs.add(ContextNeed.POSITIONING_CONTEXT)

    return KnowledgeRequirement(
        concept_id=entry.id,
        data_kinds=frozenset(data_kinds),
        context_needs=frozenset(context_needs),
        timeframe_roles=frozenset(timeframe_roles),
    )


_REQUIREMENTS_BY_CONCEPT = {
    entry.id: _knowledge_requirement(entry) for entry in KNOWLEDGE_BASE_V1
}


def requirements_for_concepts(
    asset: str,
    concepts: Iterable[str],
    *,
    mode: TradingMode | str | None = None
) -> DataRequirementPlan:
    """Build a request-scoped plan from explicit knowledge concepts.

    Unknown concepts are rejected rather than silently producing an incomplete
    collection plan. No market data is fetched or retained here.
    """
    normalized = _unique(concept.strip() for concept in concepts if concept.strip())
    if not normalized:
        raise ValueError("at least one knowledge concept is required")
    requirements: list[KnowledgeRequirement] = []
    for concept in normalized:
        get_knowledge(concept)
        requirements.append(_REQUIREMENTS_BY_CONCEPT[concept])

    data_kinds = frozenset().union(*(item.data_kinds for item in requirements))
    context_needs = frozenset().union(*(item.context_needs for item in requirements))
    timeframe_roles = frozenset().union(*(item.timeframe_roles for item in requirements))

    return DataRequirementPlan(
        asset=asset.strip(),
        concepts=normalized,
        data_kinds=data_kinds,
        context_needs=context_needs,
        timeframe_roles=timeframe_roles,
        requirements=tuple(requirements),
        mode=None if mode is None else normalize_trading_mode(mode),
    )


def default_setup_requirements(
    asset: str,
    *,
    mode: TradingMode | str | None = None,
) -> DataRequirementPlan:
    """Return the knowledge-driven baseline for an unconstrained setup search.

    This is a concept set, not a fixed candle-depth recipe. Additional
    hypotheses may expand it before collection begins.
    """
    return requirements_for_concepts(
        asset,
        (
            "market_structure.bos",
            "market_structure.choch",
            "liquidity.sweep",
            "imbalance.fvg",
            "order_block.bullish",
            "premium_discount.dealing_range",
            "price_action.rejection",
            "wyckoff.spring",
        ),
        mode=mode,
    )
