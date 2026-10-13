"""Fail-closed session checks for TradFi instruments.

US-listed equities/ETFs use the official XNYS calendar, including DST, holidays,
and early closes. Instruments without a verified base-market mapping return
None and must not be accepted until their contract calendar is configured.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from functools import lru_cache
from typing import Literal

import pandas_market_calendars as mcal


# Explicitly mapped to US equity regular sessions; ambiguous symbols are not guessed.
US_EQUITY_SYMBOLS = frozenset({
    "SOXLUSDT", "KORUUSDT", "MUUSDT", "SOXSUSDT", "MSTRUSDT",
    "CRCLUSDT", "QQQUSDT", "EWYUSDT", "NVDAUSDT", "SPYUSDT",
    "SNDKUSDT", "SKHYUSDT", "SPCXUSDT",
})
KRX_EQUITY_SYMBOLS = frozenset({"SKHYNIXUSDT", "SAMSUNGUSDT"})
COMMODITY_SYMBOLS = frozenset({"XAUUSDT", "XAGUSDT", "CLUSDT", "BZUSDT", "NATGASUSDT"})
_NEW_YORK = ZoneInfo("America/New_York")


@lru_cache(maxsize=16)
def _session_bounds(day: date, calendar_name: str = "NYSE") -> tuple[tuple[datetime, datetime], ...]:
    calendar = mcal.get_calendar(calendar_name)
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


@lru_cache(maxsize=32)
def _has_us_session(day: date) -> bool:
    schedule = mcal.get_calendar("NYSE").schedule(
        start_date=day.isoformat(), end_date=day.isoformat()
    )
    return not schedule.empty


def _commodity_session_is_open(instant: datetime) -> bool:
    """Binance commodity TradFi standard-index window: Sun 18:00–Fri 17:00 ET, with daily break."""
    local = instant.astimezone(_NEW_YORK)
    day = local.date()
    clock = local.time().replace(tzinfo=None)
    weekday = local.weekday()
    if weekday == 5 or (weekday == 6 and clock < time(18, 0)):
        return False
    if weekday == 6:
        return _has_us_session(day + timedelta(days=1))
    if not _has_us_session(day):
        return False
    if weekday == 4 and clock >= time(17, 0):
        return False
    if weekday < 5 and time(17, 0) <= clock < time(18, 0):
        return False
    if clock >= time(18, 0):
        return weekday < 4 and _has_us_session(day + timedelta(days=1))
    return clock < time(17, 0)


def tradfi_market_is_open(symbol: str, now: datetime | None = None) -> bool | None:
    """True/False for mapped markets; None means no verified calendar mapping."""
    normalized = symbol.upper() if isinstance(symbol, str) else ""
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    instant = instant.astimezone(timezone.utc)
    if normalized in US_EQUITY_SYMBOLS:
        return any(opened <= instant < closed for opened, closed in _session_bounds(instant.date(), "NYSE"))
    if normalized in KRX_EQUITY_SYMBOLS:
        return any(opened <= instant < closed for opened, closed in _session_bounds(instant.date(), "XKRX"))
    if normalized in COMMODITY_SYMBOLS:
        return _commodity_session_is_open(instant)
    return None
