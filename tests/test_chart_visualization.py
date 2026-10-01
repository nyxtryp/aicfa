import pandas as pd

from aicfa.chart_visualization import build_chart_model, render_chart
from aicfa.setup_analysis import SetupAssessment, SetupCandidate, SetupDecision, SetupLevel


def _frame() -> pd.DataFrame:
    rows = []
    for i in range(40):
        base = 100 + i * 0.2
        rows.append({
            "timestamp": pd.Timestamp("2026-01-01", tz="UTC") + pd.Timedelta(minutes=15 * i),
            "open": base,
            "high": base + 0.8,
            "low": base - 0.6,
            "close": base + 0.3,
            "volume": 1000 + i,
            "bos_up": int(i == 24),
            "choch_up": 0,
            "mss_up": int(i == 24),
            "hh": int(i == 20),
            "hl": int(i == 22),
            "lh": 0,
            "ll": 0,
            "sweep_high": 0,
            "sweep_low": int(i == 18),
            "displacement_up": int(i == 24),
            "displacement_down": 0,
            "fvg_bullish": int(i == 25),
            "fvg_bullish_low": 106.0,
            "fvg_bullish_high": 106.4,
            "order_block_bullish": int(i == 26),
            "order_block_bullish_low": 105.5,
            "order_block_bullish_high": 106.2,
        })
    return pd.DataFrame(rows)


def _setup() -> SetupAssessment:
    candidate = SetupCandidate(
        scenario="continuation",
        supporting_concepts=("market_structure.bos", "displacement", "imbalance.fvg"),
        zone_concepts=("imbalance.fvg",),
        zone_locations=("imbalance.fvg: discount",),
        entry_condition=("wait for confirmation",),
        invalidation=("below liquidity",),
        targets=("next liquidity",),
        rationale=("causal test setup",),
        direction="long",
        entry_zone=(
            SetupLevel(106.0, "15m", "active bullish FVG low"),
            SetupLevel(106.4, "15m", "active bullish FVG high"),
        ),
        invalidation_level=SetupLevel(105.0, "5m", "sell-side liquidity"),
        target_levels=(
            SetupLevel(109.0, "4h", "previous high"),
            SetupLevel(112.0, "1d", "previous high"),
        ),
        confirmation_timeframes=("15m", "5m"),
        source_timeframes=("1w", "1d", "4h", "1h", "15m", "5m", "1m"),
    )
    return SetupAssessment(
        decision=SetupDecision.READY,
        candidates=(candidate,),
        missing_context=(),
        conflicts=(),
        reasons=("ready",),
    )


def test_chart_model_preserves_setup_geometry_and_provenance():
    model = build_chart_model({"15m": _frame(), "5m": _frame()}, _setup(), asset="BTC/USDT")
    assert model.timeframe == "15m"
    assert model.direction == "long"
    assert [(x.kind, x.value, x.timeframe, x.source) for x in model.levels] == [
        ("ENTRY LOW", 106.0, "15m", "active bullish FVG low"),
        ("ENTRY HIGH", 106.4, "15m", "active bullish FVG high"),
        ("INVALIDATION", 105.0, "5m", "sell-side liquidity"),
        ("TP1", 109.0, "4h", "previous high"),
        ("TP2", 112.0, "1d", "previous high"),
    ]
    assert model.source_timeframes == ("1w", "1d", "4h", "1h", "15m", "5m", "1m")
    assert any(event.label == "BOS↑" for event in model.events)
    assert any(event.label == "HH" for event in model.structure_labels)
    assert any(zone.source == "FVG bullish" for zone in model.zones)
    assert any(zone.source == "OB bullish" for zone in model.zones)


def test_chart_model_never_uses_1m_as_setup_geometry_source():
    model = build_chart_model({"1m": _frame(), "15m": _frame()}, _setup(), asset="BTC/USDT")
    assert model.timeframe == "15m"
    assert all(level.timeframe != "1m" for level in model.levels)


def test_wait_does_not_invent_trade_geometry():
    setup = SetupAssessment(
        decision=SetupDecision.WAIT,
        candidates=(),
        missing_context=(),
        conflicts=(),
        reasons=("insufficient evidence",),
    )
    model = build_chart_model({"15m": _frame()}, setup, asset="BTC/USDT")
    assert model.status == "WAIT"
    assert model.levels == ()


def test_renderer_writes_nonempty_png(tmp_path):
    model = build_chart_model({"15m": _frame()}, _setup(), asset="BTC/USDT")
    output = render_chart(model, tmp_path / "aicfa_setup.png")
    assert output.exists()
    assert output.stat().st_size > 10_000


def test_renderer_is_causal_with_future_feature_changes():
    original = _frame()
    altered = original.copy()
    altered.loc[35:, "bos_up"] = 1
    first = build_chart_model({"15m": original}, _setup(), asset="BTC/USDT")
    second = build_chart_model({"15m": altered}, _setup(), asset="BTC/USDT")
    assert tuple((e.index, e.label) for e in first.events if e.index < 35) == tuple(
        (e.index, e.label) for e in second.events if e.index < 35
    )
