from dataclasses import dataclass, field
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
    invalidation_level: Level = field(default_factory=lambda: Level(98.0))
    target_levels: tuple = field(default_factory=lambda: (Level(106.0),))
    rationale: tuple = ("Waiting for price to reach the entry zone",)


@dataclass
class Setup:
    mode: str
    candidate: Candidate
    lifecycle_result: object = None
    decision_action: str = "wait"


def test_manual_scan_does_not_return_wait_candidates_as_setups():
    candidate = Candidate()
    market = SimpleNamespace(
        asset="BTC/USDT",
        diagnostics=SimpleNamespace(status="completed", error=""),
        setups=(Setup(mode="INTRADAY", candidate=candidate, decision_action="wait"),),
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
    assert payload["watch_candidates"] == []


def test_manual_scan_returns_only_directionally_approved_valid_geometry():
    candidate = Candidate()
    market = SimpleNamespace(
        asset="BTC/USDT",
        diagnostics=SimpleNamespace(status="completed", error=""),
        setups=(Setup(mode="INTRADAY", candidate=candidate, decision_action="long"),),
        results=(),
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
    item = payload["watch_candidates"][0]
    assert item["decision_action"] == "long"
    assert item["candidate"]["direction"] == "long"
    assert item["candidate"]["entry_zone"][0]["value"] == 100.0


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


def test_health_reports_automatic_worker_state_not_last_manual_scan():
    import json
    import threading
    from http.server import ThreadingHTTPServer
    from urllib.request import urlopen

    from aicfa.market_control import create_handler

    engine = SimpleNamespace(
        last_state=SimpleNamespace(
            result=SimpleNamespace(markets=(
                SimpleNamespace(diagnostics=SimpleNamespace(status="completed", error="")),
            ))
        ),
        scan_number=9,
        cycle_id=2,
        universe=SimpleNamespace(markets=(SimpleNamespace(asset="BTC/USDT"),)),
        automatic_pause_until_ms=0,
        automatic_worker_running=False,
        last_automatic_scan_status="restarting",
        last_automatic_scan_error="RuntimeError: worker callback failed",
        last_automatic_scan_at_ms=123456,
        last_automatic_scan_asset="ETH/USDT",
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), create_handler(engine))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urlopen(f"http://127.0.0.1:{server.server_port}/health", timeout=2) as response:
            payload = json.loads(response.read())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert payload["scanner"] == "stopped"
    assert payload["automatic_worker_running"] is False
    assert payload["last_scan_status"] == "restarting"
    assert payload["last_scan_error"] == "RuntimeError: worker callback failed"
    assert payload["last_automatic_scan_at_ms"] == 123456
    assert payload["last_automatic_scan_asset"] == "ETH/USDT"


def test_manual_scan_normalizes_enum_direction_and_returns_fresh_visual_payload():
    from enum import Enum

    class Direction(Enum):
        LONG = "long"

    class Mode(Enum):
        INTRADAY = "intraday"

    candidate = Candidate(direction=Direction.LONG)
    setup = Setup(mode=Mode.INTRADAY, candidate=candidate)
    market = SimpleNamespace(
        asset="ETH/USDT",
        diagnostics=SimpleNamespace(status="completed", error=""),
        setups=(setup,),
        results=(),
    )
    state = SimpleNamespace(
        scanned_at_ms=5678,
        scan_number=10,
        result=SimpleNamespace(markets=(market,)),
    )
    engine = SimpleNamespace(
        scan_market=lambda *args, **kwargs: state,
        automatic_pause_until_ms=0,
        registry=None,
    )

    payload = _scan_payload(engine, 0)

    assert len(payload["watch_candidates"]) == 1
    assert payload["watch_candidates"][0]["candidate"]["direction"] == "long"
    assert payload["watch_candidates"][0]["mode"] == "intraday"
    assert payload["market_visual"] == {"zones": [], "events": [], "liquidity": []}
