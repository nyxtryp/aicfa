import pandas as pd

from aicfa.market_evidence_adapter import build_market_evidence, build_market_evidence_from_frames


def _analysis(**overrides):
    row = {
        "timestamp": 1,
        "bos_up": 0,
        "bos_down": 0,
        "displacement_up": 0,
        "displacement_down": 0,
        "fvg_bullish": 0,
        "fvg_bearish": 0,
        "order_block_bullish": 0,
        "order_block_bearish": 0,
        "sweep_low": 0,
        "sweep_high": 0,
    }
    row.update(overrides)
    return pd.DataFrame([row])


def test_adapter_emits_only_active_base_observations():
    evidence = build_market_evidence(
        _analysis(bos_up=1, fvg_bullish=1),
        asset="BTC/USDT",
    )

    assert {(item.concept_id, item.timeframe, item.direction) for item in evidence.observations} == {
        ("market_structure.bos", "1m", "long"),
        ("imbalance.fvg", "1m", "long"),
    }
    assert evidence.missing_context == ()


def test_adapter_consumes_latest_causal_event_when_latest_row_is_quiet():
    analysis = pd.DataFrame(
        [
            {
                "timestamp": 1,
                "bos_up": 1,
                "bos_down": 0,
                "displacement_up": 0,
                "displacement_down": 0,
                "fvg_bullish": 0,
                "fvg_bearish": 0,
                "order_block_bullish": 0,
                "order_block_bearish": 0,
                "sweep_low": 0,
                "sweep_high": 0,
            },
            {
                "timestamp": 2,
                "bos_up": 0,
                "bos_down": 0,
                "displacement_up": 0,
                "displacement_down": 0,
                "fvg_bullish": 0,
                "fvg_bearish": 0,
                "order_block_bullish": 0,
                "order_block_bearish": 0,
                "sweep_low": 0,
                "sweep_high": 0,
            },
        ]
    )

    evidence = build_market_evidence(
        analysis,
        asset="BTC/USDT",
        timeframes=("1m",),
    )

    assert [
        (item.concept_id, item.timeframe, item.direction)
        for item in evidence.observations
    ] == [("market_structure.bos", "1m", "long")]
    assert evidence.missing_context == ()


def test_adapter_reads_higher_timeframe_structure_from_mtf_columns():
    evidence = build_market_evidence(
        _analysis(**{"mtf_4h_bos_down": 1}),
        asset="BTC/USDT",
    )

    assert any(
        item.concept_id == "market_structure.bos"
        and item.timeframe == "4h"
        and item.direction == "short"
        for item in evidence.observations
    )


def test_adapter_does_not_treat_opposite_displacement_as_structural_conflict():
    evidence = build_market_evidence(
        _analysis(bos_up=1, displacement_down=1),
        asset="BTC/USDT",
    )

    assert evidence.conflicts == ()


def test_adapter_preserves_opposite_directions_across_timeframes_without_global_conflict():
    evidence = build_market_evidence_from_frames(
        {
            "1m": _analysis(bos_up=1),
            "4h": _analysis(bos_down=1),
        },
        asset="BTC/USDT",
        timeframes=("1m", "4h"),
    )

    assert {(item.concept_id, item.timeframe, item.direction) for item in evidence.observations} == {
        ("market_structure.bos", "1m", "long"),
        ("market_structure.bos", "4h", "short"),
    }
    assert evidence.conflicts == ()


def test_adapter_does_not_treat_context_zone_opposition_as_structural_conflict():
    evidence = build_market_evidence(
        _analysis(bos_up=1, fvg_bearish=1, order_block_bullish=1),
        asset="BTC/USDT",
    )

    assert evidence.conflicts == ()


def test_adapter_reports_missing_context_only_when_analysis_is_unavailable():
    evidence = build_market_evidence_from_frames(
        {"1h": _analysis(bos_up=1)},
        asset="BTC/USDT",
        timeframes=("1h", "4h"),
    )

    assert "4h:analysis_not_available" in evidence.missing_context
