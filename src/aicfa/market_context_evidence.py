"""Market-data evidence bridge for microstructure and contextual layers.

This module turns already-computed causal market-data analyses into
MarketObservation objects that participate in the same evidence/scenario/setup
pipeline as SMC and derivatives evidence. It never invents values.
"""
from __future__ import annotations

import math

import pandas as pd

from .market_evidence import MarketEvidence, MarketObservation


def _number(value: object) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _latest(frame: pd.DataFrame | None) -> pd.Series | None:
    if frame is None or frame.empty:
        return None
    if "timestamp" in frame.columns:
        frame = frame.sort_values("timestamp")
    return frame.iloc[-1]


def _append(
    observations: list[MarketObservation],
    *,
    concept_id: str,
    timeframe: str,
    evidence: tuple[str, ...],
    direction: str | None = None,
    price_location: str | None = None,
    notes: str,
) -> None:
    if evidence:
        observations.append(
            MarketObservation(
                concept_id=concept_id,
                timeframe=timeframe,
                state="observed",
                confidence=1.0,
                evidence=evidence,
                direction=direction,
                price_location=price_location,
                notes=notes,
            )
        )


def append_market_context_evidence(
    evidence: MarketEvidence,
    *,
    timeframe: str,
    trades: pd.DataFrame,
    order_flow: pd.DataFrame,
    cvd: pd.DataFrame,
    order_book: pd.DataFrame,
    absorption: pd.DataFrame,
    analysis: pd.DataFrame,
    derivatives: pd.DataFrame,
) -> MarketEvidence:
    """Attach microstructure, Premium/Discount, Wyckoff and liquidation evidence.

    Every supplied layer is either represented by an observation or explicitly
    added to missing_context. The observations are consumed downstream by
    scenario/setup/decision reasoning; they are not metadata-only attachments.
    """
    observations = list(evidence.observations)
    missing = list(evidence.missing_context)
    optional_missing = list(evidence.optional_missing_context)

    if trades is None or trades.empty:
        missing.append("microstructure:trades:unavailable")
    else:
        latest_trade = _latest(trades)
        _append(
            observations,
            concept_id="microstructure.trades",
            timeframe=timeframe,
            evidence=(f"trade_count={len(trades)}",),
            notes="latest causal venue-provided trade sample used by microstructure analysis",
        )

    flow = _latest(order_flow)
    if flow is None:
        missing.append("microstructure:order_flow:unavailable")
    else:
        imbalance = _number(flow.get("taker_imbalance"))
        net = _number(flow.get("taker_net_volume"))
        direction = "long" if imbalance is not None and imbalance > 0 else "short" if imbalance is not None and imbalance < 0 else None
        _append(
            observations,
            concept_id="microstructure.order_flow",
            timeframe=timeframe,
            evidence=tuple(
                value
                for value in (
                    None if imbalance is None else f"taker_imbalance={imbalance:.12g}",
                    None if net is None else f"taker_net_volume={net:.12g}",
                )
                if value is not None
            ),
            direction=direction,
            notes="causal taker order-flow state derived from venue-provided trades",
        )
        if imbalance is None:
            missing.append("microstructure:order_flow:direction_unavailable")

    cvd_row = _latest(cvd)
    if cvd_row is None:
        missing.append("microstructure:cvd:unavailable")
    else:
        cvd_delta = _number(cvd_row.get("cvd_delta"))
        direction = "long" if cvd_delta is not None and cvd_delta > 0 else "short" if cvd_delta is not None and cvd_delta < 0 else None
        _append(
            observations,
            concept_id="microstructure.cvd",
            timeframe=timeframe,
            evidence=tuple(
                value
                for value in (
                    None if _number(cvd_row.get("cvd")) is None else f"cvd={_number(cvd_row.get('cvd')):.12g}",
                    None if cvd_delta is None else f"cvd_delta={cvd_delta:.12g}",
                )
                if value is not None
            ),
            direction=direction,
            notes="causal cumulative volume delta derived from venue-provided trades",
        )
        if cvd_delta is None:
            missing.append("microstructure:cvd:delta_unavailable")

    book = _latest(order_book)
    if book is None:
        missing.append("microstructure:order_book:unavailable")
    else:
        imbalance = _number(book.get("bid_ask_imbalance"))
        spread = _number(book.get("spread"))
        direction = "long" if imbalance is not None and imbalance > 0 else "short" if imbalance is not None and imbalance < 0 else None
        _append(
            observations,
            concept_id="microstructure.order_book",
            timeframe=timeframe,
            evidence=tuple(
                value
                for value in (
                    None if imbalance is None else f"bid_ask_imbalance={imbalance:.12g}",
                    None if spread is None else f"spread={spread:.12g}",
                )
                if value is not None
            ),
            direction=direction,
            notes="causal top-of-book state derived from venue-provided order-book snapshot",
        )
        if imbalance is None:
            missing.append("microstructure:order_book:imbalance_unavailable")

    absorption_row = _latest(absorption)
    if absorption_row is None:
        missing.append("microstructure:absorption:unavailable")
    else:
        active = bool(absorption_row.get("absorption", False))
        side = str(absorption_row.get("absorption_side", "")).lower()
        direction = "long" if active and side == "buy" else "short" if active and side == "sell" else None
        _append(
            observations,
            concept_id="microstructure.absorption",
            timeframe=timeframe,
            evidence=(
                f"absorption={active}",
                f"absorption_side={side or 'none'}",
            ),
            direction=direction,
            notes="causal absorption state derived from trade flow and historical displayed liquidity",
        )

    context = _latest(analysis)
    if context is None:
        missing.append(f"{timeframe}:context_analysis_unavailable")
    else:
        pd_value = _number(context.get("structural_premium_discount"))
        pd_location = None
        if pd_value is not None:
            pd_location = "premium" if pd_value > 0 else "discount" if pd_value < 0 else "equilibrium"
            _append(
                observations,
                concept_id="premium_discount.dealing_range",
                timeframe=timeframe,
                evidence=(
                    f"structural_premium_discount={pd_value:.12g}",
                    f"location={pd_location}",
                ),
                price_location=pd_location,
                notes="latest causal structural dealing-range position",
            )
        else:
            missing.append(f"{timeframe}:premium_discount:unavailable")

        wy_state = context.get("wyckoff_state")
        if pd.notna(wy_state):
            state = str(wy_state)
            direction = (
                "long" if state in {"spring_candidate", "sign_of_strength"} else
                "short" if state in {"upthrust_candidate", "sign_of_weakness"} else
                None
            )
            _append(
                observations,
                concept_id="wyckoff.state",
                timeframe=timeframe,
                evidence=(f"state={state}",),
                direction=direction,
                notes="causal Wyckoff-inspired observable state; not an intent claim",
            )
        else:
            missing.append(f"{timeframe}:wyckoff:unavailable")

    if derivatives is None or derivatives.empty:
        optional_missing.append("derivatives:liquidations:unavailable")
    else:
        row = _latest(derivatives)
        liquidation = _number(row.get("liquidation_volume"))
        long_liq = _number(row.get("long_liquidation_volume"))
        short_liq = _number(row.get("short_liquidation_volume"))
        if liquidation is None:
            optional_missing.append("derivatives:liquidations:volume_unavailable")
        else:
            direction = (
                "short" if long_liq is not None and short_liq is not None and long_liq > short_liq
                else "long" if long_liq is not None and short_liq is not None and short_liq > long_liq
                else None
            )
            _append(
                observations,
                concept_id="derivatives.liquidations",
                timeframe=timeframe,
                evidence=tuple(
                    value
                    for value in (
                        f"liquidation_volume={liquidation:.12g}",
                        None if long_liq is None else f"long_liquidation_volume={long_liq:.12g}",
                        None if short_liq is None else f"short_liquidation_volume={short_liq:.12g}",
                    )
                    if value is not None
                ),
                direction=direction,
                notes="latest causal liquidation-stream magnitude; direction is derived only when venue split is available",
            )

    return MarketEvidence(
        asset=evidence.asset,
        observations=tuple(observations),
        timeframes=evidence.timeframes,
        missing_context=tuple(dict.fromkeys(missing)),
        conflicts=evidence.conflicts,
        optional_missing_context=tuple(dict.fromkeys(optional_missing)),
    )
