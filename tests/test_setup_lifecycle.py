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
            SetupLevel(115.0, "4h", "previous high"),
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


def test_multiple_distinct_candidates_activate_and_remain_independent():
    lifecycle = SetupLifecycle()
    first = _candidate()
    second = SetupCandidate(
        **{**first.__dict__,
           "entry_zone": (
               SetupLevel(96.0, "15m", "active bullish FVG low"),
               SetupLevel(98.0, "15m", "active bullish FVG high"),
           ),
           "invalidation_level": SetupLevel(92.0, "5m", "previous low"),
           "target_levels": (
               SetupLevel(108.0, "4h", "previous high"),
               SetupLevel(115.0, "1d", "previous high"),
           )}
    )
    assessment = SetupAssessment(
        decision=SetupDecision.READY,
        candidates=(first, second),
        missing_context=(),
        conflicts=(),
        reasons=("two independent setups",),
    )

    results = lifecycle.evaluate_all(
        symbol="BTC/USDT",
        market_type="spot",
        horizon="intraday",
        assessment=assessment,
        current_price=101.0,
        current_high=103.0,
        current_low=99.0,
        now_ms=1_000,
    )

    # Only the candidate whose POI is actually touched by the execution
    # candle may become actionable. The second zone is still below price.
    assert len(results) == 1
    assert results[0].status is SetupLifecycleStatus.ACTIVE
    assert len(lifecycle.active_setups(symbol="BTC/USDT", horizon="intraday")) == 1


def test_same_candidate_on_next_scan_does_not_create_duplicate():
    lifecycle = SetupLifecycle()
    assessment = _ready()

    lifecycle.evaluate_all(
        symbol="BTC/USDT", market_type="spot", horizon="intraday",
        assessment=assessment, current_price=101.0, now_ms=1_000,
    )
    results = lifecycle.evaluate_all(
        symbol="BTC/USDT", market_type="spot", horizon="intraday",
        assessment=assessment, current_price=101.0, now_ms=2_000,
    )

    assert len(lifecycle.active_setups(symbol="BTC/USDT", horizon="intraday")) == 1
    assert results[-1].status is SetupLifecycleStatus.ACTIVE
    assert results[-1].candidate == assessment.candidates[0]


def test_same_market_can_hold_independent_horizons():
    lifecycle = SetupLifecycle()
    assessment = _ready()

    lifecycle.evaluate_all(
        symbol="BTC/USDT", market_type="spot", horizon="intraday",
        assessment=assessment, current_price=101.0, now_ms=1_000,
    )
    lifecycle.evaluate_all(
        symbol="BTC/USDT", market_type="spot", horizon="swing",
        assessment=assessment, current_price=101.0, now_ms=1_000,
    )
    lifecycle.evaluate_all(
        symbol="BTC/USDT", market_type="spot", horizon="position",
        assessment=assessment, current_price=101.0, now_ms=1_000,
    )

    assert len(lifecycle.active_setups(symbol="BTC/USDT")) == 3


def test_new_short_setup_is_not_activated_after_price_passed_entry_and_tp1():
    lifecycle = SetupLifecycle()
    candidate = SetupCandidate(
        **{**_candidate().__dict__,
           "direction": "short",
           "entry_zone": (
               SetupLevel(757.63, "1h", "bearish OB low"),
               SetupLevel(760.06, "1h", "bearish OB high"),
           ),
           "invalidation_level": SetupLevel(770.64, "1h", "structure invalidation"),
           "target_levels": (
               SetupLevel(745.17, "15m", "sell-side liquidity"),
               SetupLevel(735.00, "5m", "next liquidity"),
           )}
    )
    assessment = SetupAssessment(
        decision=SetupDecision.READY,
        candidates=(candidate,),
        missing_context=(),
        conflicts=(),
        reasons=("ready reversal",),
    )

    result = lifecycle.evaluate(
        symbol="BNB/USDT",
        market_type="spot",
        assessment=assessment,
        current_price=737.0,
        now_ms=1_000,
    )

    assert result.status is None
    assert result.action == "WAIT"
    assert lifecycle.active(symbol="BNB/USDT") is None


def test_long_setup_is_invalidated_when_execution_candle_wicks_through_stop():
    lifecycle = SetupLifecycle()
    first = lifecycle.evaluate(
        symbol="GRT/USDT",
        market_type="spot",
        assessment=_ready(),
        current_price=101.0,
        current_high=103.0,
        current_low=94.0,
        now_ms=1_000,
    )
    assert first.status is SetupLifecycleStatus.INVALIDATED
    assert lifecycle.active(symbol="GRT/USDT") is None


def test_long_setup_reaching_tp1_on_execution_candle_is_not_reported_as_fresh_entry():
    lifecycle = SetupLifecycle()
    result = lifecycle.evaluate(
        symbol="GRT/USDT",
        market_type="spot",
        assessment=_ready(),
        current_price=106.0,
        current_high=116.0,
        current_low=100.5,
        now_ms=1_000,
    )
    assert result.status is None
    assert result.action == "WAIT"
    assert lifecycle.active(symbol="GRT/USDT") is None


def test_active_long_is_invalidated_by_candle_low_even_if_close_recovers_above_stop():
    lifecycle = SetupLifecycle()
    first = lifecycle.evaluate(
        symbol="GRT/USDT",
        market_type="spot",
        assessment=_ready(),
        current_price=101.0,
        current_high=103.0,
        current_low=100.0,
        now_ms=1_000,
    )
    assert first.status is SetupLifecycleStatus.ACTIVE

    result = lifecycle.evaluate(
        symbol="GRT/USDT",
        market_type="spot",
        assessment=SetupAssessment(
            decision=SetupDecision.NEED_MORE_EVIDENCE,
            candidates=(),
            missing_context=("temporary gap",),
            conflicts=(),
            reasons=("no new setup",),
        ),
        current_price=99.0,
        current_high=101.0,
        current_low=94.0,
        now_ms=2_000,
    )
    assert result.status is SetupLifecycleStatus.INVALIDATED
    assert lifecycle.active(symbol="GRT/USDT") is None


def test_new_long_setup_stays_unpublished_until_price_reaches_entry_zone():
    lifecycle = SetupLifecycle()
    result = lifecycle.evaluate(
        symbol="GRT/USDT",
        market_type="spot",
        assessment=_ready(),
        current_price=110.0,
        current_high=111.0,
        current_low=109.0,
        now_ms=1_000,
    )
    assert result.status is None
    assert result.action == "WAIT"
    assert lifecycle.active(symbol="GRT/USDT") is None


def test_new_long_setup_is_missed_after_price_has_fully_passed_below_zone():
    lifecycle = SetupLifecycle()
    result = lifecycle.evaluate(
        symbol="GRT/USDT",
        market_type="spot",
        assessment=_ready(),
        current_price=90.0,
        current_high=91.0,
        current_low=89.0,
        now_ms=1_000,
    )
    assert result.status is None
    assert result.action == "WAIT"
    assert lifecycle.active(symbol="GRT/USDT") is None


def test_active_setup_is_not_closed_by_wall_clock_expiry(tmp_path):
    lifecycle = SetupLifecycle()
    first = lifecycle.evaluate_all(
        symbol="BTC/USDT",
        market_type="spot",
        horizon="intraday",
        assessment=_ready(),
        current_price=101.0,
        current_high=103.0,
        current_low=100.5,
        now_ms=1_000,
        expires_at_ms=1_001,
    )
    assert first[-1].status is SetupLifecycleStatus.ACTIVE

    later = lifecycle.evaluate_all(
        symbol="BTC/USDT",
        market_type="spot",
        horizon="intraday",
        assessment=SetupAssessment(
            decision=SetupDecision.NEED_MORE_EVIDENCE,
            candidates=(),
            missing_context=("no new setup",),
            conflicts=(),
            reasons=("analytical wait",),
        ),
        current_price=104.0,
        current_high=105.0,
        current_low=103.0,
        now_ms=86_400_000,
    )

    assert later[-1].status is SetupLifecycleStatus.ACTIVE
    assert lifecycle.active(symbol="BTC/USDT", horizon="intraday") is not None
