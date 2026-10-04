"""Deterministic bridge from normalized derivatives data to market evidence."""
from __future__ import annotations

import pandas as pd

from .market_evidence import MarketEvidence, MarketObservation


# Preferred derivatives evidence when a venue exposes it. These fields are
# NOT prerequisites for a valid AICFA setup.
DERIVATIVE_EVIDENCE_FIELDS = (
    "funding_rate",
    "open_interest",
    "mark_price",
)


def derivatives_completeness(frame: pd.DataFrame) -> tuple[bool, tuple[str, ...]]:
    """Report derivatives coverage; this is a diagnostic, not a setup veto."""
    missing: list[str] = []
    if frame is None or frame.empty:
        return False, ("derivatives: no observations",)
    for column in DERIVATIVE_EVIDENCE_FIELDS:
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
    """Append causal derivatives context without making it a setup gate.

    Price/structure/SMC remain the primary decision basis. Derivatives are
    additional mechanism/context evidence and may be complete, partial, or
    unavailable. Missing derivatives therefore goes to optional context,
    never to the structural missing-context gate.
    """
    complete, coverage_missing = derivatives_completeness(derivatives)
    observations = list(evidence.observations)
    missing_context = list(evidence.missing_context)
    optional_missing = list(evidence.optional_missing_context)

    if derivatives is None or derivatives.empty:
        optional_missing.extend(coverage_missing or ("derivatives:unavailable",))
        return MarketEvidence(
            asset=evidence.asset,
            observations=tuple(observations),
            timeframes=evidence.timeframes,
            missing_context=tuple(dict.fromkeys(missing_context)),
            conflicts=evidence.conflicts,
            optional_missing_context=tuple(dict.fromkeys(optional_missing)),
        )

    available = tuple(
        column
        for column in DERIVATIVE_EVIDENCE_FIELDS
        if column in derivatives.columns and derivatives[column].notna().any()
    )
    unavailable = tuple(
        f"derivatives:{column}:unavailable"
        for column in DERIVATIVE_EVIDENCE_FIELDS
        if column not in available
    )
    optional_missing.extend(unavailable)
    if not complete:
        optional_missing.append("derivatives:evidence:partial")

    if "timestamp" not in derivatives.columns or derivatives["timestamp"].isna().all():
        optional_missing.append("derivatives:timestamp:unavailable")
        return MarketEvidence(
            asset=evidence.asset,
            observations=tuple(observations),
            timeframes=evidence.timeframes,
            missing_context=tuple(dict.fromkeys(missing_context)),
            conflicts=evidence.conflicts,
            optional_missing_context=tuple(dict.fromkeys(optional_missing)),
        )

    # Price/OI evidence is emitted only when both OI and mark are available.
    # Funding enriches it when present; funding alone never creates direction.
    if "open_interest" in available and "mark_price" in available:
        ordered = derivatives.sort_values("timestamp").dropna(
            subset=["open_interest", "mark_price"]
        )
        if not ordered.empty:
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

            liquidation = pd.to_numeric(
                pd.Series([row.get("liquidation_volume")]), errors="coerce"
            ).iloc[0]
            long_liq = pd.to_numeric(
                pd.Series([row.get("long_liquidation_volume")]), errors="coerce"
            ).iloc[0]
            short_liq = pd.to_numeric(
                pd.Series([row.get("short_liquidation_volume")]), errors="coerce"
            ).iloc[0]
            if pd.isna(liquidation):
                optional_missing.append("derivatives:liquidation_volume:unavailable")
                optional_missing.append("derivatives:liquidations:volume_unavailable")
            else:
                liquidation_direction = None
                if pd.notna(long_liq) and pd.notna(short_liq):
                    if long_liq > short_liq:
                        liquidation_direction = "short"
                    elif short_liq > long_liq:
                        liquidation_direction = "long"
                observations.append(
                    MarketObservation(
                        concept_id="derivatives.liquidations",
                        timeframe=timeframe,
                        state="observed",
                        confidence=1.0,
                        evidence=tuple(
                            value for value in (
                                f"liquidation_volume={float(liquidation):.12g}",
                                None if pd.isna(long_liq) else f"long_liquidation_volume={float(long_liq):.12g}",
                                None if pd.isna(short_liq) else f"short_liquidation_volume={float(short_liq):.12g}",
                            ) if value is not None
                        ),
                        direction=liquidation_direction,
                        notes="optional liquidation context; never required for setup validity",
                    )
                )

            evidence_values = [
                f"open_interest={float(row['open_interest']):.12g}",
                f"mark_price={float(row['mark_price']):.12g}",
                "liquidation_stream=available" if pd.notna(liquidation) else "liquidation_stream=unavailable",
            ]
            if "funding_rate" in available and pd.notna(row.get("funding_rate")):
                evidence_values.insert(0, f"funding_rate={float(row['funding_rate']):.12g}")
            observations.append(
                MarketObservation(
                    concept_id="derivatives.price_oi",
                    timeframe=timeframe,
                    state="observed",
                    confidence=1.0,
                    evidence=tuple(evidence_values),
                    direction=direction,
                    notes="derivatives provide causal context/confirmation or contradiction; they never create a signal alone",
                )
            )
    elif available:
        optional_missing.append("derivatives:price_oi:partial")

    return MarketEvidence(
        asset=evidence.asset,
        observations=tuple(observations),
        timeframes=evidence.timeframes,
        missing_context=tuple(dict.fromkeys(missing_context)),
        conflicts=evidence.conflicts,
        optional_missing_context=tuple(dict.fromkeys(optional_missing)),
    )
