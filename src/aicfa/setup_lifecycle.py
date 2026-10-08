"""Stateful lifecycle for independent AICFA setups."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import threading

from .data_requirements import TradingMode, normalize_trading_mode
from .setup_analysis import SetupAssessment, SetupCandidate, SetupLevel


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
        self._lock = threading.RLock()

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

    @staticmethod
    def _candidate_from_record(payload: dict) -> SetupCandidate | None:
        """Rehydrate a lifecycle-owned candidate persisted by SetupRegistry."""
        raw = payload.get("candidate") if isinstance(payload, dict) else None
        if not isinstance(raw, dict):
            return None

        def level(value):
            if not isinstance(value, dict):
                return None
            try:
                return SetupLevel(
                    float(value["value"]),
                    str(value["timeframe"]),
                    str(value["source"]),
                )
            except (KeyError, TypeError, ValueError):
                return None

        entry_zone = tuple(x for x in (level(v) for v in raw.get("entry_zone", ())) if x is not None)
        targets = tuple(x for x in (level(v) for v in raw.get("target_levels", ())) if x is not None)
        invalidation = level(raw.get("invalidation_level"))
        try:
            return SetupCandidate(
                scenario=str(raw.get("scenario", "")),
                supporting_concepts=tuple(str(x) for x in raw.get("supporting_concepts", ())),
                zone_concepts=tuple(str(x) for x in raw.get("zone_concepts", ())),
                zone_locations=tuple(str(x) for x in raw.get("zone_locations", ())),
                entry_condition=tuple(str(x) for x in raw.get("entry_condition", ())),
                invalidation=tuple(str(x) for x in raw.get("invalidation", ())),
                targets=tuple(str(x) for x in raw.get("targets", ())),
                rationale=tuple(str(x) for x in raw.get("rationale", ())),
                direction=(str(raw["direction"]) if raw.get("direction") is not None else None),
                entry_zone=entry_zone,
                invalidation_level=invalidation,
                target_levels=targets,
                confirmation_timeframes=tuple(str(x) for x in raw.get("confirmation_timeframes", ())),
                source_timeframes=tuple(str(x) for x in raw.get("source_timeframes", ())),
            )
        except (TypeError, ValueError):
            return None

    def restore_from_registry(self, records: dict[str, dict]) -> int:
        """Restore ACTIVE/TP1_HIT lifecycle state after a process restart."""
        restored = 0
        for record in records.values():
            status = str(record.get("status", "")).upper()
            if status not in {"ACTIVE", "TP1_HIT"}:
                continue
            setup_payload = record.get("setup")
            candidate = self._candidate_from_record(setup_payload if isinstance(setup_payload, dict) else {})
            if candidate is None or candidate.direction not in {"long", "short"}:
                continue
            try:
                horizon = normalize_trading_mode(record.get("mode", "intraday"))
                identity = self.identity(
                    symbol=str(record["asset"]),
                    market_type=str(record.get("market_type", "spot")),
                    horizon=horizon,
                    candidate=candidate,
                )
                created = int(record.get("created_at_ms", 0))
                last_seen = int(record.get("last_seen_at_ms", created))
            except (KeyError, TypeError, ValueError):
                continue
            self._active[identity] = ActiveSetup(
                symbol=str(record["asset"]),
                market_type=str(record.get("market_type", "spot")),
                horizon=horizon,
                identity=identity,
                candidate=candidate,
                created_at_ms=created,
                last_seen_at_ms=last_seen,
                expires_at_ms=None,
            )
            restored += 1
        return restored

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
        with self._lock:
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
    def _risk_reward(candidate: SetupCandidate) -> float | None:
        """Return first-target structural RR without inventing prices."""
        if candidate.direction not in {"long", "short"}:
            return None
        if candidate.invalidation_level is None or not candidate.entry_zone or not candidate.target_levels:
            return None
        entry_low = min(level.value for level in candidate.entry_zone)
        entry_high = max(level.value for level in candidate.entry_zone)
        entry = (entry_low + entry_high) / 2.0
        stop = candidate.invalidation_level.value
        target = candidate.target_levels[0].value
        risk = entry - stop if candidate.direction == "long" else stop - entry
        reward = target - entry if candidate.direction == "long" else entry - target
        if risk <= 0 or reward <= 0:
            return None
        return reward / risk

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
        current_high: float | None = None,
        current_low: float | None = None,
    ) -> tuple[SetupLifecycleResult, ...]:
        with self._lock:
            return self._evaluate_all_unlocked(
                symbol=symbol,
                market_type=market_type,
                horizon=horizon,
                assessment=assessment,
                current_price=current_price,
                now_ms=now_ms,
                expires_at_ms=expires_at_ms,
                current_high=current_high,
                current_low=current_low,
            )

    def _evaluate_all_unlocked(
        self,
        *,
        symbol: str,
        market_type: str,
        horizon: TradingMode | str,
        assessment: SetupAssessment,
        current_price: float,
        now_ms: int,
        expires_at_ms: int | None = None,
        current_high: float | None = None,
        current_low: float | None = None,
    ) -> tuple[SetupLifecycleResult, ...]:
        """Evaluate all existing setups and activate every distinct new candidate."""
        normalized = normalize_trading_mode(horizon)
        results: list[SetupLifecycleResult] = []

        # Existing setups are evaluated independently. A temporary analytical
        # WAIT never removes a still-valid setup.
        for setup_id, active in tuple(self._active.items()):
            if setup_id.symbol != symbol or setup_id.market_type != market_type or setup_id.horizon != normalized:
                continue

            # An active trade is closed by market structure: stop or target.
            # Wall-clock expiry must never silently remove a live setup.
            invalidation_price = current_low if active.candidate.direction == "long" and current_low is not None else current_high if active.candidate.direction == "short" and current_high is not None else current_price
            if self._hit_invalidation(active.candidate, invalidation_price):
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

            target2_price = current_high if active.candidate.direction == "long" and current_high is not None else current_low if active.candidate.direction == "short" and current_low is not None else current_price
            if self._hit_target(active.candidate, target2_price, 1):
                del self._active[setup_id]
                results.append(SetupLifecycleResult(
                    SetupLifecycleStatus.COMPLETED, active.candidate, "WAIT",
                    "active setup reached Target 2 and is completed", setup_id,
                ))
            elif self._hit_target(active.candidate, target2_price, 0):
                results.append(SetupLifecycleResult(
                    SetupLifecycleStatus.TP1_HIT, active.candidate, active.candidate.direction.upper(),
                    "active setup remains valid after Target 1; Target 2 remains", setup_id,
                ))
            else:
                results.append(SetupLifecycleResult(
                    SetupLifecycleStatus.ACTIVE, active.candidate, active.candidate.direction.upper(),
                    "active setup remains valid; current analytical WAIT does not replace it", setup_id,
                ))

        # Every distinct actionable candidate may become active, but only
        # while its entry is still reachable. Never publish a fresh entry
        # after price has already crossed the zone or its first target.
        if assessment.decision.value == "ready":
            for candidate in assessment.candidates:
                if candidate.direction not in {"long", "short"}:
                    continue
                entry_values = [level.value for level in candidate.entry_zone]
                if not entry_values:
                    continue
                entry_low = min(entry_values)
                entry_high = max(entry_values)
                # A candidate is only an actionable entry after price has
                # actually reached its POI. A zone sitting below/above price is
                # a pending setup, not a live trade. If price has already passed
                # through the zone, the opportunity is missed and must not be
                # published as a fresh entry.
                candle_high = current_high if current_high is not None else current_price
                candle_low = current_low if current_low is not None else current_price
                zone_touched = candle_low <= entry_high and candle_high >= entry_low
                if not zone_touched:
                    continue
                invalidation_price = current_low if candidate.direction == "long" and current_low is not None else current_high if candidate.direction == "short" and current_high is not None else current_price
                target_price = current_high if candidate.direction == "long" and current_high is not None else current_low if candidate.direction == "short" and current_low is not None else current_price
                setup_id = self.identity(
                    symbol=symbol,
                    market_type=market_type,
                    horizon=normalized,
                    candidate=candidate,
                )
                if self._hit_invalidation(candidate, invalidation_price):
                    results.append(SetupLifecycleResult(
                        SetupLifecycleStatus.INVALIDATED,
                        candidate,
                        "WAIT",
                        "new setup was touched but invalidated on the same execution candle",
                        setup_id,
                    ))
                    continue
                if self._hit_target(candidate, target_price, 0):
                    continue

                if setup_id in self._active:
                    continue

                rr = self._risk_reward(candidate)
                if rr is None or rr < 2.0:
                    results.append(SetupLifecycleResult(
                        None, candidate, "WAIT",
                        (
                            f"new setup rejected: structural RR {rr:.2f}R is below the 2.0R minimum"
                            if rr is not None
                            else "new setup rejected: structural RR cannot be calculated"
                        ),
                        setup_id,
                    ))
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
        current_high: float | None = None,
        current_low: float | None = None,
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
            current_high=current_high,
            current_low=current_low,
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
