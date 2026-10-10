import pandas as pd

from aicfa.armed_zones import (
    ArmedZone,
    candle_intersects_armed_zone,
    extract_active_smc_zones,
    merge_refreshed_zones,
    zones_for_trigger_timeframe,
)


def test_extract_active_fvg_and_order_block_zones_from_latest_closed_rows():
    analyses = {
        "15m": pd.DataFrame([{
            "fvg_active_bullish_count": 2,
            "fvg_bullish_low": 99.0,
            "fvg_bullish_high": 101.0,
            "fvg_active_bearish_count": 0,
            "fvg_bearish_low": float("nan"),
            "fvg_bearish_high": float("nan"),
            "order_block_active": 1,
            "order_block_bullish_state": "UNTOUCHED",
            "order_block_bullish_low": 97.0,
            "order_block_bullish_high": 98.0,
            "order_block_bearish_state": "INVALIDATED",
            "order_block_bearish_low": 102.0,
            "order_block_bearish_high": 103.0,
        }]),
        "1m": pd.DataFrame([{
            "fvg_active_bullish_count": 1,
            "fvg_bullish_low": 100.0,
            "fvg_bullish_high": 100.5,
        }]),
    }

    zones = extract_active_smc_zones(analyses)

    assert zones == (
        ArmedZone("15m", "FVG", "bullish", 99.0, 101.0),
        ArmedZone("15m", "OB", "bullish", 97.0, 98.0),
    )


def test_candle_intersection_arms_only_when_closed_range_touches_zone():
    zones = (
        ArmedZone("15m", "FVG", "bullish", 99.0, 101.0),
        ArmedZone("1h", "OB", "bearish", 105.0, 107.0),
    )

    assert candle_intersects_armed_zone(100.5, 102.0, zones)
    assert candle_intersects_armed_zone(103.0, 106.0, zones)
    assert not candle_intersects_armed_zone(101.1, 104.9, zones)
    assert not candle_intersects_armed_zone(float("nan"), 100.0, zones)


def test_extract_active_smc_zones_ignores_missing_or_inactive_bounds():
    zones = extract_active_smc_zones({
        "1h": pd.DataFrame([{
            "fvg_active_bullish_count": 0,
            "fvg_bullish_low": 100.0,
            "fvg_bullish_high": 101.0,
            "order_block_active": 0,
            "order_block_bullish_state": "UNTOUCHED",
            "order_block_bullish_low": 98.0,
            "order_block_bullish_high": 99.0,
        }])
    })
    assert zones == ()


def test_five_minute_gate_uses_only_higher_timeframe_zones():
    zones = (
        ArmedZone("5m", "FVG", "bullish", 99.0, 100.0),
        ArmedZone("15m", "OB", "bullish", 98.0, 99.0),
        ArmedZone("1h", "FVG", "bearish", 102.0, 103.0),
    )

    five_minute = zones_for_trigger_timeframe(zones, "5m")
    one_minute = zones_for_trigger_timeframe(zones, "1m")

    assert [zone.timeframe for zone in five_minute] == ["15m", "1h"]
    assert one_minute == zones


def test_zone_refresh_replaces_only_timeframes_in_new_snapshot():
    old = (
        ArmedZone("5m", "FVG", "bullish", 99.0, 100.0),
        ArmedZone("15m", "OB", "bullish", 98.0, 99.0),
        ArmedZone("1h", "FVG", "bearish", 102.0, 103.0),
    )
    refreshed = (ArmedZone("1h", "OB", "bullish", 95.0, 96.0),)

    merged = merge_refreshed_zones(old, refreshed, ("1h", "4h"))

    assert merged == (
        old[0],
        old[1],
        refreshed[0],
    )



def test_weekly_order_block_is_available_to_lower_timeframe_gates():
    zones = extract_active_smc_zones({
        "1w": pd.DataFrame([{
            "fvg_active_bullish_count": 1,
            "fvg_bullish_low": 100.0,
            "fvg_bullish_high": 105.0,
            "order_block_active": 0,
        }])
    })
    assert zones == (ArmedZone("1w", "FVG", "bullish", 100.0, 105.0),)
    assert zones_for_trigger_timeframe(zones, "5m") == zones



def test_active_liquidity_levels_and_ote_bands_arm_lower_timeframe_scans():
    zones = extract_active_smc_zones({
        "1h": pd.DataFrame([{
            "fvg_active_bullish_count": 0,
            "fvg_active_bearish_count": 0,
            "order_block_active": 0,
            "active_buy_liquidity_pools": 1,
            "active_buy_liquidity_price": 101.0,
            "active_sell_liquidity_pools": 1,
            "active_sell_liquidity_price": 99.0,
            "structural_dealing_range_high": 110.0,
            "structural_dealing_range_low": 90.0,
        }])
    })

    assert ArmedZone("1h", "LIQUIDITY", "buy_side", 101.0, 101.0) in zones
    assert ArmedZone("1h", "LIQUIDITY", "sell_side", 99.0, 99.0) in zones
    assert ArmedZone("1h", "OTE", "bullish", 94.2, 97.6) in zones
    assert ArmedZone("1h", "OTE", "bearish", 102.4, 105.8) in zones
    assert candle_intersects_armed_zone(100.5, 101.2, zones)
    assert candle_intersects_armed_zone(95.0, 95.5, zones)


def test_structural_levels_arm_bos_and_sweep_candles():
    zones = extract_active_smc_zones({
        "1h": pd.DataFrame([{
            "swing_high_price": 101.0,
            "swing_low_price": 95.0,
            "previous_high": 102.0,
            "previous_low": 94.0,
            "sweep_high_level": 100.5,
            "sweep_low_level": 95.5,
        }])
    })
    assert ArmedZone("1h", "STRUCTURE", "swing_high_price", 101.0, 101.0) in zones
    assert ArmedZone("1h", "STRUCTURE", "sweep_low_level", 95.5, 95.5) in zones
    assert candle_intersects_armed_zone(100.8, 101.4, zones)
    assert candle_intersects_armed_zone(95.0, 95.6, zones)
