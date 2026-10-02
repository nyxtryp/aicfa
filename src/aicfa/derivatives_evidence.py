"""Deterministic bridge from normalized derivatives data to market evidence."""
from __future__ import annotations

import pandas as pd

from .market_evidence import MarketEvidence, MarketObservation


REQUIRED_DERIVATIVE_FIELDS = (
    "funding_rate",
    "open_interest",
    "liquidation_volume",
    "mark_price",
)


def derivatives_completeness(frame: pd.DataFrame) -> tuple[bool, tuple[str, ...]]:
    missing: list[str] = []
    if frame is None or frame.empty:
        return False, ("derivatives: no observations",)
    for column in REQUIRED_DERIVATIVE_FIELDS:
        if column not in frame.columns or frame[column].notna().sum() == 0:
            missing.append(f"derivatives:{column}:unavailable")
    if "timestamp" not in frame.columns or frame["timestamp"].isna().all():
        missing.append("derivatives:timestamp:unavailable")
    return not missing, tuple(missing)


def append_derivatives_evidence(
    evidence: MarketEvidence,
    derivatives: pd.DataFrame,
    *,
    timeframe: str,
) -> MarketEvidence:
    """Append one causal positioning observation without fabricating signals."""
    complete, missing = derivatives_completeness(derivatives)
    observations = list(evidence.observations)
    missing_context = list(evidence.missing_context)

    if not complete:
        missing_context.extend(missing)
        return MarketEvidence(
            asset=evidence.asset,
            observations=tuple(observations),
            timeframes=evidence.timeframes,
            missing_context=tuple(dict.fromkeys(missing_context)),
            conflicts=evidence.conflicts,
        )

    ordered = derivatives.sort_values("timestamp").dropna(
        subset=["funding_rate", "open_interest", "mark_price"]
    )
    if ordered.empty:
        missing_context.append("derivatives:price_oi:no_causal_observation")
        return MarketEvidence(
            asset=evidence.asset,
            observations=tuple(observations),
            timeframes=evidence.timeframes,
            missing_context=tuple(dict.fromkeys(missing_context)),
            conflicts=evidence.conflicts,
        )

    row = ordered.iloc[-1]
    direction = None
    oi_delta = pd.to_numeric(
        pd.Series([row.get("open_interest_delta")]), errors="coerce"
    ).iloc[0]
    price_delta = pd.to_numeric(
        pd.Series([row.get("mark_price_delta")]), errors="coerce"
    ).iloc[0]
    if pd.notna(oi_delta) and pd.notna(price_delta):
        if oi_delta > 0 and price_delta > 0:
            direction = "long"
        elif oi_delta > 0 and price_delta < 0:
            direction = "short"

    observations.append(
        MarketObservation(
            concept_id="derivatives.price_oi",
            timeframe=timeframe,
            state="observed",
            confidence=1.0,
            evidence=(
                f"funding_rate={float(row['funding_rate']):.12g}",
                f"open_interest={float(row['open_interest']):.12g}",
                f"mark_price={float(row['mark_price']):.12g}",
                "liquidation_stream=connected",
            ),
            direction=direction,
            notes="latest causally available derivatives state; liquidation data is stream-collected",
        )
    )

    return MarketEvidence(
        asset=evidence.asset,
        observations=tuple(observations),
        timeframes=evidence.timeframes,
        missing_context=tuple(dict.fromkeys(missing_context)),
        conflicts=evidence.conflicts,
    )
