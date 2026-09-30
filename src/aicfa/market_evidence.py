"""Evidence contract for deterministic market-data analysis.

Market observations are distinct from screenshot/vision observations. They are
derived from AICFA market data and carry explicit direction only when a
deterministic market rule establishes it.
"""
from __future__ import annotations

from dataclasses import dataclass


_ALLOWED_STATES = {"observed", "possible", "not_available"}


@dataclass(frozen=True)
class MarketObservation:
    """One deterministic observation derived from market data."""

    concept_id: str
    timeframe: str
    state: str
    confidence: float
    evidence: tuple[str, ...]
    notes: str = ""
    price_location: str | None = None
    direction: str | None = None

    def __post_init__(self) -> None:
        if not self.concept_id.strip():
            raise ValueError("concept_id must not be empty")
        if not self.timeframe.strip():
            raise ValueError("timeframe must not be empty")
        if self.state not in _ALLOWED_STATES:
            raise ValueError(f"unsupported market observation state: {self.state}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if not self.evidence:
            raise ValueError("market observation requires evidence")
        if self.direction not in {None, "long", "short"}:
            raise ValueError("direction must be long, short, or None")


@dataclass(frozen=True)
class MarketEvidence:
    """Structured evidence bundle produced from real market data."""

    asset: str
    observations: tuple[MarketObservation, ...]
    timeframes: tuple[str, ...]
    source: str = "market_data"

    def __post_init__(self) -> None:
        if not self.asset.strip():
            raise ValueError("asset must not be empty")
        if not self.timeframes:
            raise ValueError("market evidence requires at least one timeframe")
        if self.source != "market_data":
            raise ValueError("MarketEvidence source must be market_data")

        keys = [(item.concept_id, item.timeframe) for item in self.observations]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate concept/timeframe market observations are not allowed")
