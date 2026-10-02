import numpy as np
import pandas as pd

from aicfa.zone_reaction import (
    ZONE_BROKEN,
    ZONE_CANCELLED,
    ZONE_REACTED,
    ZONE_RETESTED,
    ZONE_TOUCHED,
    build_zone_reaction,
)


def frame(highs, lows, closes):
    n = len(closes)
    closes = np.asarray(closes, dtype=float)
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=n, freq="min", tz="UTC").astype("int64") // 10**6,
            "open": closes,
            "high": np.asarray(highs, dtype=float),
            "low": np.asarray(lows, dtype=float),
            "close": closes,
            "volume": np.full(n, 10.0),
        }
    )


def structure_frame(n=10):
    out = pd.DataFrame(index=range(n))
    out["swing_high"] = 0
    out["swing_low"] = 0
    out["swing_high_price"] = np.nan
    out["swing_low_price"] = np.nan
    out.loc[2, ["swing_high", "swing_high_price"]] = [1, 105.0]
    out.loc[4, ["swing_low", "swing_low_price"]] = [1, 95.0]
    return out


def test_support_resistance_lifecycle_touch_reaction_retest_and_break_is_causal():
    df = frame(
        highs=[101, 102, 105, 103, 96, 106, 105.5, 106.5, 108],
        lows=[99, 100, 103, 101, 94, 103, 104.5, 104, 105],
        closes=[100, 101, 104, 102, 95, 104, 105, 105.5, 107],
    )
    structure = structure_frame(len(df))

    result = build_zone_reaction(
        df,
        structure=structure,
        reaction_threshold_pct=0.01,
    )

    # Resistance is created from the confirmed swing high, not its pivot row.
    assert result.loc[2, "zone_created_resistance"] == 1
    assert result.loc[2, "zone_resistance_price"] == 105.0

    # First interaction is a touch; reaction must occur on a later candle.
    assert result.loc[5, "zone_touch_resistance"] == 1
    assert result.loc[5, "zone_reaction_resistance"] == 0
    assert result.loc[6, "zone_reaction_resistance"] == 1
    assert result.loc[6, "zone_resistance_state"] == ZONE_REACTED

    # A later second interaction is a retest, not another first-touch event.
    assert result.loc[7, "zone_retest_resistance"] == 1
    assert result.loc[7, "zone_resistance_state"] == ZONE_RETESTED

    # A close through the level cancels/breaks the active resistance.
    assert result.loc[8, "zone_break_resistance"] == 1
    assert result.loc[8, "zone_resistance_state"] == ZONE_BROKEN


def test_zone_distance_is_available_before_touch():
    df = frame(
        highs=[101, 102, 103, 104],
        lows=[99, 100, 101, 102],
        closes=[100, 101, 102, 103],
    )
    structure = structure_frame(len(df))

    result = build_zone_reaction(df, structure=structure)

    assert np.isfinite(result.loc[3, "zone_distance_to_resistance"])
    assert result.loc[3, "zone_touch_resistance"] == 0


def test_ob_fvg_and_liquidity_zones_are_preserved_as_separate_sources():
    df = frame(
        highs=[101, 102, 106, 107, 108, 109],
        lows=[99, 100, 104, 105, 106, 107],
        closes=[100, 101, 105, 106, 107, 108],
    )
    structure = structure_frame(len(df))

    fvg = pd.DataFrame(
        {
            "fvg_bullish": [0, 0, 1, 0, 0, 0],
            "fvg_bullish_low": [np.nan, np.nan, 102.0, np.nan, np.nan, np.nan],
            "fvg_bullish_high": [np.nan, np.nan, 104.0, np.nan, np.nan, np.nan],
        }
    )
    order_blocks = pd.DataFrame(
        {
            "order_block_bullish": [0, 0, 0, 1, 0, 0],
            "order_block_bullish_low": [np.nan, np.nan, np.nan, 103.0, np.nan, np.nan],
            "order_block_bullish_high": [np.nan, np.nan, np.nan, 105.0, np.nan, np.nan],
        }
    )
    liquidity = pd.DataFrame(
        {
            "liquidity_pool_created_low": [np.nan, np.nan, np.nan, np.nan, 101.0, np.nan],
            "liquidity_pool_created_high": [np.nan, np.nan, np.nan, np.nan, 109.0, np.nan],
        }
    )

    result = build_zone_reaction(
        df,
        structure=structure,
        fvg=fvg,
        order_blocks=order_blocks,
        liquidity=liquidity,
    )

    assert result.loc[2, "zone_created_fvg"] == 1
    assert result.loc[3, "zone_created_order_block"] == 1
    assert result.loc[4, "zone_created_liquidity"] >= 1
    assert result.loc[4, "zone_source_count"] >= 2


def test_future_candles_cannot_rewrite_earlier_zone_reactions():
    df = frame(
        highs=[101, 102, 105, 103, 106, 105],
        lows=[99, 100, 103, 101, 104, 103],
        closes=[100, 101, 104, 102, 105, 104],
    )
    structure = structure_frame(len(df))
    altered = df.copy()
    altered.loc[5, ["high", "low", "close"]] = [1000.0, 1.0, 500.0]

    original = build_zone_reaction(df, structure=structure)
    changed = build_zone_reaction(altered, structure=structure)

    pd.testing.assert_frame_equal(original.iloc[:5], changed.iloc[:5], check_dtype=False)


def test_zone_reaction_invalid_parameters_are_rejected():
    df = frame([101, 102, 103], [99, 100, 101], [100, 101, 102])
    structure = structure_frame(len(df))

    import pytest

    with pytest.raises(ValueError):
        build_zone_reaction(df, structure=structure, reaction_threshold_pct=0)

    with pytest.raises(ValueError):
        build_zone_reaction(df, structure=structure, break_threshold_pct=-0.1)
