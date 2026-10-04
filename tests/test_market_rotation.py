from aicfa.autonomous_scan import AutonomousScanEngine
from aicfa.market_universe import MarketUniverse, MonitoredMarket


def test_run_cycle_has_deterministic_queue_and_metrics(monkeypatch):
    calls = []

    def fake_scan_market(self, market_index, *, now_ms=None):
        calls.append(market_index)
        from aicfa.autonomous_scan import AutonomousScanState
        from aicfa.market_orchestrator import MarketHorizonScan, MultiMarketScan, MarketScanDiagnostics
        scan = MarketHorizonScan(
            asset=self.universe.markets[market_index].asset,
            results=(),
            setups=(),
            diagnostics=MarketScanDiagnostics(
                total_duration_ms=1.0,
                resolution_duration_ms=0.0,
                snapshot_duration_ms=0.0,
                snapshot_metrics=(),
                horizon_timings=(),
            ),
        )
        return AutonomousScanState(
            scan_number=len(calls),
            scanned_at_ms=now_ms or 0,
            result=MultiMarketScan(markets=(scan,)),
        )

    monkeypatch.setattr(AutonomousScanEngine, "scan_market", fake_scan_market)
    universe = MarketUniverse(tuple(MonitoredMarket(f"COIN{i}/USDT") for i in range(3)))
    engine = AutonomousScanEngine(universe)

    cycle = engine.run_cycle(now_ms=1_000)

    assert cycle.cycle_id == 1
    assert cycle.market_count == 3
    assert cycle.completed_markets == 3
    assert cycle.timeout_markets == 0
    assert cycle.error_markets == 0
    assert [item.queue_position for item in cycle.markets] == [1, 2, 3]
    assert [item.asset for item in cycle.markets] == [
        "COIN0/USDT", "COIN1/USDT", "COIN2/USDT"
    ]
    assert [item.cycle_id for item in cycle.markets] == [1, 1, 1]
    assert calls == [0, 1, 2]
    assert engine.last_cycle == cycle


def test_run_cycle_records_timeout_and_continues(monkeypatch):
    statuses = ["timeout", "completed"]

    def fake_scan_market(self, market_index, *, now_ms=None):
        from aicfa.autonomous_scan import AutonomousScanState
        from aicfa.market_orchestrator import MarketHorizonScan, MultiMarketScan, MarketScanDiagnostics
        status = statuses[market_index]
        scan = MarketHorizonScan(
            asset=self.universe.markets[market_index].asset,
            results=(),
            setups=(),
            diagnostics=MarketScanDiagnostics(
                total_duration_ms=1.0,
                resolution_duration_ms=0.0,
                snapshot_duration_ms=0.0,
                snapshot_metrics=(),
                horizon_timings=(),
                status=status,
                error="budget exceeded" if status == "timeout" else "",
            ),
        )
        return AutonomousScanState(
            scan_number=market_index + 1,
            scanned_at_ms=now_ms or 0,
            result=MultiMarketScan(markets=(scan,)),
        )

    monkeypatch.setattr(AutonomousScanEngine, "scan_market", fake_scan_market)
    engine = AutonomousScanEngine(
        MarketUniverse((MonitoredMarket("BTC/USDT"), MonitoredMarket("ETH/USDT")))
    )

    cycle = engine.run_cycle(now_ms=1_000)

    assert cycle.market_count == 2
    assert cycle.completed_markets == 1
    assert cycle.timeout_markets == 1
    assert cycle.error_markets == 0
    assert [item.status for item in cycle.markets] == ["timeout", "completed"]
