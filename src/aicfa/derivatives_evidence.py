"""Deterministic bridge from normalized derivatives data to market evidence."""
from __future__ import annotations

import pandas as pd

from .market_evidence import MarketEvidence, MarketObservation


# Core derivatives state required for positioning evidence. Liquidations are
# useful confirmation/event context, but their absence does not invalidate the
# whole derivatives state.
REQUIRED_DERIVATIVE_FIELDS = (
    "funding_rate",
    "open_interest",
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
    """Append causal positioning evidence without fabricating signals.

    Liquidations are optional event context. When absent they are recorded in
    ``optional_missing_context`` rather than blocking the complete derivatives
    positioning observation.
    """
    complete, missing = derivatives_completeness(derivatives)
    observations = list(evidence.observations)
    missing_context = list(evidence.missing_context)
    optional_missing = list(evidence.optional_missing_context)

    if not complete:
        missing_context.extend(missing)
        return MarketEvidence(
            asset=evidence.asset,
            observations=tuple(observations),
            timeframes=evidence.timeframes,
            missing_context=tuple(dict.fromkeys(missing_context)),
            conflicts=evidence.conflicts,
            optional_missing_context=tuple(dict.fromkeys(optional_missing)),
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
            optional_missing_context=tuple(dict.fromkeys(optional_missing)),
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

    liquidation = pd.to_numeric(pd.Series([row.get("liquidation_volume")]), errors="coerce").iloc[0]
    if pd.isna(liquidation):
        optional_missing.append("derivatives:liquidation_volume:unavailable")
        optional_missing.append("derivatives:liquidations:volume_unavailable")

    observations.append(
        MarketObservation(
            concept_id="derivatives.price_oi",
            timeframe=timeframe,
            state="observed",
            confidence=1.0,
            evidence=tuple(
                value for value in (
                    f"funding_rate={float(row["funding_rate"]):.12g}",
                    f"open_interest={float(row["open_interest"]):.12g}",
                    f"mark_price={float(row["mark_price"]):.12g}",
                    "liquidation_stream=available" if pd.notna(liquidation) else "liquidation_stream=unavailable",
                )
                if value is not None
            ),
            direction=direction,
            notes="latest causally available derivatives state; liquidation data is optional event context",
        )
    )

    return MarketEvidence(
        asset=evidence.asset,
        observations=tuple(observations),
        timeframes=evidence.timeframes,
        missing_context=tuple(dict.fromkeys(missing_context)),
        conflicts=evidence.conflicts,
        optional_missing_context=tuple(dict.fromkeys(optional_missing)),
    )