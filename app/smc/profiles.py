"""Explicit, deterministic strategy profiles from TZ §5."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProfileConfig:
    name: str
    bias_timeframe: str
    zone_timeframe: str
    confirmation_timeframe: str
    extra_confirmation_timeframe: str | None
    swing_left: int
    swing_right: int
    stop_buffer_atr: float
    min_rr: float
    score_threshold: int
    lifetime_hours: int
    cooldown_minutes: int
    tradfi_cutoff_minutes: int | None


# Wider structural buffer for leveraged ETF underlyings in the configured TradFi universe.
STOP_BUFFER_ATR_OVERRIDES: dict[str, float] = {
    "SOXLUSDT": 0.5,
    "SOXSUSDT": 0.5,
    "KORUUSDT": 0.5,
    "SNXXUSDT": 0.5,
}


PROFILES: dict[str, ProfileConfig] = {
    "scalp": ProfileConfig(
        name="scalp",
        bias_timeframe="1h",
        zone_timeframe="15m",
        confirmation_timeframe="5m",
        extra_confirmation_timeframe="1m",
        swing_left=2,
        swing_right=2,
        stop_buffer_atr=0.3,
        min_rr=1.49,
        score_threshold=6,
        lifetime_hours=3,
        cooldown_minutes=30,
        tradfi_cutoff_minutes=None,
    ),
    "intraday": ProfileConfig(
        name="intraday",
        bias_timeframe="4h",
        zone_timeframe="1h",
        confirmation_timeframe="15m",
        extra_confirmation_timeframe=None,
        swing_left=3,
        swing_right=3,
        stop_buffer_atr=0.3,
        min_rr=1.49,
        score_threshold=6,
        lifetime_hours=12,
        cooldown_minutes=120,
        tradfi_cutoff_minutes=15,
    ),
}


def get_profile(name: str) -> ProfileConfig:
    """Return a known profile; unknown names are never silently defaulted."""
    if not isinstance(name, str) or name not in PROFILES:
        raise ValueError("profile must be 'scalp' or 'intraday'")
    return PROFILES[name]
