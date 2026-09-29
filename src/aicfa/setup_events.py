"""Causal setup-event lifecycle for AICFA.

Events describe transitions in the canonical market state. They do not create
scores, probabilities, trade instructions, or future-looking live labels.
"""
from __future__ import annotations

import pandas as pd


def _text(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series("", index=df.index, dtype=object)
    return df[column].fillna("").astype(str)


def _num(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series(0, index=df.index, dtype="int8")
    return pd.to_numeric(df[column], errors="coerce").fillna(0).astype("int8")


def build_setup_events(state: pd.DataFrame) -> pd.DataFrame:
    required = [
        "timestamp",
        "market_state_setup_active",
        "market_state_setup_direction",
        "market_state_setup_conflicted",
        "market_state_setup_family",
    ]
    missing = [c for c in required if c not in state.columns]
    if missing:
        raise ValueError(f"Missing required market-state columns: {missing}")

    x = (
        state.copy()
        .sort_values("timestamp")
        .drop_duplicates("timestamp")
        .reset_index(drop=True)
    )

    active = _num(x, "market_state_setup_active").ne(0)
    direction = _num(x, "market_state_setup_direction")
    conflicted = _num(x, "market_state_setup_conflicted").ne(0)
    family = _text(x, "market_state_setup_family")

    # A live setup identity is the descriptive family + resolved direction.
    # Conflicts have no active identity and therefore cannot generate a
    # directional event.
    identity = family.where(active & ~conflicted & direction.ne(0), "")
    identity = identity + "|" + direction.where(identity.ne(""), 0).astype(str)

    previous_identity = identity.shift(1).fillna("")
    previous_active = previous_identity.ne("")

    created = active & ~conflicted & direction.ne(0) & ~previous_active
    same_identity = identity.ne("") & identity.eq(previous_identity)
    strengthened = same_identity & (
        _num(x, "market_state_changed").ne(0)
    )
    invalidated = previous_active & (
        identity.eq("") | identity.ne(previous_identity)
    ) & ~created
    expired = invalidated & ~active

    # When a new setup replaces an old one, emit the old lifecycle transition
    # as invalidated and the new one as created on the same observation.
    event = pd.Series("", index=x.index, dtype=object)
    event.loc[created] = "created"
    event.loc[strengthened] = "strengthened"
    event.loc[invalidated] = "invalidated"
    event.loc[expired] = "expired"

    out = pd.DataFrame(index=x.index)
    out["timestamp"] = x["timestamp"].to_numpy()
    out["setup_event_active"] = active.astype("int8")
    out["setup_event_direction"] = direction.where(active & ~conflicted, 0).astype("int8")
    out["setup_event_family"] = family.where(active & ~conflicted, "")
    out["setup_event_identity"] = identity
    out["setup_event_created"] = created.astype("int8")
    out["setup_event_strengthened"] = strengthened.astype("int8")
    out["setup_event_invalidated"] = invalidated.astype("int8")
    out["setup_event_expired"] = expired.astype("int8")
    out["setup_event_type"] = event

    # Live event state has no future outcome. Outcome labels belong to the
    # separate historical label/validation pipeline.
    out["setup_event_outcome"] = ""

    return out
