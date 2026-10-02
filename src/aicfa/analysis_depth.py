"""Knowledge-derived adaptive analysis-depth contract.

This module separates feature warm-up from the market-history depth needed by
SMC/price-action analysis. The returned row counts are analysis defaults, not
exchange limits; providers may return fewer rows when history is unavailable.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Sequence

from .data_requirements import (
    ContextNeed,
    DataRequirementPlan,
    TimeframeRole,
)


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


# These are analysis-history defaults, not exchange/provider limits.
# SMC does not define one universal candle count: HTF establishes broad
# context, the structure timeframe defines the active swing, and lower
# timeframes refine/execute. We therefore give each role a different history
# budget while keeping enough rows for the current causal feature graph.
_ROLE_DEPTH_ROWS: Mapping[TimeframeRole, int] = {
    TimeframeRole.BROADER_CONTEXT: 120,
    TimeframeRole.HIGHER_STRUCTURE: 180,
    TimeframeRole.LOWER_CONFIRMATION: 240,
    TimeframeRole.EXECUTION: 240,
}

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


def _role_depth(plan: DataRequirementPlan, timeframe: str) -> int:
    if plan.mode is None:
        # Without a mode, timeframe-to-role mapping is ambiguous. Do not guess
        # that a given timeframe is context/structure/execution; use the
        # conservative depth. Live FindSetup requests always provide a mode.
        return max(_ROLE_DEPTH_ROWS.values())
    profile = plan.mode
    # Mode is normalized by DataRequirementPlan; required_timeframes and roles
    # remain the authoritative mapping for the active analysis.
    from .data_requirements import mode_timeframe_profile

    roles = dict(mode_timeframe_profile(profile).roles)
    role = roles.get(timeframe)
    if role is None:
        return max(_ROLE_DEPTH_ROWS.values())
    return _ROLE_DEPTH_ROWS[role]


def resolve_analysis_depth(
    plan: DataRequirementPlan,
    *,
    timeframes: Sequence[str] | None = None,
) -> Mapping[str, AnalysisDepthRequirement]:
    """Resolve mode/role-aware SMC history plus technical warm-up context."""
    selected = tuple(plan.required_timeframes if timeframes is None else timeframes)
    if not selected:
        raise ValueError("analysis depth requires at least one timeframe")

    dependency_minimum = _dependency_minimum()
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
            minimum_rows=max(dependency_minimum, _role_depth(plan, timeframe)),
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
