"""Stateful lifecycle for independent AICFA setups."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .data_requirements import TradingMode, normalize_trading_mode
from .setup_analysis import SetupAssessment, SetupCandidate


class SetupLifecycleStatus(str, Enum):
    ACTIVE = "active"
    TP1_HIT = "tp1_hit"
    COMPLETED = "completed"
    INVALIDATED = "invalidated"
    EXPIRED = "expired"


@dataclass(frozen=True)
class SetupIdentity:
    """Stable identity for one actionable setup geometry."""

    symbol: str
    market_type: str
    horizon: TradingMode
    scenario: str
    direction: str
    entry_zone: tuple[tuple[float, str, str], ...]
    invalidation: tuple[float, str, str] | None
    targets: tuple[tuple[float, str, str], ...]


@dataclass(frozen=True)
class ActiveSetup:
    symbol: str
    market_type: str
    horizon: TradingMode
    identity: SetupIdentity
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
    identity: SetupIdentity | None = None


class SetupLifecycle:
    """Keep every independent emitted setup stable until its lifecycle closes.

    Multiple setups may coexist for the same market and horizon. Re-observing
    identical actionable geometry updates the existing setup instead of creating
    a duplicate; materially different geometry gets its own identity.
    """

    def __init__(self) -> None:
        self._active: dict[SetupIdentity, ActiveSetup] = {}

    @staticmethod
    def identity(
        *,
        symbol: str,
        market_type: str,
        horizon: TradingMode | str,
        candidate: SetupCandidate,
    ) -> SetupIdentity:
        if candidate.direction not in {"long", "short"}:
            raise ValueError("setup identity requires an explicit long/short direction")
        normalized = normalize_trading_mode(horizon)
        return SetupIdentity(
            symbol=symbol,
            market_type=market_type,
            horizon=normalized,
            scenario=candidate.scenario,
            direction=candidate.direction,
            entry_zone=tuple(
                (level.value, level.timeframe, level.source)
                for level in candidate.entry_zone
            ),
            invalidation=(
                None
                if candidate.invalidation_level is None
                else (
                    candidate.invalidation_level.value,
                    candidate.invalidation_level.timeframe,
                    candidate.invalidation_level.source,
                )
            ),
            targets=tuple(
                (level.value, level.timeframe, level.source)
                for level in candidate.target_levels
            ),
        )

    def active(
        self,
        *,
        symbol: str,
        market_type: str = "spot",
        horizon: TradingMode | str = TradingMode.INTRADAY,
        identity: SetupIdentity | None = None,
    ) -> ActiveSetup | None:
        if identity is not None:
            return self._active.get(identity)
        normalized = normalize_trading_mode(horizon)
        matches = [
            setup for setup_id, setup in self._active.items()
            if setup_id.symbol == symbol
            and setup_id.market_type == market_type
            and setup_id.horizon == normalized
        ]
        return matches[0] if len(matches) == 1 else None

    def active_setups(
        self,
        *,
        symbol: str | None = None,
        market_type: str | None = None,
        horizon: TradingMode | str | None = None,
    ) -> tuple[ActiveSetup, ...]:
        normalized = normalize_trading_mode(horizon) if horizon is not None else None
        return tuple(
            setup for setup in self._active.values()
            if (symbol is None or setup.symbol == symbol)
            and (market_type is None or setup.market_type == market_type)
            and (normalized is None or setup.horizon == normalized)
        )

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

    def evaluate_all(
        self,
        *,
        symbol: str,
        market_type: str,
        horizon: TradingMode | str,
        assessment: SetupAssessment,
        current_price: float,
        now_ms: int,
        expires_at_ms: int | None = None,
    ) -> tuple[SetupLifecycleResult, ...]:
        """Evaluate all existing setups and activate every distinct new candidate."""
        normalized = normalize_trading_mode(horizon)
        results: list[SetupLifecycleResult] = []

        # Existing setups are evaluated independently. A temporary analytical
        # WAIT never removes a still-valid setup.
        for setup_id, active in tuple(self._active.items()):
            if setup_id.symbol != symbol or setup_id.market_type != market_type or setup_id.horizon != normalized:
                continue

            if active.expires_at_ms is not None and now_ms >= active.expires_at_ms:
                del self._active[setup_id]
                results.append(SetupLifecycleResult(
                    SetupLifecycleStatus.EXPIRED, active.candidate, "WAIT",
                    "active setup expired", setup_id,
                ))
                continue

            if self._hit_invalidation(active.candidate, current_price):
                del self._active[setup_id]
                results.append(SetupLifecycleResult(
                    SetupLifecycleStatus.INVALIDATED, active.candidate, "WAIT",
                    "active setup invalidated by its original invalidation level", setup_id,
                ))
                continue

            refreshed = ActiveSetup(
                symbol=active.symbol,
                market_type=active.market_type,
                horizon=active.horizon,
                identity=active.identity,
                candidate=active.candidate,
                created_at_ms=active.created_at_ms,
                last_seen_at_ms=now_ms,
                expires_at_ms=active.expires_at_ms,
            )
            self._active[setup_id] = refreshed

            if self._hit_target(active.candidate, current_price, 1):
                del self._active[setup_id]
                results.append(SetupLifecycleResult(
                    SetupLifecycleStatus.COMPLETED, active.candidate, "WAIT",
                    "active setup reached Target 2 and is completed", setup_id,
                ))
            elif self._hit_target(active.candidate, current_price, 0):
                results.append(SetupLifecycleResult(
                    SetupLifecycleStatus.TP1_HIT, active.candidate, active.candidate.direction.upper(),
                    "active setup remains valid after Target 1; Target 2 remains", setup_id,
                ))
            else:
                results.append(SetupLifecycleResult(
                    SetupLifecycleStatus.ACTIVE, active.candidate, active.candidate.direction.upper(),
                    "active setup remains valid; current analytical WAIT does not replace it", setup_id,
                ))

        # Every distinct actionable candidate may become active. There is no
        # one-setup-per-market or one-setup-per-horizon restriction.
        if assessment.decision.value == "ready":
            for candidate in assessment.candidates:
                setup_id = self.identity(
                    symbol=symbol,
                    market_type=market_type,
                    horizon=normalized,
                    candidate=candidate,
                )
                if setup_id in self._active:
                    continue
                active = ActiveSetup(
                    symbol=symbol,
                    market_type=market_type,
                    horizon=normalized,
                    identity=setup_id,
                    candidate=candidate,
                    created_at_ms=now_ms,
                    last_seen_at_ms=now_ms,
                    expires_at_ms=expires_at_ms,
                )
                self._active[setup_id] = active
                results.append(SetupLifecycleResult(
                    SetupLifecycleStatus.ACTIVE, candidate, candidate.direction.upper(),
                    "new independent setup activated", setup_id,
                ))

        if not results:
            return (
                SetupLifecycleResult(
                    None, None, "WAIT",
                    "no active setup and no new actionable setup is ready",
                ),
            )
        return tuple(results)

    def evaluate(
        self,
        *,
        symbol: str,
        market_type: str,
        assessment: SetupAssessment,
        current_price: float,
        now_ms: int,
        expires_at_ms: int | None = None,
        horizon: TradingMode | str = TradingMode.INTRADAY,
    ) -> SetupLifecycleResult:
        """Backward-compatible single-result view over evaluate_all()."""
        results = self.evaluate_all(
            symbol=symbol,
            market_type=market_type,
            horizon=horizon,
            assessment=assessment,
            current_price=current_price,
            now_ms=now_ms,
            expires_at_ms=expires_at_ms,
        )
        return results[0]

    def clear(
        self,
        *,
        symbol: str,
        market_type: str = "spot",
        horizon: TradingMode | str | None = None,
        identity: SetupIdentity | None = None,
    ) -> None:
        if identity is not None:
            self._active.pop(identity, None)
            return
        normalized = normalize_trading_mode(horizon) if horizon is not None else None
        for setup_id in tuple(self._active):
            if setup_id.symbol != symbol or setup_id.market_type != market_type:
                continue
            if normalized is not None and setup_id.horizon != normalized:
                continue
            del self._active[setup_id]
