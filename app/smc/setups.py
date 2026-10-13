"""Deterministic §6 setup evidence scoring; never activates live setups."""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from numbers import Real


@dataclass(frozen=True, slots=True)
class SetupEvidence:
    """Boolean/ratio evidence computed by the SMC/profile pipeline for one candle."""

    liquidity_sweep: bool
    order_block_fvg_overlap: bool
    ote_overlap: bool
    higher_timeframe_bias_aligned: bool
    higher_timeframe_agreement: bool
    confirmation_volume: float
    average_volume: float
    clean_path_to_tp1: bool


@dataclass(frozen=True, slots=True)
class SetupScore:
    total: int
    maximum: int
    components: tuple[tuple[str, int], ...]


def score_setup(evidence: SetupEvidence) -> SetupScore:
    """Apply TZ §6 fixed weights (2+2+1+2+1+1+1 = 10 points)."""
    flags = (
        ("liquidity_sweep", evidence.liquidity_sweep),
        ("order_block_fvg_overlap", evidence.order_block_fvg_overlap),
        ("ote_overlap", evidence.ote_overlap),
        ("higher_timeframe_bias_aligned", evidence.higher_timeframe_bias_aligned),
        ("higher_timeframe_agreement", evidence.higher_timeframe_agreement),
        ("clean_path_to_tp1", evidence.clean_path_to_tp1),
    )
    if any(not isinstance(value, bool) for _, value in flags):
        raise ValueError("setup evidence flags must be booleans")
    for name, value in (("confirmation_volume", evidence.confirmation_volume),
                        ("average_volume", evidence.average_volume)):
        if isinstance(value, bool) or not isinstance(value, Real) or not isfinite(float(value)) or value < 0:
            raise ValueError(f"{name} must be a finite real number >= 0")

    volume_bonus = int(evidence.average_volume > 0 and
                       evidence.confirmation_volume > 1.5 * evidence.average_volume)
    weighted = (
        ("liquidity_sweep", 2 if evidence.liquidity_sweep else 0),
        ("order_block_fvg_overlap", 2 if evidence.order_block_fvg_overlap else 0),
        ("ote_overlap", 1 if evidence.ote_overlap else 0),
        ("higher_timeframe_bias_aligned", 2 if evidence.higher_timeframe_bias_aligned else 0),
        ("higher_timeframe_agreement", 1 if evidence.higher_timeframe_agreement else 0),
        ("volume_above_1_5x_average", volume_bonus),
        ("clean_path_to_tp1", 1 if evidence.clean_path_to_tp1 else 0),
    )
    return SetupScore(total=sum(points for _, points in weighted), maximum=10, components=weighted)
