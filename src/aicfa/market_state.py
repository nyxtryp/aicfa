"""Canonical causal market-state representation for AICFA.

This layer does not add a score, probability, ranking, or trade decision.
It converts already-built feature/scenario/setup observations into a stable,
machine-readable current-state representation for later scanners and event
engines.
"""
from __future__ import annotations

import pandas as pd


_REQUIRED = [
    "timestamp",
    "close",
    "smc_structure_direction",
    "smc_state_ready",
    "scenario_active",
    "scenario_direction",
    "scenario_event",
    "setup_candidate_active",
    "setup_candidate_up",
    "setup_candidate_down",
    "setup_candidate_conflicted",
    "setup_direction",
]


def _numeric(df: pd.DataFrame, column: str, default: float = 0.0) -> pd.Series:
    if column not in df.columns:
        return pd.Series(default, index=df.index, dtype=float)
    return pd.to_numeric(df[column], errors="coerce").fillna(default).astype(float)


def _text(df: pd.DataFrame, column: str, default: str = "") -> pd.Series:
    if column not in df.columns:
        return pd.Series(default, index=df.index, dtype=object)
    return df[column].fillna(default).astype(str)


def build_market_state(df: pd.DataFrame) -> pd.DataFrame:
    """Build a causal, descriptive canonical market-state representation."""
    missing = [c for c in _REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required market-state columns: {missing}")

    x = (
        df.copy()
        .sort_values("timestamp")
        .drop_duplicates("timestamp")
        .reset_index(drop=True)
    )

    structure = _numeric(x, "smc_structure_direction")
    smc_ready = _numeric(x, "smc_state_ready")
    scenario_active = _numeric(x, "scenario_active").ne(0)
    scenario_direction = _numeric(x, "scenario_direction")
    setup_active = _numeric(x, "setup_candidate_active").ne(0)
    setup_up = _numeric(x, "setup_candidate_up").ne(0)
    setup_down = _numeric(x, "setup_candidate_down").ne(0)
    setup_conflicted = _numeric(x, "setup_candidate_conflicted").ne(0)
    setup_direction = _numeric(x, "setup_direction")

    out = pd.DataFrame(index=x.index)
    out["timestamp"] = x["timestamp"].to_numpy()
    out["market_state_structure_direction"] = structure.clip(-1, 1).astype("int8")
    out["market_state_scenario_active"] = scenario_active.astype("int8")
    out["market_state_scenario_direction"] = scenario_direction.clip(-1, 1).astype("int8")
    out["market_state_scenario_event"] = _text(x, "scenario_event")
    out["market_state_setup_active"] = setup_active.astype("int8")
    out["market_state_setup_up"] = setup_up.astype("int8")
    out["market_state_setup_down"] = setup_down.astype("int8")
    out["market_state_setup_conflicted"] = setup_conflicted.astype("int8")

    # Direction is copied only from the already-resolved setup layer.
    # Conflicted candidates therefore remain neutral.
    out["market_state_setup_direction"] = setup_direction.clip(-1, 1).astype("int8")

    if "setup_primary_family" in x.columns:
        out["market_state_setup_family"] = _text(x, "setup_primary_family")
    else:
        out["market_state_setup_family"] = ""

    out["market_state_smc_ready"] = smc_ready.ne(0).astype("int8")

    for source, target in [
        ("smc_premium_discount", "market_state_premium_discount"),
        ("premium", "market_state_premium"),
        ("discount", "market_state_discount"),
        ("equilibrium", "market_state_equilibrium"),
        ("volatility_regime", "market_state_volatility_regime"),
        ("volume_regime", "market_state_volume_regime"),
        ("wyckoff_state", "market_state_wyckoff_state"),
        ("pa_consolidation", "market_state_consolidation"),
        ("pa_expansion", "market_state_expansion"),
        ("cvd_delta", "market_state_cvd_available"),
        ("taker_net_volume", "market_state_taker_flow_available"),
        ("absorption_candidate", "market_state_absorption_available"),
        ("order_book_imbalance", "market_state_order_book_available"),
    ]:
        if source in x.columns:
            if target.endswith("_available"):
                out[target] = x[source].notna().astype("int8")
            elif target in {
                "market_state_premium",
                "market_state_discount",
                "market_state_equilibrium",
                "market_state_premium_discount",
            }:
                out[target] = pd.to_numeric(x[source], errors="coerce")
            else:
                out[target] = _text(x, source)
        else:
            if target.endswith("_available"):
                out[target] = pd.Series(0, index=x.index, dtype="int8")
            elif target in {
                "market_state_premium",
                "market_state_discount",
                "market_state_equilibrium",
                "market_state_premium_discount",
            }:
                out[target] = pd.Series(float("nan"), index=x.index)
            else:
                out[target] = ""

    # A compact availability mask describes which optional context sources
    # actually exist at the current row. It is a bitmask, not a confidence score.
    availability_sources = [
        ("market_state_cvd_available", 1),
        ("market_state_taker_flow_available", 2),
        ("market_state_absorption_available", 4),
        ("market_state_order_book_available", 8),
    ]
    mask = pd.Series(0, index=x.index, dtype="int16")
    for column, bit in availability_sources:
        mask = mask + out[column].astype("int16") * bit
    out["market_state_context_availability_mask"] = mask

    # Stable event-engine input: changes only when the descriptive state
    # representation itself changes. No future data is involved.
    signature_columns = [
        "market_state_structure_direction",
        "market_state_scenario_active",
        "market_state_scenario_direction",
        "market_state_scenario_event",
        "market_state_setup_active",
        "market_state_setup_up",
        "market_state_setup_down",
        "market_state_setup_conflicted",
        "market_state_setup_direction",
        "market_state_setup_family",
        "market_state_smc_ready",
        "market_state_volatility_regime",
        "market_state_volume_regime",
        "market_state_wyckoff_state",
        "market_state_context_availability_mask",
    ]
    out["market_state_changed"] = (
        out[signature_columns].astype(str).agg("|".join, axis=1)
        .ne(out[signature_columns].astype(str).agg("|".join, axis=1).shift(1))
        .astype("int8")
    )

    return out
