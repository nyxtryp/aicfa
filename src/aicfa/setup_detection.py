"""Causal setup-candidate detection for AICFA.

This layer combines already-built market-state observations into explicit,
descriptive setup candidates. It does not score setups, predict outcomes, or
emit trading instructions. Every value at row t uses only data available at t.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _flag(x: pd.DataFrame, column: str) -> pd.Series:
    if column not in x.columns:
        return pd.Series(0, index=x.index, dtype="int8")
    return x[column].fillna(0).astype(float).ne(0).astype("int8")


def _numeric(x: pd.DataFrame, column: str) -> pd.Series:
    if column not in x.columns:
        return pd.Series(np.nan, index=x.index, dtype=float)
    return pd.to_numeric(x[column], errors="coerce").astype(float)


def build_setup_candidates(df: pd.DataFrame) -> pd.DataFrame:
    """Build causal, descriptive setup candidates from market-state features."""
    required = ["timestamp", "open", "high", "low", "close"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required setup-state columns: {missing}")

    x = (
        df.copy()
        .sort_values("timestamp")
        .drop_duplicates("timestamp")
        .reset_index(drop=True)
    )
    for column in ["open", "high", "low", "close"]:
        x[column] = x[column].astype(float)
    if (x["high"] < x[["open", "close"]].max(axis=1)).any():
        raise ValueError("Invalid OHLC: high is below open/close")
    if (x["low"] > x[["open", "close"]].min(axis=1)).any():
        raise ValueError("Invalid OHLC: low is above open/close")

    out = x.copy()

    sweep_low_reclaim = _flag(x, "smc_sweep_low_reclaim")
    sweep_high_reclaim = _flag(x, "smc_sweep_high_reclaim")
    structure_shift = _numeric(x, "smc_structure_shift").fillna(0)
    structure_direction = _numeric(x, "smc_structure_direction").fillna(0)
    displacement = _numeric(x, "smc_displacement_direction").fillna(0)
    bos_up = _flag(x, "smc_displacement_bos_up")
    bos_down = _flag(x, "smc_displacement_bos_down")

    pa_bull_rejection = _flag(x, "pa_bullish_rejection")
    pa_bear_rejection = _flag(x, "pa_bearish_rejection")
    pa_retest_up = _flag(x, "pa_retest_up")
    pa_retest_down = _flag(x, "pa_retest_down")
    pa_failed_up = _flag(x, "pa_failed_breakout_up")
    pa_failed_down = _flag(x, "pa_failed_breakout_down")

    spring = _flag(x, "wyckoff_spring")
    upthrust = _flag(x, "wyckoff_upthrust")
    expansion_up = _flag(x, "scenario_expansion_up")
    expansion_down = _flag(x, "scenario_expansion_down")

    out["setup_liquidity_reversal_up"] = (
        sweep_low_reclaim.eq(1)
        & (structure_shift.eq(1) | pa_bull_rejection.eq(1) | spring.eq(1))
    ).astype("int8")
    out["setup_liquidity_reversal_down"] = (
        sweep_high_reclaim.eq(1)
        & (structure_shift.eq(-1) | pa_bear_rejection.eq(1) | upthrust.eq(1))
    ).astype("int8")

    out["setup_structure_continuation_up"] = (
        structure_direction.eq(1) & displacement.eq(1) & bos_up.eq(1)
    ).astype("int8")
    out["setup_structure_continuation_down"] = (
        structure_direction.eq(-1) & displacement.eq(-1) & bos_down.eq(1)
    ).astype("int8")

    out["setup_breakout_retest_up"] = (
        pa_retest_up.eq(1) & structure_direction.eq(1)
    ).astype("int8")
    out["setup_breakout_retest_down"] = (
        pa_retest_down.eq(1) & structure_direction.eq(-1)
    ).astype("int8")

    out["setup_failed_breakout_up"] = pa_failed_up
    out["setup_failed_breakout_down"] = pa_failed_down
    out["setup_wyckoff_spring"] = spring
    out["setup_wyckoff_upthrust"] = upthrust
    out["setup_expansion_up"] = expansion_up
    out["setup_expansion_down"] = expansion_down

    context_flags = {
        "setup_fvg_bullish_context": "fvg_bullish",
        "setup_fvg_bearish_context": "fvg_bearish",
        "setup_fvg_active_context": "fvg_active",
        "setup_order_block_bullish_context": "order_block_bullish",
        "setup_order_block_bearish_context": "order_block_bearish",
        "setup_order_block_active_context": "order_block_active",
        "setup_premium_context": "premium",
        "setup_discount_context": "discount",
        "setup_absorption_context": "absorption_candidate",
        "setup_cvd_positive_context": "cvd_delta",
        "setup_taker_positive_context": "taker_net_volume",
        "setup_derivatives_context": "oi_price_up_up",
    }
    for output, source in context_flags.items():
        if source in x.columns:
            values = pd.to_numeric(x[source], errors="coerce").fillna(0).astype(float)
            if output in {"setup_cvd_positive_context", "setup_taker_positive_context"}:
                out[output] = values.gt(0).astype("int8")
            else:
                out[output] = values.ne(0).astype("int8")
        else:
            out[output] = pd.Series(0, index=x.index, dtype="int8")

    up_families = [
        "setup_liquidity_reversal_up", "setup_structure_continuation_up",
        "setup_breakout_retest_up", "setup_failed_breakout_down",
        "setup_wyckoff_spring", "setup_expansion_up",
    ]
    down_families = [
        "setup_liquidity_reversal_down", "setup_structure_continuation_down",
        "setup_breakout_retest_down", "setup_failed_breakout_up",
        "setup_wyckoff_upthrust", "setup_expansion_down",
    ]

    up_matrix = np.column_stack([out[c].to_numpy(bool) for c in up_families])
    down_matrix = np.column_stack([out[c].to_numpy(bool) for c in down_families])
    any_up = up_matrix.any(axis=1)
    any_down = down_matrix.any(axis=1)

    out["setup_candidate_up"] = (any_up & ~any_down).astype("int8")
    out["setup_candidate_down"] = (any_down & ~any_up).astype("int8")
    out["setup_candidate_conflicted"] = (any_up & any_down).astype("int8")
    out["setup_candidate_active"] = (any_up | any_down).astype("int8")

    family_definitions = [
        (
            "liquidity_reversal",
            ["setup_liquidity_reversal_up", "setup_liquidity_reversal_down"],
        ),
        (
            "structure_continuation",
            ["setup_structure_continuation_up", "setup_structure_continuation_down"],
        ),
        (
            "breakout_retest",
            ["setup_breakout_retest_up", "setup_breakout_retest_down"],
        ),
        (
            "failed_breakout",
            ["setup_failed_breakout_up", "setup_failed_breakout_down"],
        ),
        (
            "wyckoff",
            ["setup_wyckoff_spring", "setup_wyckoff_upthrust"],
        ),
        (
            "expansion",
            ["setup_expansion_up", "setup_expansion_down"],
        ),
    ]
    family_matrix = np.column_stack([
        out[columns[0]].to_numpy(bool) | out[columns[1]].to_numpy(bool)
        for _, columns in family_definitions
    ])
    family_count = family_matrix.sum(axis=1)
    labels = np.array([name for name, _ in family_definitions], dtype=object)
    out["setup_primary_family"] = np.where(
        family_count == 1, labels[family_matrix.argmax(axis=1)], ""
    )

    direction = np.where(any_up & ~any_down, 1, np.where(any_down & ~any_up, -1, 0))
    out["setup_direction"] = direction.astype("int8")

    low_level = _numeric(x, "smc_sweep_low_level")
    high_level = _numeric(x, "smc_sweep_high_level")
    prior_low = _numeric(x, "previous_low")
    prior_high = _numeric(x, "previous_high")
    out["setup_reference_price"] = np.where(
        direction > 0, low_level.fillna(prior_low),
        np.where(direction < 0, high_level.fillna(prior_high), np.nan)
    )
    out["setup_invalidation_price"] = out["setup_reference_price"]

    return out
