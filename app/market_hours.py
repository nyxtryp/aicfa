"""Fail-closed session checks for TradFi instruments.

US-listed equities/ETFs use the official XNYS calendar, including DST, holidays,
and early closes. Instruments without a verified base-market mapping return
None and must not be accepted until their contract calendar is configured.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from typing import Literal

import pandas_market_calendars as mcal


# Explicitly mapped to US equity regular sessions; ambiguous symbols are not guessed.
US_EQUITY_SYMBOLS = frozenset({
    "SOXLUSDT", "KORUUSDT", "MUUSDT", "SOXSUSDT", "MSTRUSDT",
    "CRCLUSDT", "QQQUSDT", "EWYUSDT", "NVDAUSDT", "SPYUSDT",
    "SNDKUSDT",
})


@lru_cache(maxsize=16)
def _session_bounds(day: date) -> tuple[tuple[datetime, datetime], ...]:
    calendar = mcal.get_calendar("NYSE")
    schedule = calendar.schedule(
        start_date=(day - timedelta(days=1)).isoformat(),
        end_date=(day + timedelta(days=1)).isoformat(),
    )
    bounds = []
    for _, row in schedule.iterrows():
        opened = row["market_open"].to_pydatetime().astimezone(timezone.utc)
        closed = row["market_close"].to_pydatetime().astimezone(timezone.utc)
        bounds.append((opened, closed))
    return tuple(bounds)


def tradfi_market_is_open(symbol: str, now: datetime | None = None) -> bool | None:
    """True/False for a mapped US equity; None means no verified calendar mapping."""
    normalized = symbol.upper() if isinstance(symbol, str) else ""
    if normalized not in US_EQUITY_SYMBOLS:
        return None
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    instant = instant.astimezone(timezone.utc)
    return any(opened <= instant < closed for opened, closed in _session_bounds(instant.date()))
