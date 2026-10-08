"""Deterministic multi-timeframe SETUP ENGINE for AICFA.

The engine consumes the complete current seven-timeframe market context:
1w -> 1d -> 4h -> 1h -> 15m -> 5m -> 1m.

Higher timeframes establish structure; lower timeframes confirm and execute.
The 1m timeframe is never sufficient to establish setup direction or levels.
No future data, scores, probabilities, order execution, or fabricated prices.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping

import pandas as pd

from aicfa.evidence_reasoning import EvidenceAssessment, EvidenceDecision
from aicfa.data_requirements import TradingMode, mode_timeframe_profile, normalize_trading_mode
from aicfa.knowledge_base import get_knowledge
from aicfa.market_evidence import MarketObservation
from aicfa.scenario_reasoning import ScenarioAssessment, ScenarioHypothesis
from aicfa.visual_evidence import VisualObservation

SETUP_TIMEFRAMES = ("1m", "5m", "15m", "1h", "4h", "1d", "1w")

_TIMEFRAME_MS = {
    "1m": 60_000,
    "5m": 5 * 60_000,
    "15m": 15 * 60_000,
    "1h": 60 * 60_000,
    "4h": 4 * 60 * 60_000,
    "1d": 24 * 60 * 60_000,
    "1w": 7 * 24 * 60 * 60_000,
}
_MAX_INVALIDATION_AGE_CANDLES = 12


def _timestamp_ms(value: object) -> int | None:
    try:
        if isinstance(value, pd.Timestamp):
            return int(value.value // 1_000_000)
        numeric = float(value)
        if abs(numeric) >= 1e11:
            return int(numeric)
        return int(numeric * 1000)
    except (TypeError, ValueError, OverflowError):
        try:
            return int(pd.Timestamp(value).value // 1_000_000)
        except (TypeError, ValueError, OverflowError):
            return None


def _row_timestamp_ms(row: pd.Series) -> int | None:
    if "timestamp" in row.index:
        return _timestamp_ms(row.get("timestamp"))
    return _timestamp_ms(row.name)
_HIGHER_STRUCTURE = ("1w", "1d", "4h", "1h")
_CONFIRMATION = ("15m", "5m")
_EXECUTION = ("1m",)

_ZONE_CONCEPTS = {
    "imbalance.fvg",
    "order_block.bullish",
    "order_block.bearish",
    "liquidity.sweep",
    "price_action.rejection",
    "premium_discount.dealing_range",
}
_STRUCTURAL_CONCEPTS = {
    "market_structure.bos",
    "market_structure.choch",
    "displacement",
    "liquidity.sweep",
}
_DIRECTIONAL_CONCEPTS = _STRUCTURAL_CONCEPTS | {
    "order_block.bullish",
    "order_block.bearish",
    "imbalance.fvg",
}


class SetupDecision(str, Enum):
    READY = "ready"
    NEED_MORE_EVIDENCE = "need_more_evidence"
    WAIT = "wait"


@dataclass(frozen=True)
class SetupLevel:
    value: float
    timeframe: str
    source: str


@dataclass(frozen=True)
class MultiTimeframeContext:
    timeframes: tuple[str, ...]
    mode: TradingMode
    latest_rows: Mapping[str, pd.Series]
    observations: tuple[MarketObservation, ...]
    missing_timeframes: tuple[str, ...] = ()
    structure_direction: str | None = None
    structure_timeframe: str = ""
    confirmation_directions: tuple[str, ...] = ()
    context_timeframe: str = ""
    refinement_timeframe: str | None = None
    execution_timeframe: str = ""


@dataclass(frozen=True)
class SetupCandidate:
    scenario: str
    supporting_concepts: tuple[str, ...]
    zone_concepts: tuple[str, ...]
    zone_locations: tuple[str, ...]
    entry_condition: tuple[str, ...]
    invalidation: tuple[str, ...]
    targets: tuple[str, ...]
    rationale: tuple[str, ...]
    direction: str | None = None
    entry_zone: tuple[SetupLevel, ...] = ()
    invalidation_level: SetupLevel | None = None
    target_levels: tuple[SetupLevel, ...] = ()
    confirmation_timeframes: tuple[str, ...] = ()
    source_timeframes: tuple[str, ...] = ()


@dataclass(frozen=True)
class SetupAssessment:
    decision: SetupDecision
    candidates: tuple[SetupCandidate, ...]
    missing_context: tuple[str, ...]
    conflicts: tuple[str, ...]
    reasons: tuple[str, ...]


def _unique(values: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))


def _observed(observations: tuple) -> tuple:
    return tuple(
        item for item in observations
        if item.state == "observed" and item.confidence >= 0.5
    )


def _latest_rows(analyses: Mapping[str, pd.DataFrame]) -> dict[str, pd.Series]:
    rows: dict[str, pd.Series] = {}
    for timeframe, frame in analyses.items():
        if frame is None or frame.empty or "timestamp" not in frame.columns:
            continue
        ordered = frame.sort_values("timestamp").drop_duplicates("timestamp")
        if not ordered.empty:
            rows[timeframe] = ordered.iloc[-1]
    return rows


def _structure_direction(row: pd.Series) -> int:
    for column in ("smc_structure_direction", "structure_direction"):
        if column in row.index:
            try:
                value = float(row[column])
            except (TypeError, ValueError):
                continue
            if value in (-1.0, 1.0):
                return int(value)
    return 0


def _structure_states(context: MultiTimeframeContext) -> tuple[str, ...]:
    states: list[str] = []
    seen: set[str] = set()
    for timeframe in (
        context.context_timeframe,
        context.structure_timeframe,
        context.refinement_timeframe,
        context.execution_timeframe,
    ):
        if not timeframe or timeframe in seen:
            continue
        seen.add(timeframe)
        row = context.latest_rows.get(timeframe)
        if row is None:
            continue
        value = _structure_direction(row)
        if value:
            states.append(f"{timeframe} structure={'long' if value > 0 else 'short'}")
    return tuple(states)


def _event_direction_conflict(
    context: MultiTimeframeContext,
    *,
    scenario: str,
    direction: str,
    observations: tuple[MarketObservation, ...],
) -> str | None:
    """Validate causal event direction without breaking valid reversal/failure paths.

    Event direction is scenario-specific:
    - continuation: BOS/displacement must support the active structural leg;
    - reversal: CHoCH/MSS must support the new leg and the sweep must be aligned;
    - breakout failure: the post-sweep structural break/rejection must support
      the failure direction.
    A counter-direction event is not automatically a contradiction: for a
    reversal it can be the very event that creates the new direction.
    """
    relevant = {
        tf for tf in (
            context.context_timeframe,
            context.structure_timeframe,
            context.refinement_timeframe,
        ) if tf
    }
    items = [item for item in _observed(observations) if item.timeframe in relevant]

    def wrong(item: MarketObservation) -> str | None:
        if item.direction not in {"long", "short"} or item.direction == direction:
            return None
        return (
            f"{item.timeframe} {item.concept_id}={item.direction} "
            f"conflicts with {direction} {scenario}"
        )

    if scenario == "continuation":
        for item in items:
            if item.concept_id in {"market_structure.bos", "market_structure.mss", "market_structure.choch"}:
                conflict = wrong(item)
                if conflict:
                    return conflict
        return None

    if scenario == "reversal":
        transition = [
            item for item in items
            if item.concept_id in {"market_structure.choch", "market_structure.mss"}
        ]
        if not any(item.direction == direction for item in transition):
            return f"{direction} reversal lacks a same-direction CHoCH/MSS"
        for item in transition:
            conflict = wrong(item)
            if conflict:
                return conflict
        sweeps = [item for item in items if item.concept_id == "liquidity.sweep"]
        if not any(item.direction == direction for item in sweeps):
            return f"{direction} reversal lacks a same-direction liquidity sweep"
        return None

    if scenario == "breakout_failure":
        sweeps = [item for item in items if item.concept_id == "liquidity.sweep"]
        if not any(item.direction == direction for item in sweeps):
            return f"{direction} breakout failure lacks a same-direction liquidity sweep"
        structural = [
            item for item in items
            if item.concept_id in {"market_structure.bos", "market_structure.choch", "market_structure.mss"}
        ]
        if structural and not any(item.direction == direction for item in structural):
            return f"{direction} breakout failure lacks same-direction structural confirmation"
        for item in structural:
            if item.direction == direction:
                continue
            # A prior opposite BOS can describe the failed breakout itself; it
            # is not a contradiction. Only an opposite final transition blocks.
            if item.concept_id in {"market_structure.choch", "market_structure.mss"}:
                return wrong(item)
        return None

    return None


def build_multi_timeframe_context(
    observations: tuple[MarketObservation, ...],
    analyses: Mapping[str, pd.DataFrame],
    *,
    timeframes: tuple[str, ...] = SETUP_TIMEFRAMES,
    mode: TradingMode | str = TradingMode.INTRADAY,
) -> MultiTimeframeContext:
    """Build current state using only the selected mode hierarchy."""
    normalized_mode = normalize_trading_mode(mode)
    profile = mode_timeframe_profile(normalized_mode)
    rows = _latest_rows(analyses)
    missing = tuple(tf for tf in timeframes if tf not in rows)

    structure_timeframe = profile.structure_timeframe
    structure_direction = None
    row = rows.get(structure_timeframe)
    if row is not None:
        direction = _structure_direction(row)
        if direction:
            structure_direction = "long" if direction > 0 else "short"

    confirmations: list[str] = []
    refinement = profile.refinement_timeframe
    if refinement is not None:
        row = rows.get(refinement)
        if row is not None:
            direction = _structure_direction(row)
            if direction:
                confirmations.append("long" if direction > 0 else "short")

    return MultiTimeframeContext(
        timeframes=timeframes,
        mode=normalized_mode,
        latest_rows=rows,
        observations=observations,
        missing_timeframes=missing,
        structure_direction=structure_direction,
        structure_timeframe=structure_timeframe,
        confirmation_directions=tuple(confirmations),
        context_timeframe=profile.context_timeframe,
        refinement_timeframe=refinement,
        execution_timeframe=profile.execution_timeframe,
    )

def _zone_data(observations: tuple) -> tuple[tuple[str, ...], tuple[str, ...]]:
    concepts: list[str] = []
    locations: list[str] = []
    for item in _observed(observations):
        if item.concept_id not in _ZONE_CONCEPTS:
            continue
        concepts.append(item.concept_id)
        if item.price_location:
            locations.append(f"{item.concept_id}: {item.price_location}")
    return _unique(concepts), _unique(locations)


def _knowledge_requirements(concepts: tuple[str, ...]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    confirmations: list[str] = []
    invalidations: list[str] = []
    for concept in concepts:
        try:
            entry = get_knowledge(concept)
        except KeyError:
            continue
        confirmations.extend(entry.confirmations)
        invalidations.extend(entry.invalidations)
    return _unique(confirmations), _unique(invalidations)


def _entry_confirmation_conditions(
    scenario: str,
    supporting: tuple[str, ...],
    direction: str,
    structure_timeframe: str,
    observations: tuple[MarketObservation, ...],
) -> tuple[str, ...]:
    """Describe the causal confirmation required at the selected zone."""
    conditions = [
        f"zone reaction/confirmation is required before {direction} entry",
        f"entry direction confirmed by {structure_timeframe} structure",
    ]
    if "market_structure.bos" in supporting:
        conditions.append("confirmed BOS with follow-through")
    if "market_structure.choch" in supporting:
        conditions.append("confirmed CHoCH with follow-through")
    if "displacement" in supporting:
        conditions.append("displacement confirms repricing from the zone")
    if "liquidity.sweep" in supporting:
        conditions.append("liquidity sweep must show rejection or displacement away")
    if "price_action.rejection" in supporting:
        conditions.append("price rejection must occur at meaningful structural context")
    if any(item.concept_id.startswith("volume") and item.state == "observed" for item in observations):
        conditions.append("volume evidence may confirm the reaction but cannot create the entry level")
    return _unique(conditions)


def _targets(hypothesis: ScenarioHypothesis) -> tuple[str, ...]:
    if hypothesis.scenario == "range":
        return ("opposing visible range boundary or opposing liquidity, if present",)
    if hypothesis.scenario == "breakout_failure":
        return ("opposing visible liquidity or structural extreme, if present",)
    if hypothesis.scenario == "reversal":
        return ("next visible opposing liquidity or structural extreme, if present",)
    return ("next visible opposing liquidity or structural objective, if present",)


def _numeric(row: pd.Series, column: str) -> float | None:
    if column not in row.index:
        return None
    value = pd.to_numeric(pd.Series([row[column]]), errors="coerce").iloc[0]
    return None if pd.isna(value) else float(value)


def _ordered_source_timeframes(
    context: MultiTimeframeContext,
    concepts: tuple[str, ...] = (),
    preferred_timeframes: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """Prefer explicit supporting timeframes, then observed evidence timeframes."""
    ordered = [tf for tf in preferred_timeframes if tf in context.latest_rows]
    observed = {
        item.timeframe
        for item in context.observations
        if item.concept_id in concepts and getattr(item, "timeframe", None)
    }
    ordered.extend(tf for tf in context.timeframes if tf in observed and tf not in ordered)
    ordered.extend(tf for tf in reversed(context.timeframes) if tf not in ordered)
    return tuple(ordered)


def _zone_levels(
    context: MultiTimeframeContext,
    direction: str,
    concepts: tuple[str, ...],
    current_price: float | None,
) -> tuple[SetupLevel, ...]:
    """Select one actionable zone, honoring scenario concept priority."""
    definitions = {
        "imbalance.fvg": (
            "fvg_bullish_low" if direction == "long" else "fvg_bearish_low",
            "fvg_bullish_high" if direction == "long" else "fvg_bearish_high",
            "active bullish FVG" if direction == "long" else "active bearish FVG",
        ),
        "order_block.bullish" if direction == "long" else "order_block.bearish": (
            "order_block_bullish_low" if direction == "long" else "order_block_bearish_low",
            "order_block_bullish_high" if direction == "long" else "order_block_bearish_high",
            "active bullish OB" if direction == "long" else "active bearish OB",
        ),
    }

    zones: list[tuple[float, float, str, str]] = []
    ordered_timeframes = _ordered_source_timeframes(context, concepts)

    for concept in concepts:
        definition = definitions.get(concept)
        if definition is None:
            continue
        low_col, high_col, source = definition
        concept_zones: list[tuple[float, float, str, str]] = []
        for timeframe in ordered_timeframes:
            # 1m is execution/microstructure only. It may confirm an entry,
            # but it must never manufacture the setup zone itself.
            if timeframe == context.execution_timeframe:
                continue
            row = context.latest_rows.get(timeframe)
            if row is None:
                continue
            low = _numeric(row, low_col)
            high = _numeric(row, high_col)
            if low is None or high is None or low > high or low <= 0 or high <= 0:
                continue
            if current_price is not None:
                if direction == "long" and low >= current_price:
                    continue
                if direction == "short" and high <= current_price:
                    continue
            concept_zones.append((low, high, timeframe, source))
        if concept_zones:
            zones = concept_zones
            break

    if not zones:
        return ()

    if current_price is None:
        low, high, timeframe, source = zones[0]
    elif direction == "long":
        containing = [zone for zone in zones if zone[0] <= current_price <= zone[1]]
        below = [zone for zone in zones if zone[1] < current_price]
        if containing:
            low, high, timeframe, source = max(containing, key=lambda zone: zone[1])
        elif below:
            low, high, timeframe, source = max(below, key=lambda zone: zone[1])
        else:
            return ()
    else:
        containing = [zone for zone in zones if zone[0] <= current_price <= zone[1]]
        above = [zone for zone in zones if zone[0] > current_price]
        if containing:
            low, high, timeframe, source = min(containing, key=lambda zone: zone[0])
        elif above:
            low, high, timeframe, source = min(above, key=lambda zone: zone[0])
        else:
            return ()

    return (
        SetupLevel(value=low, timeframe=timeframe, source=f"{source} low"),
        SetupLevel(value=high, timeframe=timeframe, source=f"{source} high"),
    )

def _scenario_zone_concepts(
    scenario: str,
    direction: str,
    available: tuple[str, ...],
) -> tuple[str, ...]:
    """Choose a scenario-specific zone family without inventing levels."""
    if scenario == "continuation":
        preferred = (
            "order_block.bullish" if direction == "long" else "order_block.bearish",
            "imbalance.fvg",
        )
    elif scenario == "reversal":
        preferred = (
            "imbalance.fvg",
            "order_block.bullish" if direction == "long" else "order_block.bearish",
        )
    elif scenario == "breakout_failure":
        preferred = (
            "order_block.bullish" if direction == "long" else "order_block.bearish",
            "imbalance.fvg",
        )
    else:
        preferred = ("imbalance.fvg",)
    selected = tuple(concept for concept in preferred if concept in available)
    return selected or available



def _invalidation_level(
    context: MultiTimeframeContext,
    direction: str,
    scenario: str,
    source_timeframes: tuple[str, ...],
    entry_zone: tuple[SetupLevel, ...],
) -> SetupLevel | None:
    if direction == "long":
        sweep_column, sweep_source = "smc_sweep_low_level", "sweep low"
        swing_column, swing_source = "previous_low", "previous low"
    else:
        sweep_column, sweep_source = "smc_sweep_high_level", "sweep high"
        swing_column, swing_source = "previous_high", "previous high"

    # Invalidation is the structural level whose violation breaks the setup
    # hypothesis. Liquidity pools are draw-on targets, not automatic stop levels.
    preferred = (
        (sweep_column, sweep_source),
        (swing_column, swing_source),
    ) if scenario in {"reversal", "breakout_failure"} else (
        (swing_column, swing_source),
        (sweep_column, sweep_source),
    )

    if len(entry_zone) < 2:
        return None
    entry_low = min(level.value for level in entry_zone)
    entry_high = max(level.value for level in entry_zone)
    candidates: list[SetupLevel] = []

    # Invalidation must come from the mode's active structural hierarchy.
    # A current Intraday setup may not borrow a weeks-old 1D/1W swing merely
    # because that level is present in the broader evidence set.
    profile_timeframes = {
        context.context_timeframe,
        context.structure_timeframe,
    }
    allowed = tuple(
        tf for tf in context.timeframes
        if tf != context.execution_timeframe and tf in profile_timeframes
    )
    ordered_timeframes = tuple(
        tf for tf in source_timeframes if tf in allowed
    ) + tuple(
        tf for tf in allowed if tf not in source_timeframes
    )
    for timeframe in ordered_timeframes:
        row = context.latest_rows.get(timeframe)
        if row is None:
            continue
        row_ts = _row_timestamp_ms(row)
        execution_row = context.latest_rows.get(context.execution_timeframe)
        execution_ts = _row_timestamp_ms(execution_row) if execution_row is not None else None
        max_age = _TIMEFRAME_MS.get(timeframe, 0) * _MAX_INVALIDATION_AGE_CANDLES
        if row_ts is None or execution_ts is None or max_age <= 0 or execution_ts - row_ts > max_age:
            continue
        for column, source in preferred:
            value = _numeric(row, column)
            if value is None or value <= 0:
                continue
            if direction == "long" and value < entry_low:
                candidates.append(SetupLevel(value=value, timeframe=timeframe, source=source))
            elif direction == "short" and value > entry_high:
                candidates.append(SetupLevel(value=value, timeframe=timeframe, source=source))

    if not candidates:
        return None

    # Pick the nearest valid level from the preferred structural family.
    if direction == "long":
        return max(candidates, key=lambda level: level.value)
    return min(candidates, key=lambda level: level.value)


def _scenario_requirements(scenario: str) -> tuple[str, ...]:
    return {
        "continuation": ("market_structure.bos", "displacement"),
        # Reversal accepts either CHoCH or MSS as the structural transition.
        # The actual direction/sweep relationship is validated separately.
        "reversal": ("liquidity.sweep",),
        "breakout_failure": (
            "liquidity.sweep",
            "price_action.rejection",
        ),
    }.get(scenario, ())


def _scenario_requirements_met(
    scenario: str,
    supporting: tuple[str, ...],
) -> bool:
    concepts = set(supporting)
    if scenario == "reversal":
        return (
            "liquidity.sweep" in concepts
            and (
                "market_structure.choch" in concepts
                or "market_structure.mss" in concepts
            )
        )
    if scenario == "breakout_failure":
        return (
            "liquidity.sweep" in concepts
            and "price_action.rejection" in concepts
            and bool(
                concepts
                & {
                    "market_structure.bos",
                    "market_structure.choch",
                    "market_structure.mss",
                }
            )
        )
    return _scenario_has_required_evidence(scenario, supporting)


def _scenario_has_required_evidence(
    scenario: str,
    supporting: tuple[str, ...],
) -> bool:
    required = _scenario_requirements(scenario)
    return not required or all(concept in supporting for concept in required)


def _actionable_geometry_key(candidate: SetupCandidate) -> tuple:
    """Identify duplicate trade geometry without ranking different hypotheses."""
    return (
        candidate.direction,
        tuple((level.value, level.timeframe, level.source) for level in candidate.entry_zone),
        None if candidate.invalidation_level is None else (
            candidate.invalidation_level.value,
            candidate.invalidation_level.timeframe,
            candidate.invalidation_level.source,
        ),
        tuple((level.value, level.timeframe, level.source) for level in candidate.target_levels),
    )


def _risk_reward_value(
    direction: str,
    entry_zone: tuple[SetupLevel, ...],
    invalidation: SetupLevel | None,
    targets: tuple[SetupLevel, ...],
) -> float | None:
    if len(entry_zone) < 2 or invalidation is None or not targets:
        return None
    entry_low = min(level.value for level in entry_zone)
    entry_high = max(level.value for level in entry_zone)
    if direction == "long":
        risk = entry_low - invalidation.value
        reward = targets[0].value - entry_high
    else:
        risk = invalidation.value - entry_high
        reward = entry_low - targets[0].value
    if risk <= 0 or reward <= 0:
        return None
    return reward / risk


def _risk_reward_is_valid(
    direction: str,
    entry_zone: tuple[SetupLevel, ...],
    invalidation: SetupLevel | None,
    targets: tuple[SetupLevel, ...],
    *,
    minimum_rr: float = 2.0,
) -> bool:
    rr = _risk_reward_value(direction, entry_zone, invalidation, targets)
    return rr is not None and rr >= minimum_rr


def _target_levels(
    context: MultiTimeframeContext,
    direction: str,
    current_price: float | None,
    preferred_timeframes: tuple[str, ...] = (),
    entry_timeframe: str | None = None,
    entry_zone: tuple[SetupLevel, ...] = (),
) -> tuple[SetupLevel, ...]:
    # A target is the next causal draw-on-liquidity/objective, not an arbitrary
    # number above/below price. The hierarchy follows the market-delivery logic:
    # active liquidity first, then breakout objective, then confirmed structural
    # extremes, then causal range extremes.
    columns = (
        ("active_buy_liquidity_price", "active buy-side liquidity"),
        ("liquidity_breakout_high", "liquidity breakout high"),
        ("previous_high", "previous high"),
        ("internal_previous_high", "internal previous high"),
        ("rolling_high_60", "causal rolling high"),
    ) if direction == "long" else (
        ("active_sell_liquidity_price", "active sell-side liquidity"),
        ("liquidity_breakout_low", "liquidity breakout low"),
        ("previous_low", "previous low"),
        ("internal_previous_low", "internal previous low"),
        ("rolling_low_60", "causal rolling low"),
    )

    # Target discovery is independent of the entry zone timeframe.
    # A setup may draw liquidity/objectives from any relevant MTF layer;
    # only the 1m execution layer must never manufacture the setup objective.
    allowed = tuple(tf for tf in context.timeframes if tf != context.execution_timeframe)

    ordered = tuple(
        tf for tf in preferred_timeframes if tf in allowed
    ) + tuple(tf for tf in allowed if tf not in preferred_timeframes)

    candidates: list[tuple[int, float, int, str, str, float]] = []
    for source_priority, (column, source) in enumerate(columns):
        for timeframe in ordered:
            row = context.latest_rows.get(timeframe)
            if row is None:
                continue
            value = _numeric(row, column)
            if value is None or value <= 0:
                continue
            if current_price is not None:
                if direction == "long" and value <= current_price:
                    continue
                if direction == "short" and value >= current_price:
                    continue
            # A target must be outside the entire entry zone, not merely
            # beyond the current price. This matters when price is still
            # inside the POI: otherwise TP1 can be placed inside the entry
            # zone and the setup geometry becomes internally contradictory.
            if entry_zone:
                entry_low = min(level.value for level in entry_zone)
                entry_high = max(level.value for level in entry_zone)
                if direction == "long" and value <= entry_high:
                    continue
                if direction == "short" and value >= entry_low:
                    continue
            distance = (
                abs(value - current_price) if current_price is not None else 0.0
            )
            candidates.append((
                source_priority,
                distance,
                -context.timeframes.index(timeframe),
                timeframe,
                source,
                value,
            ))

    if not candidates:
        return ()

    # First target = the nearest valid objective within the highest available
    # objective class. This prevents a random nearby swing from outranking an
    # actual active liquidity draw.
    candidates.sort(key=lambda item: item[:3])
    first = candidates[0]
    result = [
        SetupLevel(value=first[5], timeframe=first[3], source=first[4])
    ]

    # Second target = next distinct objective above/below T1, preferably from
    # the same or a higher objective class. Never duplicate the first level.
    first_value = first[5]
    for candidate in candidates[1:]:
        value = candidate[5]
        if value == first_value:
            continue
        if direction == "long" and value <= first_value:
            continue
        if direction == "short" and value >= first_value:
            continue
        result.append(
            SetupLevel(value=value, timeframe=candidate[3], source=candidate[4])
        )
        break

    return tuple(result)



def _resolve_direction(
    context: MultiTimeframeContext,
    *,
    scenario: str | None = None,
    supporting: tuple[str, ...] = (),
) -> tuple[str | None, str | None]:
    """Resolve direction from the MTF structural hierarchy."""
    if context.structure_direction is None:
        return None, None
    direction = context.structure_direction

    # Report the most specific direct contradiction first. This preserves the
    # actual lower-timeframe confirmation conflict when both MTF checks disagree.
    confirmations = set(context.confirmation_directions)
    if confirmations and direction not in confirmations:
        return None, "lower confirmation conflicts with higher-timeframe structure"

    broader_row = context.latest_rows.get(context.context_timeframe)
    if broader_row is not None:
        broader_value = _structure_direction(broader_row)
        if broader_value:
            broader_direction = "long" if broader_value > 0 else "short"
            if broader_direction != direction:
                reversal_confirmed = (
                    scenario == "reversal"
                    and (
                        "market_structure.choch" in supporting
                        or "market_structure.mss" in supporting
                    )
                    and "liquidity.sweep" in supporting
                )
                failure_confirmed = (
                    scenario == "breakout_failure"
                    and "liquidity.sweep" in supporting
                    and "price_action.rejection" in supporting
                )
                if not reversal_confirmed and not failure_confirmed:
                    return None, "broader higher-timeframe structure conflicts with setup direction"
    return direction, None


def analyze_setups(
    evidence_assessment: EvidenceAssessment,
    scenario_assessment: ScenarioAssessment,
    *,
    observations: tuple[MarketObservation, ...] | None = None,
    analyses: Mapping[str, pd.DataFrame] | None = None,
    timeframes: tuple[str, ...] = SETUP_TIMEFRAMES,
    mode: TradingMode | str = TradingMode.INTRADAY,
) -> SetupAssessment:
    """Run setup analysis over the complete current multi-timeframe state."""
    if evidence_assessment.decision is EvidenceDecision.WAIT:
        return SetupAssessment(
            decision=SetupDecision.WAIT,
            candidates=(),
            missing_context=evidence_assessment.missing_context,
            conflicts=evidence_assessment.conflicts,
            reasons=evidence_assessment.reasons or ("evidence contains material contradictions",),
        )

    if evidence_assessment.decision is not EvidenceDecision.PROCEED:
        return SetupAssessment(
            decision=SetupDecision.NEED_MORE_EVIDENCE,
            candidates=(),
            missing_context=evidence_assessment.missing_context,
            conflicts=evidence_assessment.conflicts,
            reasons=evidence_assessment.reasons or ("evidence is not sufficient for setup analysis",),
        )

    if scenario_assessment.decision is EvidenceDecision.WAIT:
        return SetupAssessment(
            decision=SetupDecision.WAIT,
            candidates=(),
            missing_context=evidence_assessment.missing_context,
            conflicts=evidence_assessment.conflicts,
            reasons=scenario_assessment.reasons or ("scenario reasoning requires WAIT",),
        )

    if scenario_assessment.decision is not EvidenceDecision.PROCEED:
        return SetupAssessment(
            decision=SetupDecision.NEED_MORE_EVIDENCE,
            candidates=(),
            missing_context=evidence_assessment.missing_context,
            conflicts=evidence_assessment.conflicts,
            reasons=scenario_assessment.reasons or ("no sufficiently supported scenario exists",),
        )

    evidence_observations = observations or evidence_assessment.observations
    legacy_mode = analyses is None
    context = build_multi_timeframe_context(
        evidence_observations,
        analyses or {},
        timeframes=timeframes,
        mode=mode,
    ) if not legacy_mode else None
    if not legacy_mode and context.missing_timeframes:
        return SetupAssessment(
            decision=SetupDecision.NEED_MORE_EVIDENCE,
            candidates=(),
            missing_context=tuple(
                f"required timeframe: {tf}" for tf in context.missing_timeframes
            ),
            conflicts=evidence_assessment.conflicts,
            reasons=(f"complete {context.mode.value} timeframe state is required",),
        )

    if not legacy_mode and context.structure_direction is None:
        return SetupAssessment(
            decision=SetupDecision.NEED_MORE_EVIDENCE,
            candidates=(),
            missing_context=("higher-timeframe structural direction is not established",),
            conflicts=evidence_assessment.conflicts,
            reasons=("setup direction cannot be established without higher-timeframe structure",),
        )

    zones, locations = _zone_data(evidence_observations)
    candidates: list[SetupCandidate] = []
    missing: list[str] = []
    direction_conflicts: list[str] = []
    directional_observations = {
        item.timeframe: item.direction
        for item in _observed(evidence_observations)
        if item.direction in {"long", "short"} and item.concept_id in _DIRECTIONAL_CONCEPTS
    }

    for hypothesis in scenario_assessment.hypotheses:
        observed_items = _observed(evidence_observations)
        observed_concepts = {item.concept_id for item in observed_items}
        supporting = tuple(
            concept for concept in hypothesis.supporting_concepts
            if concept in observed_concepts
        )

        if len(supporting) < 2:
            missing.append(f"{hypothesis.scenario}: at least two independent supporting concepts are required")
            continue
        if not legacy_mode and not _scenario_requirements_met(hypothesis.scenario, supporting):
            missing.append(f"{hypothesis.scenario}: required scenario evidence is incomplete")
            continue
        if not zones:
            missing.append(f"{hypothesis.scenario}: no contextual setup zone is visible")
            continue

        direction, direction_conflict = (
            (None, None)
            if legacy_mode
            else _resolve_direction(
                context,
                scenario=hypothesis.scenario,
                supporting=supporting,
            )
        )
        if direction_conflict:
            direction_conflicts.append(direction_conflict)
            continue
        if direction is None and not legacy_mode:
            missing.append(f"{hypothesis.scenario}: setup direction is not structurally established")
            continue

        if not legacy_mode:
            event_conflict = _event_direction_conflict(
                context,
                scenario=hypothesis.scenario,
                direction=direction,
                observations=evidence_observations,
            )
            if event_conflict:
                direction_conflicts.append(event_conflict)
                continue

        # Keep directional rationale/evidence coherent: an opposite-side
        # order block must not be presented as support for the resolved trade.
        if direction == "long":
            supporting = tuple(concept for concept in supporting if concept != "order_block.bearish")
        elif direction == "short":
            supporting = tuple(concept for concept in supporting if concept != "order_block.bullish")

        confirmations, invalidations = _knowledge_requirements(supporting)
        source_tfs = _unique([
            item.timeframe
            for item in _observed(evidence_observations)
            if item.concept_id in supporting
        ])
        if legacy_mode:
            entry_levels = ()
            invalidation_level = None
            target_levels = ()
            entry_conditions = _unique(list(hypothesis.confirmations) + list(confirmations))
            rationale = _unique(list(hypothesis.rationale) + [f"setup zone observed on {tf}" for tf in source_tfs])
        else:
            current_row = context.latest_rows.get(context.execution_timeframe)
            current_price = _numeric(current_row, "close") if current_row is not None else None
            scenario_zones = _scenario_zone_concepts(
                hypothesis.scenario,
                direction,
                zones,
            )
            entry_levels = _zone_levels(context, direction, scenario_zones, current_price)
            invalidation_level = _invalidation_level(context, direction, hypothesis.scenario, source_tfs, entry_levels)
            entry_timeframe = entry_levels[0].timeframe if entry_levels else None
            target_levels = _target_levels(
                context,
                direction,
                current_price,
                source_tfs,
                entry_timeframe,
                entry_levels,
            )
            entry_conditions = _entry_confirmation_conditions(
                hypothesis.scenario,
                supporting,
                direction,
                context.structure_timeframe,
                evidence_observations,
            )
            rationale = _unique(
                [
                    item for item in hypothesis.rationale
                    if not (
                        direction == "long" and "order_block.bearish" in item
                    )
                    and not (
                        direction == "short" and "order_block.bullish" in item
                    )
                ]
                + [f"higher-timeframe structure: {context.structure_timeframe}={direction}"]
                + [f"setup zone observed on {tf}" for tf in source_tfs]
            )
            rationale = _unique(
                list(rationale)
                + [f"MTF hierarchy: {item}" for item in _structure_states(context)]
            )

            if not entry_levels:
                missing.append(f"{hypothesis.scenario}: no directionally valid entry zone is available")
                continue
            if invalidation_level is None:
                missing.append(f"{hypothesis.scenario}: no geometrically valid invalidation level is available")
                continue
            if not target_levels:
                missing.append(f"{hypothesis.scenario}: no geometrically valid target is available")
                continue
            # RR is derived from structural Entry/SL/TP geometry. It is
            # exposed for evaluation, but activation is decided by lifecycle:
            # the setup must actually reach the POI and satisfy the actionable
            # risk/reward policy there. This keeps structural analysis honest
            # without allowing RR to invent or distort the geometry.
            rr = _risk_reward_value(
                direction, entry_levels, invalidation_level, target_levels
            )
            if rr is not None:
                rationale = _unique(list(rationale) + [f"structural RR: {rr:.2f}R"])

        candidates.append(
            SetupCandidate(
                scenario=hypothesis.scenario,
                supporting_concepts=supporting,
                zone_concepts=scenario_zones if not legacy_mode else zones,
                zone_locations=locations,
                entry_condition=entry_conditions,
                invalidation=invalidations,
                targets=_targets(hypothesis),
                rationale=rationale,
                direction=direction,
                entry_zone=entry_levels,
                invalidation_level=invalidation_level,
                target_levels=target_levels,
                confirmation_timeframes=(() if legacy_mode else tuple(tf for tf in (context.refinement_timeframe, context.execution_timeframe) if tf is not None and tf in context.latest_rows)),
                source_timeframes=source_tfs,
            )
        )

    if not candidates:
        conflicts = _unique(list(evidence_assessment.conflicts) + direction_conflicts)
        if conflicts:
            return SetupAssessment(
                decision=SetupDecision.WAIT,
                candidates=(),
                missing_context=_unique(missing),
                conflicts=conflicts,
                reasons=("higher-timeframe structure or causal structural event conflicts with setup direction",),
            )
        return SetupAssessment(
            decision=SetupDecision.NEED_MORE_EVIDENCE,
            candidates=(),
            missing_context=_unique(missing),
            conflicts=evidence_assessment.conflicts,
            reasons=("setup conditions are not sufficiently specified",),
        )

    # Legacy/non-numeric setup analysis preserves scenario hypotheses.
    # Actionable geometry deduplication belongs only to the real MTF engine,
    # where numeric Entry/Invalidation/Target geometry exists.
    if legacy_mode:
        return SetupAssessment(
            decision=SetupDecision.READY,
            candidates=tuple(candidates),
            missing_context=_unique(missing),
            conflicts=evidence_assessment.conflicts,
            reasons=("one or more conditional setups are sufficiently specified by the current evidence",),
        )

    # Multiple MTF scenario hypotheses may describe the same actionable trade
    # geometry. Keep one setup object rather than presenting the same trade
    # twice. This does not rank scenarios: distinct geometry remains distinct,
    # while duplicate geometry is recorded as a non-actionable duplicate.
    unique_candidates: list[SetupCandidate] = []
    seen_geometry: dict[tuple, str] = {}
    for candidate in candidates:
        key = _actionable_geometry_key(candidate)
        if key in seen_geometry:
            missing.append(
                f"{candidate.scenario}: same actionable geometry as "
                f"{seen_geometry[key]}; not emitted as a separate setup"
            )
            continue
        seen_geometry[key] = candidate.scenario
        unique_candidates.append(candidate)

    return SetupAssessment(
        decision=SetupDecision.READY,
        candidates=tuple(unique_candidates),
        missing_context=_unique(missing),
        conflicts=evidence_assessment.conflicts,
        reasons=("one or more conditional setups are sufficiently specified by the current seven-timeframe state",),
    )
