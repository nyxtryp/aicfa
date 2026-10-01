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
from aicfa.knowledge_base import get_knowledge
from aicfa.market_evidence import MarketObservation
from aicfa.scenario_reasoning import ScenarioAssessment, ScenarioHypothesis
from aicfa.visual_evidence import VisualObservation

SETUP_TIMEFRAMES = ("1m", "5m", "15m", "1h", "4h", "1d", "1w")
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
    latest_rows: Mapping[str, pd.Series]
    observations: tuple[MarketObservation, ...]
    missing_timeframes: tuple[str, ...] = ()
    structure_direction: str | None = None
    structure_timeframe: str | None = None
    confirmation_directions: tuple[str, ...] = ()


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


def build_multi_timeframe_context(
    observations: tuple[MarketObservation, ...],
    analyses: Mapping[str, pd.DataFrame],
    *,
    timeframes: tuple[str, ...] = SETUP_TIMEFRAMES,
) -> MultiTimeframeContext:
    """Build one causal current-state object from all required timeframes."""
    rows = _latest_rows(analyses)
    missing = tuple(tf for tf in timeframes if tf not in rows)

    structure_direction = None
    structure_timeframe = None
    for timeframe in _HIGHER_STRUCTURE:
        row = rows.get(timeframe)
        if row is None:
            continue
        direction = _structure_direction(row)
        if direction:
            structure_direction = "long" if direction > 0 else "short"
            structure_timeframe = timeframe
            break

    confirmations: list[str] = []
    for timeframe in _CONFIRMATION:
        row = rows.get(timeframe)
        if row is None:
            continue
        direction = _structure_direction(row)
        if direction:
            confirmations.append("long" if direction > 0 else "short")

    return MultiTimeframeContext(
        timeframes=timeframes,
        latest_rows=rows,
        observations=observations,
        missing_timeframes=missing,
        structure_direction=structure_direction,
        structure_timeframe=structure_timeframe,
        confirmation_directions=tuple(confirmations),
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
    ordered.extend(tf for tf in SETUP_TIMEFRAMES if tf in observed and tf not in ordered)
    ordered.extend(tf for tf in SETUP_TIMEFRAMES[::-1] if tf not in ordered)
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
            if timeframe in _EXECUTION:
                continue
            row = context.latest_rows.get(timeframe)
            if row is None:
                continue
            low = _numeric(row, low_col)
            high = _numeric(row, high_col)
            if low is None or high is None or low > high:
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
        below = [zone for zone in zones if zone[1] <= current_price]
        low, high, timeframe, source = max(below, key=lambda zone: zone[1]) if below else zones[0]
    else:
        above = [zone for zone in zones if zone[0] >= current_price]
        low, high, timeframe, source = min(above, key=lambda zone: zone[0]) if above else zones[0]

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
    source_timeframes: tuple[str, ...],
    entry_zone: tuple[SetupLevel, ...],
) -> SetupLevel | None:
    columns = (
        ("smc_sweep_low_level", "sweep low"),
        ("previous_low", "previous low"),
        ("active_sell_liquidity_price", "sell-side liquidity"),
    ) if direction == "long" else (
        ("smc_sweep_high_level", "sweep high"),
        ("previous_high", "previous high"),
        ("active_buy_liquidity_price", "buy-side liquidity"),
    )
    if len(entry_zone) < 2:
        return None
    entry_low = min(level.value for level in entry_zone)
    entry_high = max(level.value for level in entry_zone)
    candidates: list[SetupLevel] = []
    # Invalidation is tied to the structural premise, not mechanically to
    # the entry zone timeframe. Inspect every non-execution structural layer.
    allowed = tuple(tf for tf in SETUP_TIMEFRAMES if tf != "1m")
    ordered_timeframes = tuple(
        tf for tf in source_timeframes if tf in allowed
    ) + tuple(
        tf for tf in allowed if tf not in source_timeframes
    )
    for timeframe in ordered_timeframes:
        row = context.latest_rows.get(timeframe)
        if row is None:
            continue
        for column, source in columns:
            value = _numeric(row, column)
            if value is None:
                continue
            if direction == "long" and value < entry_low:
                candidates.append(SetupLevel(value=value, timeframe=timeframe, source=source))
            elif direction == "short" and value > entry_high:
                candidates.append(SetupLevel(value=value, timeframe=timeframe, source=source))
    if not candidates:
        return None
    if direction == "long":
        return max(candidates, key=lambda level: level.value)
    return min(candidates, key=lambda level: level.value)


def _scenario_requirements(scenario: str) -> tuple[str, ...]:
    return {
        "continuation": ("market_structure.bos", "displacement"),
        "reversal": ("market_structure.choch", "liquidity.sweep"),
        "breakout_failure": (
            "market_structure.bos",
            "liquidity.sweep",
            "price_action.rejection",
        ),
    }.get(scenario, ())


def _scenario_has_required_evidence(
    scenario: str,
    supporting: tuple[str, ...],
) -> bool:
    required = _scenario_requirements(scenario)
    return not required or all(concept in supporting for concept in required)


def _risk_reward_is_valid(
    direction: str,
    entry_zone: tuple[SetupLevel, ...],
    invalidation: SetupLevel | None,
    targets: tuple[SetupLevel, ...],
    *,
    minimum_rr: float = 2.0,
) -> bool:
    if len(entry_zone) < 2 or invalidation is None or not targets:
        return False
    entry_low = min(level.value for level in entry_zone)
    entry_high = max(level.value for level in entry_zone)
    if direction == "long":
        risk = entry_low - invalidation.value
        reward = targets[0].value - entry_high
    else:
        risk = invalidation.value - entry_high
        reward = entry_low - targets[0].value
    if risk <= 0 or reward <= 0:
        return False
    return reward / risk >= minimum_rr


def _target_levels(
    context: MultiTimeframeContext,
    direction: str,
    current_price: float | None,
    preferred_timeframes: tuple[str, ...] = (),
    entry_timeframe: str | None = None,
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
    allowed = tuple(tf for tf in SETUP_TIMEFRAMES if tf != "1m")

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
            if value is None:
                continue
            if current_price is not None:
                if direction == "long" and value <= current_price:
                    continue
                if direction == "short" and value >= current_price:
                    continue
            distance = (
                abs(value - current_price) if current_price is not None else 0.0
            )
            candidates.append((
                source_priority,
                distance,
                -SETUP_TIMEFRAMES.index(timeframe),
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



def _resolve_direction(context: MultiTimeframeContext) -> tuple[str | None, str | None]:
    """Resolve direction from higher-timeframe structure, never from 1m alone."""
    if context.structure_direction is None:
        return None, None
    confirmations = set(context.confirmation_directions)
    if confirmations and context.structure_direction not in confirmations:
        return None, "lower confirmation conflicts with higher-timeframe structure"
    return context.structure_direction, None


def analyze_setups(
    evidence_assessment: EvidenceAssessment,
    scenario_assessment: ScenarioAssessment,
    *,
    observations: tuple[MarketObservation, ...] | None = None,
    analyses: Mapping[str, pd.DataFrame] | None = None,
    timeframes: tuple[str, ...] = SETUP_TIMEFRAMES,
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
    ) if not legacy_mode else None
    if not legacy_mode and context.missing_timeframes:
        return SetupAssessment(
            decision=SetupDecision.NEED_MORE_EVIDENCE,
            candidates=(),
            missing_context=tuple(
                f"required timeframe: {tf}" for tf in context.missing_timeframes
            ),
            conflicts=evidence_assessment.conflicts,
            reasons=("complete seven-timeframe current state is required",),
        )

    direction, direction_conflict = (
        (None, None) if legacy_mode else _resolve_direction(context)
    )
    if direction_conflict:
        return SetupAssessment(
            decision=SetupDecision.WAIT,
            candidates=(),
            missing_context=(),
            conflicts=evidence_assessment.conflicts + (direction_conflict,),
            reasons=("higher-timeframe structure and lower-timeframe confirmation conflict",),
        )
    if direction is None and not legacy_mode:
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
    directional_observations = {
        item.timeframe: item.direction
        for item in _observed(evidence_observations)
        if item.direction in {"long", "short"} and item.concept_id in _DIRECTIONAL_CONCEPTS
    }

    for hypothesis in scenario_assessment.hypotheses:
        supporting = tuple(
            concept for concept in hypothesis.supporting_concepts
            if concept in {item.concept_id for item in _observed(evidence_observations)}
        )
        if len(supporting) < 2:
            missing.append(f"{hypothesis.scenario}: at least two independent supporting concepts are required")
            continue
        if not _scenario_has_required_evidence(hypothesis.scenario, supporting):
            missing.append(f"{hypothesis.scenario}: required scenario evidence is incomplete")
            continue
        if not zones:
            missing.append(f"{hypothesis.scenario}: no contextual setup zone is visible")
            continue

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
            current_row = context.latest_rows.get("1m")
            current_price = _numeric(current_row, "close") if current_row is not None else None
            scenario_zones = _scenario_zone_concepts(
                hypothesis.scenario,
                direction,
                zones,
            )
            entry_levels = _zone_levels(context, direction, scenario_zones, current_price)
            invalidation_level = _invalidation_level(context, direction, source_tfs, entry_levels)
            entry_timeframe = entry_levels[0].timeframe if entry_levels else None
            target_levels = _target_levels(
                context,
                direction,
                current_price,
                source_tfs,
                entry_timeframe,
            )
            entry_conditions = _unique(
                list(hypothesis.confirmations)
                + list(confirmations)
                + [f"direction confirmed by {context.structure_timeframe} structure"]
            )
            rationale = _unique(
                list(hypothesis.rationale)
                + [f"higher-timeframe structure: {context.structure_timeframe}={direction}"]
                + [f"setup zone observed on {tf}" for tf in source_tfs]
            )
            if directional_observations:
                rationale = _unique(
                    list(rationale)
                    + [f"{tf} directional evidence={side}" for tf, side in directional_observations.items()]
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
            if not _risk_reward_is_valid(
                direction, entry_levels, invalidation_level, target_levels
            ):
                missing.append(
                    f"{hypothesis.scenario}: structural risk/reward is below the minimum"
                )
                continue

        candidates.append/(
            SetupCandidate(
                scenario=hypothesis.scenario,
                supporting_concepts=supporting,
                zone_concepts=zones,
                zone_locations=locations,
                entry_condition=entry_conditions,
                invalidation=invalidations,
                targets=_targets(hypothesis),
                rationale=rationale,
                direction=direction,
                entry_zone=entry_levels,
                invalidation_level=invalidation_level,
                target_levels=target_levels,
                confirmation_timeframes=_CONFIRMATION,
                source_timeframes=source_tfs,
            )
        )

    if not candidates:
        return SetupAssessment(
            decision=SetupDecision.NEED_MORE_EVIDENCE,
            candidates=(),
            missing_context=_unique(missing),
            conflicts=evidence_assessment.conflicts,
            reasons=("setup conditions are not sufficiently specified",),
        )

    return SetupAssessment(
        decision=SetupDecision.READY,
        candidates=tuple(candidates),
        missing_context=_unique(missing),
        conflicts=evidence_assessment.conflicts,
        reasons=("one or more conditional setups are sufficiently specified by the current seven-timeframe state",),
    )


def test_setup_engine_selects_nearest_mtf_target_above_current_price():
    frames = _frames(structure_4h=1, structure_15m=1, structure_1m=-1)
    for tf, frame in frames.items():
        frame.loc[0, "active_buy_liquidity_price"] = float("nan")
        frame.loc[0, "previous_high"] = float("nan")
        frame.loc[0, "internal_previous_high"] = float("nan")
        frame.loc[0, "rolling_high_60"] = float("nan")
    frames["1h"].loc[0, "previous_high"] = 130.0
    frames["4h"].loc[0, "previous_high"] = 125.0

    result = _pipeline(frames)
    candidate = result.candidates[0]
    assert candidate.target_levels
    assert candidate.target_levels[0].timeframe == "4h"
    assert candidate.target_levels[0].value == 125.0


def test_setup_engine_does_not_use_execution_timeframe_as_target_source():
    frames = _frames(structure_4h=1, structure_15m=1, structure_1m=-1)
    for tf, frame in frames.items():
        frame.loc[0, "active_buy_liquidity_price"] = float("nan")
        frame.loc[0, "previous_high"] = float("nan")
        frame.loc[0, "internal_previous_high"] = float("nan")
        frame.loc[0, "rolling_high_60"] = float("nan")
    frames["1m"].loc[0, "previous_high"] = 106.0
    frames["4h"].loc[0, "previous_high"] = 125.0

    result = _pipeline(frames)
    candidate = result.candidates[0]
    assert candidate.target_levels
    assert candidate.target_levels[0].timeframe == "4h"
