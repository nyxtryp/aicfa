from __future__ import annotations

import json

from aicfa.setup_registry import SetupRegistry


def test_registry_refreshes_same_identity_without_duplicate(tmp_path):
    registry = SetupRegistry(tmp_path / "journal" / "setup_registry.json")

    class Candidate:
        scenario = "reversal"
        direction = "long"

    class Lifecycle:
        status = type("Status", (), {"value": "active"})()

    class Setup:
        mode = "intraday"
        candidate = Candidate()
        identity = None
        lifecycle_result = Lifecycle()
        evidence_concepts = ("market_structure.choch",)
        decision_action = "long"

    class Market:
        asset = "CRV/USDT"
        setups = (Setup(),)
        lifecycle_results = ()

    class State:
        scanned_at_ms = 1_000
        scan_number = 1
        result = type("Result", (), {"markets": (Market(),)})()

    registry.record_scan(State())
    State.scanned_at_ms = 2_000
    State.scan_number = 2
    registry.record_scan(State())

    records = registry.read()
    assert len(records) == 1
    record = next(iter(records.values()))
    assert record["last_seen_at_ms"] == 2_000
    assert record["status"] == "ACTIVE"


def test_registry_marks_unseen_setup_stale_then_expired(tmp_path):
    registry = SetupRegistry(tmp_path / "journal" / "setup_registry.json")

    class Candidate:
        scenario = "continuation"
        direction = "long"

    class Lifecycle:
        status = type("Status", (), {"value": "active"})()

    class Setup:
        mode = "swing"
        candidate = Candidate()
        identity = None
        lifecycle_result = Lifecycle()
        evidence_concepts = ()
        decision_action = "long"

    class Market:
        asset = "BTC/USDT"
        setups = (Setup(),)
        lifecycle_results = ()

    class State:
        scanned_at_ms = 0
        scan_number = 1
        result = type("Result", (), {"markets": (Market(),)})()

    registry.record_scan(State())
    State.result = type("Result", (), {"markets": ()})()
    State.scanned_at_ms = 36 * 60 * 60_000
    registry.record_scan(State())
    assert next(iter(registry.read().values()))["status"] == "STALE"

    State.scanned_at_ms = 48 * 60 * 60_000
    registry.record_scan(State())
    assert next(iter(registry.read().values()))["status"] == "STALE"
    assert registry.current() == ()

    
def test_registry_keeps_lifecycle_active_setup_alive_during_analytical_wait(tmp_path):
    registry = SetupRegistry(tmp_path / "journal" / "setup_registry.json")

    class Candidate:
        scenario = "continuation"
        direction = "long"

    class Identity:
        symbol = "ETH/USDT"
        market_type = "futures"
        horizon = "swing"
        scenario = "continuation"
        direction = "long"

    class LifecycleResult:
        status = type("Status", (), {"value": "active"})()

    class Setup:
        mode = "swing"
        candidate = Candidate()
        identity = Identity()
        lifecycle_result = LifecycleResult()

    class Lifecycle:
        identity = Identity()
        status = type("Status", (), {"value": "active"})()

    class Market:
        asset = "ETH/USDT"
        setups = (Setup(),)
        lifecycle_results = ()

    class State:
        scanned_at_ms = 0
        scan_number = 1
        result = type("Result", (), {"markets": (Market(),)})()

    registry.record_scan(State())

    # Later scan: no analytical candidate, but the lifecycle engine still
    # confirms that the existing setup remains active.
    State.scanned_at_ms = 4 * 24 * 60 * 60_000
    State.scan_number = 2
    Market.setups = ()
    Market.lifecycle_results = (Lifecycle(),)
    registry.record_scan(State())

    record = next(iter(registry.read().values()))
    assert record["status"] == "ACTIVE"
    assert record["lifecycle_status"] == "active"
    assert record["last_lifecycle_at_ms"] == State.scanned_at_ms


def test_registry_does_not_queue_pending_candidate_without_lifecycle_activation(tmp_path):
    registry = SetupRegistry(tmp_path / "journal" / "setup_registry.json")

    class Candidate:
        scenario = "continuation"
        direction = "long"

    class Setup:
        mode = "intraday"
        candidate = Candidate()
        identity = None
        lifecycle_result = None

    class Market:
        asset = "GRT/USDT"
        setups = (Setup(),)
        lifecycle_results = ()

    class State:
        scanned_at_ms = 1_000
        scan_number = 1
        result = type("Result", (), {"markets": (Market(),)})()

    registry.record_scan(State())
    assert registry.read() == {}
    assert registry.current() == ()


def test_registry_migrates_only_lifecycle_owned_revision_three_setup(tmp_path):
    registry = SetupRegistry(tmp_path / "journal" / "setup_registry.json")
    registry._write({
        "BTC/USDT|spot|INTRADAY|continuation|long|1h": {
            "strategy_revision": 3,
            "status": "ACTIVE",
            "lifecycle_status": "active",
            "asset": "BTC/USDT",
            "last_seen_at_ms": 1000,
        },
        "ETH/USDT|spot|INTRADAY|continuation|long|1h": {
            "strategy_revision": 2,
            "status": "ACTIVE",
            "lifecycle_status": "active",
            "asset": "ETH/USDT",
            "last_seen_at_ms": 1000,
        },
    })

    current = registry.current()

    assert len(current) == 1
    assert current[0]["asset"] == "BTC/USDT"
    assert current[0]["strategy_revision"] == 5
    records = registry.read()
    assert records["BTC/USDT|spot|INTRADAY|continuation|long|1h"]["strategy_revision"] == 5
    assert records["ETH/USDT|spot|INTRADAY|continuation|long|1h"]["strategy_revision"] == 2


def test_registry_migrates_tp1_hit_but_keeps_it_out_of_actionable_queue(tmp_path):
    registry = SetupRegistry(tmp_path / "journal" / "setup_registry.json")
    registry._write({
        "CAKE/USDT|spot|INTRADAY|reversal|short|1h": {
            "strategy_revision": 3,
            "status": "TP1_HIT",
            "lifecycle_status": "tp1_hit",
            "asset": "CAKE/USDT",
            "last_seen_at_ms": 1000,
        },
    })

    assert registry.current() == ()
    record = next(iter(registry.read().values()))
    assert record["strategy_revision"] == 5
    assert record["status"] == "TP1_HIT"



def test_partial_market_scan_does_not_stale_setups_for_other_markets(tmp_path):
    registry = SetupRegistry(tmp_path / "journal" / "setup_registry.json")

    class Candidate:
        scenario = "continuation"
        direction = "long"

    class Lifecycle:
        status = type("Status", (), {"value": "active"})()

    class Setup:
        mode = "intraday"
        candidate = Candidate()
        identity = None
        lifecycle_result = Lifecycle()
        evidence_concepts = ()
        decision_action = "long"

    class Diagnostics:
        status = "completed"

    class Market:
        diagnostics = Diagnostics()
        setups = (Setup(),)
        lifecycle_results = ()

        def __init__(self, asset):
            self.asset = asset

    class FullState:
        scanned_at_ms = 1_000
        scan_number = 1
        universe_size = 2
        is_full_universe_scan = True
        result = type("Result", (), {
            "markets": (Market("BTC/USDT"), Market("ETH/USDT"))
        })()

    registry.record_scan(FullState())

    class PartialState:
        scanned_at_ms = 2_000
        scan_number = 2
        universe_size = 2
        is_full_universe_scan = False
        result = type("Result", (), {"markets": (Market("BTC/USDT"),)})()

    registry.record_scan(PartialState())

    records = registry.read()
    assert {record["asset"]: record["status"] for record in records.values()} == {
        "BTC/USDT": "ACTIVE",
        "ETH/USDT": "ACTIVE",
    }


def test_failed_partial_scan_does_not_stale_existing_setup(tmp_path):
    registry = SetupRegistry(tmp_path / "journal" / "setup_registry.json")

    class Candidate:
        scenario = "continuation"
        direction = "long"

    class Lifecycle:
        status = type("Status", (), {"value": "active"})()

    class Setup:
        mode = "intraday"
        candidate = Candidate()
        identity = None
        lifecycle_result = Lifecycle()
        evidence_concepts = ()
        decision_action = "long"

    class GoodDiagnostics:
        status = "completed"

    class FailedDiagnostics:
        status = "error"

    class GoodMarket:
        asset = "BTC/USDT"
        diagnostics = GoodDiagnostics()
        setups = (Setup(),)
        lifecycle_results = ()

    class FailedMarket:
        asset = "BTC/USDT"
        diagnostics = FailedDiagnostics()
        setups = ()
        lifecycle_results = ()

    class InitialState:
        scanned_at_ms = 1_000
        scan_number = 1
        universe_size = 1
        is_full_universe_scan = True
        result = type("Result", (), {"markets": (GoodMarket(),)})()

    registry.record_scan(InitialState())

    class FailedState:
        scanned_at_ms = 2_000
        scan_number = 2
        universe_size = 2
        is_full_universe_scan = False
        result = type("Result", (), {"markets": (FailedMarket(),)})()

    registry.record_scan(FailedState())

    record = next(iter(registry.read().values()))
    assert record["status"] == "ACTIVE"
    assert record["lifecycle_status"] == "active"


def test_registry_persists_missed_by_price_as_terminal_not_active(tmp_path):
    registry = SetupRegistry(tmp_path / "journal" / "setup_registry.json")

    class Candidate:
        scenario = "continuation"
        direction = "long"
        entry_zone = ()

    class Lifecycle:
        status = type("Status", (), {"value": "missed_by_price"})()
        reason = "missed by price: maximum acceptable entry price 102"

    class Setup:
        mode = "scalping"
        candidate = Candidate()
        identity = None
        lifecycle_result = Lifecycle()
        evidence_concepts = ()
        decision_action = "wait"

    class Market:
        asset = "BTC/USDT"
        setups = (Setup(),)
        lifecycle_results = ()

    class State:
        scanned_at_ms = 1_000
        scan_number = 1
        result = type("Result", (), {"markets": (Market(),)})()

    registry.record_scan(State())
    records = registry.read()
    assert len(records) == 1
    record = next(iter(records.values()))
    assert record["status"] == "MISSED_BY_PRICE"
    assert record["lifecycle_status"] == "missed_by_price"
    assert registry.current() == ()

    State.scanned_at_ms = 2_000
    State.scan_number = 2
    Market.setups = ()
    registry.record_scan(State())
    assert next(iter(registry.read().values()))["status"] == "MISSED_BY_PRICE"
