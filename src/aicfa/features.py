"""Deterministic, causal market feature engine for AICFA.

All features at row t use only candles at or before t.
Future-looking labels belong to a separate pipeline.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

EPS = 1e-12


def _merge_columns(out: pd.DataFrame, frame: pd.DataFrame, columns=None, *, prefix: str | None = None) -> pd.DataFrame:
    """Append a feature block in one DataFrame operation instead of per-column assignment."""
    if prefix is not None:
        columns = [column for column in frame.columns if column.startswith(prefix)]
    elif columns is None:
        columns = list(frame.columns)
    if not columns:
        return out
    block = frame.loc[:, columns].copy()
    block.index = out.index
    return pd.concat([out, block], axis=1)


def build_features(
    df: pd.DataFrame,
    *,
    multi_timeframe_frames: dict[str, pd.DataFrame] | None = None,
    derivatives_frame: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build causal market-state features from OHLCV candles."""
    required = ["timestamp", "open", "high", "low", "close", "volume"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    x = df[required].copy().sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)
    o=x["open"].astype(float); h=x["high"].astype(float); l=x["low"].astype(float)
    c=x["close"].astype(float); v=x["volume"].astype(float)
    out=x.copy()
    candle_range=(h-l).clip(lower=EPS); body=c-o
    out["return_1"]=c.pct_change(); out["log_return_1"]=np.log(c).diff()
    out["body"]=body; out["body_pct_range"]=body/candle_range
    out["upper_wick_pct_range"]=(h-np.maximum(o,c))/candle_range
    out["lower_wick_pct_range"]=(np.minimum(o,c)-l)/candle_range
    out["range_pct"]=candle_range/c.clip(lower=EPS)
    out["close_location"]=(c-l)/candle_range
    out["direction"]=np.sign(body).astype("int8")

    for n in (5,15,30,60):
        out[f"volatility_{n}"]=out["log_return_1"].rolling(n,min_periods=n).std()
        out[f"range_mean_{n}"]=out["range_pct"].rolling(n,min_periods=n).mean()
        out[f"volume_mean_{n}"]=v.rolling(n,min_periods=n).mean()
        out[f"relative_volume_{n}"]=v/out[f"volume_mean_{n}"].clip(lower=EPS)
        out[f"rolling_high_{n}"]=h.rolling(n,min_periods=n).max()
        out[f"rolling_low_{n}"]=l.rolling(n,min_periods=n).min()
        out[f"distance_to_high_{n}"]=(out[f"rolling_high_{n}"]-c)/c.clip(lower=EPS)
        out[f"distance_to_low_{n}"]=(c-out[f"rolling_low_{n}"])/c.clip(lower=EPS)

    out["range_expansion_15"]=out["range_pct"]/out["range_mean_15"].clip(lower=EPS)
    out["volume_expansion_15"]=out["relative_volume_15"]
    out["impulse_score_15"]=out["body_pct_range"].abs()*out["range_expansion_15"]
    out["compression_15"]=out["range_pct"]/out["range_mean_60"].clip(lower=EPS)

    dr_high=h.rolling(60,min_periods=60).max(); dr_low=l.rolling(60,min_periods=60).min()
    dr_width=(dr_high-dr_low).clip(lower=EPS)
    out["rolling_dealing_range_high"]=dr_high; out["rolling_dealing_range_low"]=dr_low
    out["rolling_dealing_range_position"]=(c-dr_low)/dr_width
    out["rolling_premium_discount"]=out["rolling_dealing_range_position"]*2.0-1.0

    from .premium_discount import build_premium_discount
    premium_discount=build_premium_discount(x)
    out = _merge_columns(out, liquidity, ["structural_dealing_range_high","structural_dealing_range_low",
                    "structural_equilibrium","structural_dealing_range_position",
                    "structural_premium_discount","premium","discount","equilibrium"]:
        out[column]=premium_discount[column].to_numpy()
    out["dealing_range_high"]=out["structural_dealing_range_high"]
    out["dealing_range_low"]=out["structural_dealing_range_low"]
    out["dealing_range_equilibrium"]=out["structural_equilibrium"]
    out["dealing_range_position"]=out["structural_dealing_range_position"]
    out["premium_discount"]=out["structural_premium_discount"]

    prev_high=h.shift(1).rolling(30,min_periods=30).max()
    prev_low=l.shift(1).rolling(30,min_periods=30).min()
    out["breakout_up"]=(h>prev_high).astype("int8")
    out["breakout_down"]=(l<prev_low).astype("int8")
    out["sweep_high_reject"]=((h>prev_high)&(c<prev_high)).astype("int8")
    out["sweep_low_reclaim"]=((l<prev_low)&(c>prev_low)).astype("int8")

    from .structure import build_structure
    structure=build_structure(x)
    out = _merge_columns(out, volume_volatility, ["swing_high","swing_low","hh","hl","lh","ll","bos_up","bos_down",
                    "choch_up","choch_down","mss_up","mss_down","swing_high_price",
                    "swing_low_price","structure_direction"]:
        out[column]=structure[column].to_numpy()

    from .liquidity import build_liquidity
    liquidity=build_liquidity(x)
    for column in [
        "equal_high","equal_low","buy_side_liquidity","sell_side_liquidity",
        "sweep_high","sweep_low","sweep_high_reclaim","sweep_low_reclaim",
        "buy_side_liquidity_price","sell_side_liquidity_price",
        "sweep_high_level","sweep_low_level",
        "previous_high","previous_low","internal_previous_high","internal_previous_low",
        "active_buy_liquidity_pools","active_sell_liquidity_pools",
        "active_external_buy_pools","active_external_sell_pools",
        "active_internal_buy_pools","active_internal_sell_pools",
        "active_buy_liquidity_price","active_sell_liquidity_price",
        "external_buy_side_liquidity","external_sell_side_liquidity",
        "internal_buy_side_liquidity","internal_sell_side_liquidity",
        "liquidity_breakout_high","liquidity_breakout_low",
        "liquidity_pool_created_high","liquidity_pool_created_low",
        "liquidity_pool_swept_high","liquidity_pool_swept_low",
        "liquidity_pool_invalidated_high","liquidity_pool_invalidated_low",
    ])

    from .displacement import build_displacement
    displacement=build_displacement(x)
    for column in ["displacement_range_expansion","displacement_body_expansion",
                    "displacement_close_efficiency","displacement_relative_volume",
                    "displacement_close_location","impulsive_close_up","impulsive_close_down",
                    "directional_displacement","displacement_up","displacement_down",
                    "displacement","displacement_bos_up","displacement_bos_down"]:
        out[column]=displacement[column].to_numpy()

    from .fvg import build_fvg
    fvg=build_fvg(x)
    for column in ["fvg_bullish","fvg_bearish","fvg","fvg_size","fvg_size_pct",
                    "fvg_displacement_bullish","fvg_displacement_bearish","fvg_mitigated",
                    "fvg_filled","fvg_invalidated","fvg_active","fvg_bullish_low",
                    "fvg_bullish_high","fvg_bearish_low","fvg_bearish_high"]:
        out[column]=fvg[column].to_numpy()

    from .order_blocks import build_order_blocks
    order_blocks=build_order_blocks(x)
    for column in ["order_block_bullish","order_block_bearish","order_block",
                    "order_block_mitigated","order_block_invalidated","order_block_active",
                    "breaker_bullish","breaker_bearish","breaker",
                    "order_block_displacement_bullish","order_block_displacement_bearish",
                    "order_block_bullish_low","order_block_bullish_high",
                    "order_block_bearish_low","order_block_bearish_high",
                    "order_block_bullish_state","order_block_bearish_state",
                    "order_block_bullish_penetration","order_block_bearish_penetration",
                    "order_block_bullish_volume_ratio","order_block_bearish_volume_ratio",
                    "order_block_bullish_volume_confirmed","order_block_bearish_volume_confirmed"]:
        out[column]=order_blocks[column].to_numpy()

    from .zone_reaction import build_zone_reaction
    zone_reaction = build_zone_reaction(
        x,
        structure=structure,
        fvg=fvg,
        order_blocks=order_blocks,
        liquidity=liquidity,
    )
    out = _merge_columns(out, zone_reaction, prefix="zone_")

    from .price_action import build_price_action
    price_action = build_price_action(x)
    out = _merge_columns(out, price_action, prefix="pa_")

    from .wyckoff import build_wyckoff
    wyckoff = build_wyckoff(x)
    out = _merge_columns(out, wyckoff, prefix="wyckoff_")

    from .volume_volatility import build_volume_volatility
    volume_volatility = build_volume_volatility(x)
    for column in [
        "realized_volatility","true_range","atr","atr_pct","range_zscore",
        "volume_zscore","relative_volume_causal","volatility_ratio",
        "volatility_expansion","volatility_compression","volume_expansion",
        "volume_dry_up","volatility_regime","volume_regime",
    ])

    if derivatives_frame is not None:
        from .derivatives import build_derivatives
        derivatives = build_derivatives(x, derivatives_frame)
        for column in derivatives.columns:
            out[column] = derivatives[column].to_numpy()

    from .volume_evidence import build_volume_evidence
    volume_evidence = build_volume_evidence(
        x, structure=structure, liquidity=liquidity, displacement=displacement
    )
    out = _merge_columns(out, volume_evidence, prefix="volume_evidence_")

    from .unified_smc import build_unified_smc
    unified_smc=build_unified_smc(x,structure=structure,liquidity=liquidity,
        displacement=displacement,fvg=fvg,order_blocks=order_blocks,
        premium_discount=premium_discount,volume_evidence=volume_evidence)
    for column in ["smc_structure_direction","smc_structure_event","smc_structure_shift",
                    "smc_liquidity_event","smc_sweep_low_reclaim","smc_sweep_high_reclaim",
                    "smc_buy_side_liquidity","smc_sell_side_liquidity",
                    "smc_external_buy_side_liquidity","smc_external_sell_side_liquidity",
                    "smc_internal_buy_side_liquidity","smc_internal_sell_side_liquidity",
                    "smc_previous_high","smc_previous_low",
                    "smc_internal_previous_high","smc_internal_previous_low",
                    "smc_active_buy_liquidity_pools","smc_active_sell_liquidity_pools",
                    "smc_active_external_buy_pools","smc_active_external_sell_pools",
                    "smc_active_internal_buy_pools","smc_active_internal_sell_pools",
                    "smc_active_buy_liquidity_price","smc_active_sell_liquidity_price",
                    "smc_liquidity_breakout_high","smc_liquidity_breakout_low",
                    "smc_liquidity_pool_created_high","smc_liquidity_pool_created_low",
                    "smc_liquidity_pool_swept_high","smc_liquidity_pool_swept_low",
                    "smc_liquidity_pool_invalidated_high","smc_liquidity_pool_invalidated_low",
                    "smc_displacement_direction","smc_displacement_bos_up",
                    "smc_displacement_bos_down","smc_fvg_event","smc_fvg_lifecycle",
                    "smc_fvg_active","smc_order_block_event","smc_order_block_lifecycle",
                    "smc_order_block_active","smc_breaker_bullish","smc_breaker_bearish",
                    "smc_dealing_range_position","smc_premium_discount","smc_premium",
                    "smc_discount","smc_equilibrium","smc_state_ready",
                    "smc_volume_evidence_relative","smc_volume_evidence_zscore",
                    "smc_volume_evidence_expansion","smc_volume_evidence_dry_up",
                    "smc_volume_evidence_breakout_up","smc_volume_evidence_breakout_down",
                    "smc_volume_evidence_rejection_high","smc_volume_evidence_rejection_low",
                    "smc_volume_evidence_liquidity_sweep_high","smc_volume_evidence_liquidity_sweep_low",
                    "smc_volume_evidence_displacement_up","smc_volume_evidence_displacement_down"]:
        out[column]=unified_smc[column].to_numpy()

    if multi_timeframe_frames is not None:
        from .multi_timeframe import build_multi_timeframe_structure
        mtf=build_multi_timeframe_structure(x,multi_timeframe_frames)
        for column in mtf.columns:
            if column.startswith("mtf_"): out[column]=mtf[column].to_numpy()

    from .scenarios import build_scenarios
    scenarios=build_scenarios(out)
    out = _merge_columns(out, scenarios, prefix="scenario_")

    from .setup_detection import build_setup_candidates
    setup_candidates = build_setup_candidates(out)
    out = _merge_columns(out, setup_candidates, prefix="setup_")

    from .market_state import build_market_state
    market_state = build_market_state(out)
    out = _merge_columns(out, market_state, prefix="market_state_")

    from .setup_events import build_setup_events
    setup_events = build_setup_events(out)
    out = _merge_columns(out, setup_events, prefix="setup_event_")

    for n in (15,60):
        out[f"return_{n}"]=c.pct_change(n)
        mean_n=c.rolling(n,min_periods=n).mean()
        out[f"close_vs_mean_{n}"]=c/mean_n.clip(lower=EPS)-1.0

    ts=pd.to_datetime(out["timestamp"],unit="ms",utc=True)
    out["hour_utc"]=ts.dt.hour.astype("int8"); out["day_of_week"]=ts.dt.dayofweek.astype("int8")
    return out
