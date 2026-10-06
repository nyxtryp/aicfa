from __future__ import annotations

import json

from aicfa.setup_registry import SetupRegistry


def test_registry_refreshes_same_identity_without_duplicate(tmp_path):
    registry = SetupRegistry(tmp_path / "journal" / "setup_registry.json")

    class Candidate:
        scenario = "reversal"
        direction = "long"

    class Setup:
        mode = "intraday"
        candidate = Candidate()
        identity = None
        lifecycle_result = None
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

    class Setup:
        mode = "swing"
        candidate = Candidate()
        identity = None
        lifecycle_result = None
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
    assert next(iter(registry.read().values()))["status"] == "EXPIRED"
