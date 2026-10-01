"""Knowledge-derived adaptive analysis-depth contract.

This module describes why temporary OHLCV context is required. It does not
choose an exchange limit and it does not persist market history.

The initial minimum is derived from the causal dependencies currently used by
the deterministic feature graph. Active lifecycle state and recent events are
not bounded by an arbitrary row count, so the contract marks them for adaptive
context expansion.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Sequence

from .data_requirements import ContextNeed, DataRequirementPlan


class ContextResolution(str, Enum):
    MINIMUM_DEPENDENCY_CONTEXT = "minimum_dependency_context"
    RECENT_EVENTS = "recent_events"
    ACTIVE_LIFECYCLE_STATE = "active_lifecycle_state"


@dataclass(frozen=True)
class DependencyRequirement:
    name: str
    rows: int
    reason: str


@dataclass(frozen=True)
class AnalysisDepthRequirement:
    timeframe: str
    minimum_rows: int
    resolutions: tuple[ContextResolution, ...]
    dependencies: tuple[DependencyRequirement, ...]
    adaptive: bool

    @property
    def requires_event_context(self) -> bool:
        return ContextResolution.RECENT_EVENTS in self.resolutions

    @property
    def requires_active_state(self) -> bool:
        return ContextResolution.ACTIVE_LIFECYCLE_STATE in self.resolutions


# These values are dependency facts of the current causal feature graph, not
# production fetch limits. The largest explicit rolling dependency is 60.
_FEATURE_DEPENDENCIES: tuple[DependencyRequirement, ...] = (
    DependencyRequirement("feature.rolling", 60, "features.py uses a 60-row causal rolling baseline"),
    DependencyRequirement("displacement.baseline", 21, "20 prior candles plus the current candle"),
    DependencyRequirement("price_action.regime", 20, "Price Action uses a 20-row regime/lookback window"),
    DependencyRequirement("wyckoff.range", 21, "Wyckoff uses a prior 20-row range window"),
    DependencyRequirement("structure.external", 5, "2 left + pivot + 2 right causal swing confirmation"),
    DependencyRequirement("structure.internal", 3, "1 left + pivot + 1 right causal swing confirmation"),
    DependencyRequirement("fvg.creation", 3, "three-candle FVG definition"),
    DependencyRequirement("order_block.creation", 21, "immediately prior source candle plus displacement baseline"),
)


def _dependency_minimum() -> int:
    return max(item.rows for item in _FEATURE_DEPENDENCIES)


def resolve_analysis_depth(
    plan: DataRequirementPlan,
    *,
    timeframes: Sequence[str] | None = None,
) -> Mapping[str, AnalysisDepthRequirement]:
    """Resolve minimum temporary context from the active knowledge plan.

    The result deliberately separates dependency warm-up from lifecycle
    history. A finite warm-up proves that the feature graph can initialize;
    it cannot prove that an arbitrarily old FVG/OB/liquidity state is inactive.
    Such state requires adaptive expansion until the relevant causal anchor is
    established or the provider's available context is exhausted.
    """
    selected = tuple(plan.required_timeframes if timeframes is None else timeframes)
    if not selected:
        raise ValueError("analysis depth requires at least one timeframe")

    minimum = _dependency_minimum()
    resolutions = [ContextResolution.MINIMUM_DEPENDENCY_CONTEXT]
    if plan.needs(ContextNeed.RECENT_EVENTS):
        resolutions.append(ContextResolution.RECENT_EVENTS)
    if plan.needs(ContextNeed.ACTIVE_ZONES):
        resolutions.append(ContextResolution.ACTIVE_LIFECYCLE_STATE)

    adaptive = any(
        item in resolutions
        for item in (
            ContextResolution.RECENT_EVENTS,
            ContextResolution.ACTIVE_LIFECYCLE_STATE,
        )
    )

    return {
        timeframe: AnalysisDepthRequirement(
            timeframe=timeframe,
            minimum_rows=minimum,
            resolutions=tuple(dict.fromkeys(resolutions)),
            dependencies=_FEATURE_DEPENDENCIES,
            adaptive=adaptive,
        )
        for timeframe in selected
    }


__all__ = [
    "AnalysisDepthRequirement",
    "ContextResolution",
    "DependencyRequirement",
    "resolve_analysis_depth",
]
