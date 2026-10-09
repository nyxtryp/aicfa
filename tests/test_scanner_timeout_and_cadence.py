"""Regression tests for bounded autonomous market rotation."""
from __future__ import annotations

import time
from types import SimpleNamespace

from aicfa.autonomous_scan import AutonomousScanEngine
from aicfa.market_universe import MarketUniverse, MonitoredMarket


def test_market_scan_is_hard_timed_out_on_main_thread(monkeypatch):
    def slow_scan(*args, **kwargs):
        time.sleep(0.15)

    monkeypatch.setattr("aicfa.autonomous_scan.scan_universe", slow_scan)
    engine = AutonomousScanEngine(
        MarketUniverse((MonitoredMarket("BTC/USDT"),)),
        market_timeout_seconds=0.02,
        journal=None,
    )

    state = engine.scan_market(0, enforce_timeout=True)

    diagnostic = state.result.markets[0].diagnostics
    assert diagnostic.status == "timeout"
    assert "hard execution budget" in diagnostic.error


def test_rotation_uses_start_to_start_interval_not_extra_post_scan_delay(monkeypatch):
    now = {"seconds": 0.0}
    sleeps = []
    seen = []

    def monotonic():
        return now["seconds"]

    def fake_sleep(seconds):
        sleeps.append(seconds)
        now["seconds"] += seconds

    monkeypatch.setattr("aicfa.autonomous_scan.time.monotonic", monotonic)
    engine = AutonomousScanEngine(
        MarketUniverse((
            MonitoredMarket("BTC/USDT"),
            MonitoredMarket("ETH/USDT"),
        )),
        journal=None,
    )

    def fake_scan_market(index, **kwargs):
        now["seconds"] += 12.0
        asset = engine.universe.markets[index].asset
        return SimpleNamespace(
            scan_number=len(seen) + 1,
            result=SimpleNamespace(markets=(SimpleNamespace(
                asset=asset,
                diagnostics=SimpleNamespace(status="completed", error=""),
                setups=(),
            ),)),
        )

    monkeypatch.setattr(engine, "scan_market", fake_scan_market)
    engine.run_forever_batches(
        interval_seconds=30.0,
        batch_size=1,
        on_scan=lambda state: seen.append(state.result.markets[0].asset),
        should_stop=lambda: len(seen) >= 2,
        sleep=fake_sleep,
    )

    assert seen == ["BTC/USDT", "ETH/USDT"]
    assert sleeps == [18.0]



def test_manual_scan_does_not_pause_automatic_rotation():
    from aicfa.market_control import _scan_payload

    market_result = SimpleNamespace(
        asset="BTC/USDT",
        diagnostics=SimpleNamespace(status="completed", error=""),
        setups=(),
    )
    state = SimpleNamespace(
        scan_number=1,
        scanned_at_ms=123,
        result=SimpleNamespace(markets=(market_result,)),
    )

    class FakeEngine:
        universe = SimpleNamespace(markets=(SimpleNamespace(asset="BTC/USDT"),))
        registry = None
        automatic_pause_until_ms = 0

        def __init__(self):
            self.pause_calls = 0
            self.scan_kwargs = None

        def pause_automatic_scanning(self, *args, **kwargs):
            self.pause_calls += 1
            return 30_123

        def scan_market(self, market_index, **kwargs):
            self.scan_kwargs = (market_index, kwargs)
            return state

    engine = FakeEngine()
    payload = _scan_payload(engine, 0)

    assert engine.pause_calls == 0
    assert engine.scan_kwargs == (0, {"journal": True, "enforce_timeout": False})
    assert payload["automatic_scan_paused_until_ms"] == 0
    assert payload["market"]["diagnostics"] is not None
