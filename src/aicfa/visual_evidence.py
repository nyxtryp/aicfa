from dataclasses import dataclass
from typing import Iterable


_ALLOWED_STATES = {"observed", "possible", "not_visible"}


@dataclass(frozen=True)
class VisualObservation:
    """A concept observation produced from a user-supplied chart image.

    This is an inference-time evidence contract. It is not a manually supplied
    label, training example, or trade signal.
    """

    concept_id: str
    state: str
    confidence: float
    evidence: tuple[str, ...]
    notes: str = ""
    price_location: str | None = None
    direction: str | None = None

    def __post_init__(self) -> None:
        if not self.concept_id.strip():
            raise ValueError("concept_id must not be empty")
        if self.state not in _ALLOWED_STATES:
            raise ValueError(f"unsupported visual observation state: {self.state}")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if not self.evidence:
            raise ValueError("visual observation requires evidence")
        if self.direction not in {None, "long", "short"}:
            raise ValueError("direction must be long, short, or None")


@dataclass(frozen=True)
class VisualEvidence:
    """Structured evidence extracted by AICFA from one chart screenshot."""

    asset: str
    timeframe: str
    observations: tuple[VisualObservation, ...]
    visible_context: tuple[str, ...] = ()
    missing_context: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    captured_at_ms: int | None = None
    source: str = "user_screenshot"

    def __post_init__(self) -> None:
        if not self.asset.strip():
            raise ValueError("asset must not be empty")
        if not self.timeframe.strip():
            raise ValueError("timeframe must not be empty")
        if self.source != "user_screenshot":
            raise ValueError("VisualEvidence source must be user_screenshot")
        if self.captured_at_ms is not None and self.captured_at_ms < 0:
            raise ValueError("captured_at_ms must be non-negative")

        ids = [observation.concept_id for observation in self.observations]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate concept observations are not allowed")


@dataclass(frozen=True)
class VisualEvidenceSet:
    """Evidence bundle for one user request across multiple chart timeframes."""

    items: tuple[VisualEvidence, ...]

    def __post_init__(self) -> None:
        keys = [(item.asset, item.timeframe) for item in self.items]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate asset/timeframe evidence is not allowed")

    @property
    def assets(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(item.asset for item in self.items))

    @property
    def timeframes(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(item.timeframe for item in self.items))

    def observations_for(self, concept_id: str) -> tuple[VisualObservation, ...]:
        return tuple(
            observation
            for item in self.items
            for observation in item.observations
            if observation.concept_id == concept_id
        )


def observation(
    concept_id: str,
    *,
    state: str,
    confidence: float,
    evidence: Iterable[str],
    notes: str = "",
    price_location: str | None = None,
    direction: str | None = None,
) -> VisualObservation:
    """Build one normalized observation from the future vision layer."""

    return VisualObservation(
        concept_id=concept_id,
        state=state,
        confidence=confidence,
        evidence=tuple(evidence),
        notes=notes,
        price_location=price_location,
        direction=direction,
    )
