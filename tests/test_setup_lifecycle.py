import pytest

from aicfa.setup_analysis import SetupAssessment, SetupCandidate, SetupDecision, SetupLevel
from aicfa.setup_lifecycle import SetupLifecycle, SetupLifecycleStatus


def _candidate():
    return SetupCandidate(
        scenario="continuation",
        supporting_concepts=("market_structure.bos", "imbalance.fvg"),
        zone_concepts=("imbalance.fvg",),
        zone_locations=("15m",),
        entry_condition=("15m",),
        invalidation=("sell-side liquidity",),
        targets=("TP1", "TP2"),
        rationale=("higher-timeframe structure supports continuation",),
        direction="long",
        entry_zone=(
            SetupLevel(100.0, "15m", "active bullish FVG low"),
            SetupLevel(102.0, "15m", "active bullish FVG high"),
        ),
        invalidation_level=SetupLevel(95.0, "5m", "sell-side liquidity"),
        target_levels=(
            SetupLevel(110.0, "4h", "previous high"),
            SetupLevel(120.0, "1d", "previous high"),
        ),
        confirmation_timeframes=("15m", "5m"),
        source_timeframes=("1w", "1d", "4h", "1h", "15m", "5m", "1m"),
    )


def _ready():
    return SetupAssessment(
        decision=SetupDecision.READY,
        candidates=(_candidate(),),
        missing_context=(),
        conflicts=(),
        reasons=("setup ready",),
    )


def test_active_long_survives_new_analytical_wait():
    lifecycle = SetupLifecycle()
    first = lifecycle.evaluate(
        symbol="BTC/USDT",
        market_type="spot",
        assessment=_ready(),
        current_price=101.0,
        now_ms=1_000,
    )
    assert first.status is SetupLifecycleStatus.ACTIVE
    assert first.action == "LONG"

    wait = SetupAssessment(
        decision=SetupDecision.NEED_MORE_EVIDENCE,
        candidates=(),
        missing_context=("temporary evidence gap",),
        conflicts=(),
        reasons=("current state is incomplete",),
    )
    second = lifecycle.evaluate(
        symbol="BTC/USDT",
        market_type="spot",
        assessment=wait,
        current_price=103.0,
        now_ms=2_000,
    )

    assert second.status is SetupLifecycleStatus.ACTIVE
    assert second.action == "LONG"
    assert second.candidate == first.candidate
    assert lifecycle.active(symbol="BTC/USDT").candidate == first.candidate


def test_active_long_closes_only_when_invalidation_is_hit():
    lifecycle = SetupLifecycle()
    lifecycle.evaluate(
        symbol="BTC/USDT",
        market_type="spot",
        assessment=_ready(),
        current_price=101.0,
        now_ms=1_000,
    )

    result = lifecycle.evaluate(
        symbol="BTC/USDT",
        market_type="spot",
        assessment=SetupAssessment(
            decision=SetupDecision.NEED_MORE_EVIDENCE,
            candidates=(),
            missing_context=("rr changed",),
            conflicts=(),
            reasons=("no new setup",),
        ),
        current_price=95.0,
        now_ms=2_000,
    )

    assert result.status is SetupLifecycleStatus.INVALIDATED
    assert result.action == "WAIT"
    assert lifecycle.active(symbol="BTC/USDT") is None


def test_active_long_keeps_original_geometry_when_new_ready_geometry_changes():
    lifecycle = SetupLifecycle()
    first = lifecycle.evaluate(
        symbol="BTC/USDT",
        market_type="spot",
        assessment=_ready(),
        current_price=101.0,
        now_ms=1_000,
    )

    changed = _candidate()
    changed = SetupCandidate(
        **{**changed.__dict__, "target_levels": (
            SetupLevel(111.0, "4h", "new previous high"),
            SetupLevel(125.0, "1d", "new previous high"),
        )}
    )
    assessment = SetupAssessment(
        decision=SetupDecision.READY,
        candidates=(changed,),
        missing_context=(),
        conflicts=(),
        reasons=("new geometry",),
    )

    result = lifecycle.evaluate(
        symbol="BTC/USDT",
        market_type="spot",
        assessment=assessment,
        current_price=104.0,
        now_ms=2_000,
    )

    assert result.action == "LONG"
    assert result.candidate == first.candidate
    assert result.candidate.target_levels[0].value == 110.0


def test_active_long_completes_at_target_two():
    lifecycle = SetupLifecycle()
    lifecycle.evaluate(
        symbol="BTC/USDT",
        market_type="spot",
        assessment=_ready(),
        current_price=101.0,
        now_ms=1_000,
    )

    result = lifecycle.evaluate(
        symbol="BTC/USDT",
        market_type="spot",
        assessment=SetupAssessment(
            decision=SetupDecision.NEED_MORE_EVIDENCE,
            candidates=(),
            missing_context=("new setup unavailable",),
            conflicts=(),
            reasons=("no new setup",),
        ),
        current_price=120.0,
        now_ms=2_000,
    )

    assert result.status is SetupLifecycleStatus.COMPLETED
    assert result.action == "WAIT"
    assert lifecycle.active(symbol="BTC/USDT") is None
