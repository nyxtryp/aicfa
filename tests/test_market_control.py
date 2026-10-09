from dataclasses import dataclass
from types import SimpleNamespace

from aicfa.market_control import _scan_payload


@dataclass
class Level:
    value: float
    timeframe: str = "15m"
    source: str = "test"


@dataclass
class Candidate:
    direction: str = "long"
    scenario: str = "reversal"
    entry_zone: tuple = (Level(100.0), Level(101.0))
    invalidation_level: Level = Level(98.0)
    target_levels: tuple = (Level(106.0),)
    rationale: tuple = ("Waiting for price to reach the entry zone",)


@dataclass
class Setup:
    mode: str
    candidate: Candidate
    lifecycle_result: object = None
    decision_action: str = "wait"


def test_manual_scan_returns_waiting_candidates_separately_from_active_setups():
    candidate = Candidate()
    market = SimpleNamespace(
        asset="BTC/USDT",
        diagnostics=SimpleNamespace(status="completed", error=""),
        setups=(Setup(mode="INTRADAY", candidate=candidate),),
    )
    state = SimpleNamespace(
        scanned_at_ms=1234,
        scan_number=7,
        result=SimpleNamespace(markets=(market,)),
    )
    engine = SimpleNamespace(
        scan_market=lambda *args, **kwargs: state,
        automatic_pause_until_ms=0,
        registry=None,
    )

    payload = _scan_payload(engine, 0)

    assert payload["setups"] == []
    assert len(payload["watch_candidates"]) == 1
    pending = payload["watch_candidates"][0]
    assert pending["asset"] == "BTC/USDT"
    assert pending["mode"] == "INTRADAY"
    assert pending["candidate"]["direction"] == "long"
    assert pending["candidate"]["entry_zone"][0]["value"] == 100.0
    assert pending["candidate"]["invalidation_level"]["value"] == 98.0
    assert pending["candidate"]["target_levels"][0]["value"] == 106.0


def test_manual_scan_does_not_duplicate_lifecycle_active_candidates_as_watch():
    candidate = Candidate()
    lifecycle = SimpleNamespace(status=SimpleNamespace(value="active"))
    market = SimpleNamespace(
        asset="BTC/USDT",
        diagnostics=SimpleNamespace(status="completed", error=""),
        setups=(Setup(mode="INTRADAY", candidate=candidate, lifecycle_result=lifecycle, decision_action="long"),),
    )
    state = SimpleNamespace(
        scanned_at_ms=1234,
        scan_number=8,
        result=SimpleNamespace(markets=(market,)),
    )
    engine = SimpleNamespace(
        scan_market=lambda *args, **kwargs: state,
        automatic_pause_until_ms=0,
        registry=None,
    )

    payload = _scan_payload(engine, 0)

    assert payload["watch_candidates"] == []
