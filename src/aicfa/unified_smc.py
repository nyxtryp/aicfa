"""Causal unified SMC market-state representation for AICFA.

This module does not turn SMC observations into a BUY/SELL score. It
normalizes the independently causal engines into one prefixed state frame so
later multi-timeframe, scenario, dataset, and model layers can consume a
consistent representation.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def build_unified_smc(
    df: pd.DataFrame,
    *,
    structure: pd.DataFrame | None = None,
    liquidity: pd.DataFrame | None = None,
    displacement: pd.DataFrame | None = None,
    fvg: pd.DataFrame | None = None,
    order_blocks: pd.DataFrame | None = None,
    premium_discount: pd.DataFrame | None = None,
    volume_evidence: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Build a causal unified SMC state from already-causal components.

    No directional verdict or confirmation-count score is produced. Each
    component remains an observable state/event so historical relationships
    can be measured statistically later.
    """
    required = ["timestamp", "open", "high", "low", "close", "volume"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    x = df[required].copy().sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)
    for column in required[1:]:
        x[column] = x[column].astype(float)
    if (x["high"] < x[["open", "close"]].max(axis=1)).any():
        raise ValueError("Invalid OHLC: high is below open/close")
    if (x["low"] > x[["open", "close"]].min(axis=1)).any():
        raise ValueError("Invalid OHLC: low is above open/close")
    if (x["volume"] < 0).any():
        raise ValueError("Invalid volume: negative values are not allowed")

    if displacement is None:
        from .displacement import build_displacement
        displacement = build_displacement(x)
    if structure is None:
        from .structure import build_structure
        structure = build_structure(x, displacement=displacement)
    if liquidity is None:
        from .liquidity import build_liquidity
        liquidity = build_liquidity(x)
    if fvg is None:
        from .fvg import build_fvg
        fvg = build_fvg(x)
    if order_blocks is None:
        from .order_blocks import build_order_blocks
        order_blocks = build_order_blocks(x)
    if premium_discount is None:
        from .premium_discount import build_premium_discount
        premium_discount = build_premium_discount(x)
    if volume_evidence is None:
        from .volume_evidence import build_volume_evidence
        volume_evidence = build_volume_evidence(
            x, structure=structure, liquidity=liquidity, displacement=displacement
        )

    n = len(x)
    out = x.copy()

    def copy_column(frame: pd.DataFrame, source: str, target: str, default: float = 0.0) -> None:
        if source in frame.columns:
            values = frame[source].to_numpy()
            if len(values) != n:
                raise ValueError(f"Component length mismatch for {source}")
            out[target] = values
        else:
            out[target] = default

    # Structure: direction and discrete break/shift events remain separate.
    copy_column(structure, "structure_direction", "smc_structure_direction")
    structure_bos_up = structure["bos_up"].to_numpy() if "bos_up" in structure.columns else np.zeros(n, dtype="int8")
    structure_bos_down = structure["bos_down"].to_numpy() if "bos_down" in structure.columns else np.zeros(n, dtype="int8")
    structure_choch_up = structure["choch_up"].to_numpy() if "choch_up" in structure.columns else np.zeros(n, dtype="int8")
    structure_choch_down = structure["choch_down"].to_numpy() if "choch_down" in structure.columns else np.zeros(n, dtype="int8")
    out["smc_structure_event"] = np.select(
        [structure_bos_up == 1, structure_bos_down == 1],
        [1, -1],
        default=0,
    ).astype("int8")
    out["smc_structure_shift"] = np.select(
        [structure_choch_up == 1, structure_choch_down == 1],
        [1, -1],
        default=0,
    ).astype("int8")

    # Refined Market Structure: preserve external and internal observations
    # separately so downstream layers can choose the required sensitivity.
    for source, target in [
        ("internal_swing_high", "smc_internal_swing_high"),
        ("internal_swing_low", "smc_internal_swing_low"),
        ("internal_hh", "smc_internal_hh"),
        ("internal_hl", "smc_internal_hl"),
        ("internal_lh", "smc_internal_lh"),
        ("internal_ll", "smc_internal_ll"),
        ("internal_bos_up", "smc_internal_bos_up"),
        ("internal_bos_down", "smc_internal_bos_down"),
        ("internal_choch_up", "smc_internal_choch_up"),
        ("internal_choch_down", "smc_internal_choch_down"),
        ("internal_structure_direction", "smc_internal_structure_direction"),
    ]:
        copy_column(structure, source, target)

    # MSS is distinct from CHoCH: it is only populated by the causal
    # displacement-aware structure engine.
    copy_column(structure, "mss_up", "smc_mss_up")
    copy_column(structure, "mss_down", "smc_mss_down")

    # Protected levels are structural state, not trade signals.
    for source, target in [
        ("protected_high_price", "smc_protected_high_price"),
        ("protected_low_price", "smc_protected_low_price"),
        ("protected_high_active", "smc_protected_high_active"),
        ("protected_low_active", "smc_protected_low_active"),
        ("protected_high_created", "smc_protected_high_created"),
        ("protected_low_created", "smc_protected_low_created"),
        ("protected_high_broken", "smc_protected_high_broken"),
        ("protected_low_broken", "smc_protected_low_broken"),
    ]:
        default = np.nan if source.endswith("_price") else 0.0
        copy_column(structure, source, target, default)

    # Liquidity: a high sweep is represented as a buy-side sweep event (-1),
    # a low sweep as a sell-side sweep event (+1). Reclaim is retained as a
    # separate binary observation rather than folded into a directional score.
    out["smc_liquidity_event"] = np.select(
        [liquidity["sweep_low"].to_numpy() == 1, liquidity["sweep_high"].to_numpy() == 1],
        [1, -1],
        default=0,
    ).astype("int8")
    copy_column(liquidity, "sweep_low_reclaim", "smc_sweep_low_reclaim")
    copy_column(liquidity, "sweep_high_reclaim", "smc_sweep_high_reclaim")
    for source, target in [
        ("buy_side_liquidity", "smc_buy_side_liquidity"),
        ("sell_side_liquidity", "smc_sell_side_liquidity"),
        ("external_buy_side_liquidity", "smc_external_buy_side_liquidity"),
        ("external_sell_side_liquidity", "smc_external_sell_side_liquidity"),
        ("internal_buy_side_liquidity", "smc_internal_buy_side_liquidity"),
        ("internal_sell_side_liquidity", "smc_internal_sell_side_liquidity"),
        ("previous_high", "smc_previous_high"),
        ("previous_low", "smc_previous_low"),
        ("internal_previous_high", "smc_internal_previous_high"),
        ("internal_previous_low", "smc_internal_previous_low"),
        ("active_buy_liquidity_pools", "smc_active_buy_liquidity_pools"),
        ("active_sell_liquidity_pools", "smc_active_sell_liquidity_pools"),
        ("active_external_buy_pools", "smc_active_external_buy_pools"),
        ("active_external_sell_pools", "smc_active_external_sell_pools"),
        ("active_internal_buy_pools", "smc_active_internal_buy_pools"),
        ("active_internal_sell_pools", "smc_active_internal_sell_pools"),
        ("active_buy_liquidity_price", "smc_active_buy_liquidity_price"),
        ("active_sell_liquidity_price", "smc_active_sell_liquidity_price"),
        ("liquidity_breakout_high", "smc_liquidity_breakout_high"),
        ("liquidity_breakout_low", "smc_liquidity_breakout_low"),
        ("liquidity_pool_created_high", "smc_liquidity_pool_created_high"),
        ("liquidity_pool_created_low", "smc_liquidity_pool_created_low"),
        ("liquidity_pool_swept_high", "smc_liquidity_pool_swept_high"),
        ("liquidity_pool_swept_low", "smc_liquidity_pool_swept_low"),
        ("liquidity_pool_invalidated_high", "smc_liquidity_pool_invalidated_high"),
        ("liquidity_pool_invalidated_low", "smc_liquidity_pool_invalidated_low"),
    ]:
        default = np.nan if source.endswith("_price") or source in {
            "previous_high", "previous_low", "internal_previous_high", "internal_previous_low"
        } else 0.0
        copy_column(liquidity, source, target, default)

    # Displacement is an event direction, not a prediction.
    out["smc_displacement_direction"] = np.select(
        [displacement["displacement_up"].to_numpy() == 1, displacement["displacement_down"].to_numpy() == 1],
        [1, -1],
        default=0,
    ).astype("int8")
    copy_column(displacement, "displacement_bos_up", "smc_displacement_bos_up")
    copy_column(displacement, "displacement_bos_down", "smc_displacement_bos_down")

    # FVG: creation direction and lifecycle events are intentionally separate.
    out["smc_fvg_event"] = np.select(
        [fvg["fvg_bullish"].to_numpy() == 1, fvg["fvg_bearish"].to_numpy() == 1],
        [1, -1],
        default=0,
    ).astype("int8")
    out["smc_fvg_lifecycle"] = np.select(
        [
            fvg["fvg_invalidated"].to_numpy() == 1,
            fvg["fvg_filled"].to_numpy() == 1,
            fvg["fvg_mitigated"].to_numpy() == 1,
        ],
        [-1, 2, 1],
        default=0,
    ).astype("int8")
    copy_column(fvg, "fvg_active", "smc_fvg_active")

    # Order Block: creation direction and lifecycle events are separate; the
    # OB remains an observed structural object, never a BUY/SELL signal.
    out["smc_order_block_event"] = np.select(
        [
            order_blocks["order_block_bullish"].to_numpy() == 1,
            order_blocks["order_block_bearish"].to_numpy() == 1,
        ],
        [1, -1],
        default=0,
    ).astype("int8")
    out["smc_order_block_lifecycle"] = np.select(
        [
            order_blocks["order_block_invalidated"].to_numpy() == 1,
            order_blocks["order_block_mitigated"].to_numpy() == 1,
        ],
        [-1, 1],
        default=0,
    ).astype("int8")
    copy_column(order_blocks, "order_block_active", "smc_order_block_active")
    copy_column(order_blocks, "breaker_bullish", "smc_breaker_bullish")
    copy_column(order_blocks, "breaker_bearish", "smc_breaker_bearish")

    # Volume Evidence remains a set of observable, causal measurements.
    # It is propagated without collapsing the evidence into a score/verdict.
    for source in [
        "volume_evidence_relative", "volume_evidence_zscore",
        "volume_evidence_expansion", "volume_evidence_dry_up",
        "volume_evidence_breakout_up", "volume_evidence_breakout_down",
        "volume_evidence_rejection_high", "volume_evidence_rejection_low",
        "volume_evidence_liquidity_sweep_high", "volume_evidence_liquidity_sweep_low",
        "volume_evidence_displacement_up", "volume_evidence_displacement_down",
    ]:
        copy_column(volume_evidence, source, "smc_" + source)

    # Structural Premium/Discount is already causal and is carried into the
    # unified representation without converting it into a trade verdict.
    copy_column(premium_discount, "structural_dealing_range_position", "smc_dealing_range_position", np.nan)
    copy_column(premium_discount, "structural_premium_discount", "smc_premium_discount", np.nan)
    copy_column(premium_discount, "premium", "smc_premium")
    copy_column(premium_discount, "discount", "smc_discount")
    copy_column(premium_discount, "equilibrium", "smc_equilibrium")

    # A readiness flag means the unified representation has a confirmed
    # structural range. It is not a trade signal.
    out["smc_state_ready"] = (
        out["smc_dealing_range_position"].notna()
        & out["smc_premium_discount"].notna()
    ).astype("int8")

    return out
