import pandas as pd
import pytest
from types import SimpleNamespace

from aicfa.data_requirements import TradingMode
from aicfa.setup_analysis import SetupCandidate, SetupLevel
from aicfa.trade_description import build_trade_description, build_trade_descriptions


def _result(candidate):
    frame = pd.DataFrame(
        {"timestamp": [pd.Timestamp("2026-10-03T10:00:00Z")], "close": [100.0]}
    )
    return SimpleNamespace(
        symbol="BTC/USDT",
        mode=TradingMode.INTRADAY,
        request=SimpleNamespace(market_type="spot"),
        analysis=frame,
        setup_assessment=SimpleNamespace(candidates=(candidate,)),
    )


def _candidate():
    return SetupCandidate(
        scenario="continuation",
        supporting_concepts=(
            "market_structure.bos",
            "displacement",
            "liquidity.sweep",
            "order_block.bullish",
            "price_action.rejection",
            "volume.confirmation",
        ),
        zone_concepts=("order_block.bullish", "imbalance.fvg"),
        zone_locations=("order_block.bullish: discount",),
        entry_condition=("zone reaction/confirmation is required before long entry",),
        invalidation=("previous low breaks the setup",),
        targets=("next liquidity",),
        rationale=("BOS followed by displacement",),
        direction="long",
        entry_zone=(
            SetupLevel(98.0, "15m", "bullish OB low"),
            SetupLevel(99.0, "15m", "bullish OB high"),
        ),
        invalidation_level=SetupLevel(96.0, "1h", "previous low"),
        target_levels=(
            SetupLevel(105.0, "1h", "previous high"),
            SetupLevel(110.0, "4h", "active buy-side liquidity"),
        ),
        confirmation_timeframes=("15m",),
        source_timeframes=("1h", "15m"),
    )


def test_trade_description_projects_existing_geometry_and_evidence():
    description = build_trade_description(_result(_candidate()), now_ms=1_759_488_000_000)

    assert description.asset == "BTC/USDT"
    assert description.market_type == "spot"
    assert description.horizon is TradingMode.INTRADAY
    assert description.direction == "long"
    assert description.entry == description.entry_zone
    assert description.entry[0].value == 98.0
    assert description.stop_loss.value == 96.0
    assert description.tp1.value == 105.0
    assert description.tp2.value == 110.0
    assert description.rr == pytest.approx(6.0)
    assert "market_structure.bos" in description.structure_evidence
    assert "liquidity.sweep" in description.liquidity_evidence
    assert description.zone_evidence == ("order_block.bullish", "imbalance.fvg")
    assert description.reaction_evidence == ("price_action.rejection",)
    assert description.volume_evidence == ("volume.confirmation",)
    assert description.confirmation_timeframes == ("15m",)
    assert description.lifecycle_status == "new"
    assert description.freshness_ms is not None


def test_missing_geometry_is_preserved_without_fabrication():
    candidate = _candidate()
    candidate = SetupCandidate(
        **{**candidate.__dict__, "entry_zone": (), "invalidation_level": None, "target_levels": ()}
    )
    description = build_trade_description(_result(candidate))

    assert description.entry == ()
    assert description.stop_loss is None
    assert description.tp1 is None
    assert description.tp2 is None
    assert description.rr is None


def test_all_candidates_are_preserved():
    first = _candidate()
    second = SetupCandidate(**{**first.__dict__, "direction": "short", "scenario": "reversal"})
    result = _result(first)
    result = SimpleNamespace(**{**result.__dict__, "setup_assessment": SimpleNamespace(candidates=(first, second))})

    descriptions = build_trade_descriptions(result)

    assert len(descriptions) == 2
    assert [item.direction for item in descriptions] == ["long", "short"]


def test_invalid_direction_and_status_are_rejected():
    candidate = SetupCandidate(**{**_candidate().__dict__, "direction": None})
    with pytest.raises(ValueError, match="LONG or SHORT"):
        build_trade_description(_result(candidate))

    with pytest.raises(ValueError, match="lifecycle status"):
        build_trade_description(_result(_candidate()), lifecycle_status="signal")


def test_lifecycle_status_can_be_updated_without_changing_geometry():
    description = build_trade_description(
        _result(_candidate()),
        lifecycle_status="active",
    )
    assert description.lifecycle_status == "active"
    assert description.entry[0].value == 98.0
