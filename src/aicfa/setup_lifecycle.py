"""Stateful lifecycle for actionable AICFA setups.

The analytical SETUP ENGINE remains stateless and answers whether a new setup
can be formed from the current market state. This module owns the separate
lifecycle of a setup that has already been emitted: ACTIVE until invalidated,
completed, or explicitly expired.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .setup_analysis import SetupAssessment, SetupCandidate


class SetupLifecycleStatus(str, Enum):
    ACTIVE = "active"
    TP1_HIT = "tp1_hit"
    COMPLETED = "completed"
    INVALIDATED = "invalidated"
    EXPIRED = "expired"


@dataclass(frozen=True)
class ActiveSetup:
    symbol: str
    market_type: str
    candidate: SetupCandidate
    created_at_ms: int
    last_seen_at_ms: int
    expires_at_ms: int | None = None


@dataclass(frozen=True)
class SetupLifecycleResult:
    status: SetupLifecycleStatus | None
    candidate: SetupCandidate | None
    action: str
    reason: str


class SetupLifecycle:
    """Keep an emitted setup stable until its lifecycle actually closes.

    A new analytical WAIT cannot overwrite an existing ACTIVE setup. The
    original Entry, Invalidation and Target geometry is immutable.
    """

    def __init__(self) -> None:
        self._active: dict[tuple[str, str], ActiveSetup] = {}

    def active(self, *, symbol: str, market_type: str = "spot") -> ActiveSetup | None:
        return self._active.get((symbol, market_type))

    @staticmethod
    def _hit_invalidation(candidate: SetupCandidate, price: float) -> bool:
        level = candidate.invalidation_level
        if level is None or candidate.direction is None:
            return False
        if candidate.direction == "long":
            return price <= level.value
        return price >= level.value

    @staticmethod
    def _hit_target(candidate: SetupCandidate, price: float, index: int) -> bool:
        if len(candidate.target_levels) <= index or candidate.direction is None:
            return False
        target = candidate.target_levels[index].value
        if candidate.direction == "long":
            return price >= target
        return price <= target

    def evaluate(
        self,
        *,
        symbol: str,
        market_type: str,
        assessment: SetupAssessment,
        current_price: float,
        now_ms: int,
        expires_at_ms: int | None = None,
    ) -> SetupLifecycleResult:
        key = (symbol, market_type)
        active = self._active.get(key)

        if active is not None:
            if active.expires_at_ms is not None and now_ms >= active.expires_at_ms:
                del self._active[key]
                return SetupLifecycleResult(
                    status=SetupLifecycleStatus.EXPIRED,
                    candidate=active.candidate,
                    action="WAIT",
                    reason="active setup expired",
                )

            if self._hit_invalidation(active.candidate, current_price):
                del self._active[key]
                return SetupLifecycleResult(
                    status=SetupLifecycleStatus.INVALIDATED,
                    candidate=active.candidate,
                    action="WAIT",
                    reason="active setup invalidated by its original invalidation level",
                )

            active = ActiveSetup(
                symbol=active.symbol,
                market_type=active.market_type,
                candidate=active.candidate,
                created_at_ms=active.created_at_ms,
                last_seen_at_ms=now_ms,
                expires_at_ms=active.expires_at_ms,
            )
            self._active[key] = active

            if self._hit_target(active.candidate, current_price, 1):
                del self._active[key]
                return SetupLifecycleResult(
                    status=SetupLifecycleStatus.COMPLETED,
                    candidate=active.candidate,
                    action="WAIT",
                    reason="active setup reached Target 2 and is completed",
                )

            if self._hit_target(active.candidate, current_price, 0):
                return SetupLifecycleResult(
                    status=SetupLifecycleStatus.TP1_HIT,
                    candidate=active.candidate,
                    action=active.candidate.direction.upper(),
                    reason="active setup remains valid after Target 1; Target 2 remains",
                )

            return SetupLifecycleResult(
                status=SetupLifecycleStatus.ACTIVE,
                candidate=active.candidate,
                action=active.candidate.direction.upper(),
                reason="active setup remains valid; current analytical WAIT does not replace it",
            )

        if assessment.decision.value == "ready":
            if len(assessment.candidates) != 1:
                return SetupLifecycleResult(
                    status=None,
                    candidate=None,
                    action="WAIT",
                    reason="multiple distinct actionable setups require explicit resolution before activation",
                )
            candidate = assessment.candidates[0]
            active = ActiveSetup(
                symbol=symbol,
                market_type=market_type,
                candidate=candidate,
                created_at_ms=now_ms,
                last_seen_at_ms=now_ms,
                expires_at_ms=expires_at_ms,
            )
            self._active[key] = active
            return SetupLifecycleResult(
                status=SetupLifecycleStatus.ACTIVE,
                candidate=candidate,
                action=candidate.direction.upper(),
                reason="new setup activated",
            )

        return SetupLifecycleResult(
            status=None,
            candidate=None,
            action="WAIT",
            reason="no active setup and no new actionable setup is ready",
        )

    def clear(self, *, symbol: str, market_type: str = "spot") -> None:
        self._active.pop((symbol, market_type), None)
