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


@dataclass(frozen=True, slots=True)
class CandidateDecision:
    """Pure eligibility result; ELIGIBLE is not persisted or activated live."""

    status: str
    score: SetupScore
    entry_limit: float | None
    risk_reward: float | None
    reasons: tuple[str, ...]


def evaluate_candidate(
    evidence: SetupEvidence,
    *,
    direction: str,
    higher_timeframe_bias: str,
    premium_discount_zone: str,
    zone_intersects_ote: bool,
    confirmation_aligned: bool,
    one_minute_confirmed: bool,
    profile: str,
    entry_price: float,
    current_price: float,
    stop_price: float,
    tp1_price: float,
    min_rr: float | None = None,
    tick_size: float,
    min_stop_distance: float,
    score_threshold: int | None = None,
    data_fresh: bool,
    tradfi_market_open: bool = True,
    duplicate: bool = False,
    cooldown_active: bool = False,
    active_count: int = 0,
    max_active: int = 8,
) -> CandidateDecision:
    """Evaluate §6–7 gates without storing, notifying, or activating a setup."""
    from app.smc.profiles import get_profile
    from app.smc.risk import acceptable_entry_limit, calculate_risk_reward

    side = direction.lower() if isinstance(direction, str) else ""
    bias = higher_timeframe_bias.lower() if isinstance(higher_timeframe_bias, str) else ""
    zone = premium_discount_zone.lower() if isinstance(premium_discount_zone, str) else ""
    profile_name = profile.lower() if isinstance(profile, str) else ""
    profile_config = None
    try:
        profile_config = get_profile(profile_name)
    except ValueError:
        pass
    if profile_config is not None:
        if min_rr is None:
            min_rr = profile_config.min_rr
        if score_threshold is None:
            score_threshold = profile_config.score_threshold
    score = score_setup(evidence)
    reasons: list[str] = []

    if side not in {"long", "short"}:
        reasons.append("invalid_direction")
    if bias != side:
        reasons.append("higher_timeframe_bias_conflict")
    required_zone = "discount" if side == "long" else "premium"
    if zone != required_zone:
        reasons.append("wrong_premium_discount_zone")
    if not isinstance(zone_intersects_ote, bool) or not zone_intersects_ote:
        reasons.append("zone_does_not_intersect_ote")
    if not evidence.liquidity_sweep:
        reasons.append("liquidity_sweep_missing")
    if not isinstance(confirmation_aligned, bool) or not confirmation_aligned:
        reasons.append("confirmation_not_aligned")
    if profile_config is None:
        reasons.append("invalid_profile")
    elif profile_config.extra_confirmation_timeframe is not None and (
        not isinstance(one_minute_confirmed, bool) or not one_minute_confirmed
    ):
        reasons.append("one_minute_confirmation_missing")
    if isinstance(score_threshold, bool) or not isinstance(score_threshold, int) or not 0 <= score_threshold <= 10:
        reasons.append("invalid_score_threshold")
    elif score.total < score_threshold:
        reasons.append("score_below_threshold")
    if not isinstance(data_fresh, bool) or not data_fresh:
        reasons.append("market_data_stale_or_incomplete")
    if not isinstance(tradfi_market_open, bool) or not tradfi_market_open:
        reasons.append("tradfi_market_closed")
    if not isinstance(duplicate, bool) or duplicate:
        reasons.append("duplicate_setup")
    if not isinstance(cooldown_active, bool) or cooldown_active:
        reasons.append("cooldown_active")
    if isinstance(active_count, bool) or not isinstance(active_count, int) or active_count < 0:
        reasons.append("invalid_active_count")
    elif isinstance(max_active, bool) or not isinstance(max_active, int) or max_active < 1 or active_count >= max_active:
        reasons.append("active_setup_limit_reached")

    entry_limit = None
    rr = None
    try:
        entry = _finite_price("entry_price", entry_price)
        current = _finite_price("current_price", current_price)
        stop = _finite_price("stop_price", stop_price)
        target = _finite_price("tp1_price", tp1_price)
        min_stop = _finite_price("min_stop_distance", min_stop_distance)
        if min_stop < 0:
            raise ValueError("min_stop_distance must be >= 0")
        if abs(entry - stop) < min_stop:
            reasons.append("stop_distance_below_minimum")
        rr = calculate_risk_reward(side, entry, stop, target)
        entry_limit = acceptable_entry_limit(side, target, stop, min_rr=min_rr, tick_size=tick_size)
        missed = current > entry_limit if side == "long" else current < entry_limit
        if rr < min_rr:
            reasons.append("risk_reward_below_minimum")
        if missed:
            reasons.append("price_beyond_acceptable_entry")
    except (ValueError, TypeError, ArithmeticError):
        reasons.append("invalid_price_or_risk_parameters")
        missed = False

    if reasons:
        status = "MISSED_PRICE" if missed and reasons == ["price_beyond_acceptable_entry"] else "REJECTED"
    else:
        status = "ELIGIBLE"
    return CandidateDecision(status, score, entry_limit, rr, tuple(reasons))


def _finite_price(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, Real) or not isfinite(float(value)):
        raise ValueError(f"{name} must be a finite real number")
    return float(value)
