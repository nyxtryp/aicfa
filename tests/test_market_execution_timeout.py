import time

from aicfa.autonomous_scan import AutonomousScanEngine
from aicfa.market_universe import MarketUniverse, MonitoredMarket


def test_scan_market_timeout_records_failure_and_advances(monkeypatch):
    def slow_scan(*args, **kwargs):
        time.sleep(0.05)

    monkeypatch.setattr("aicfa.autonomous_scan.scan_universe", slow_scan)

    engine = AutonomousScanEngine(
        MarketUniverse((
            MonitoredMarket("BTC/USDT"),
            MonitoredMarket("ETH/USDT"),
        )),
        market_timeout_seconds=0.01,
    )

    first = engine.scan_market(0, now_ms=1_000)

    assert first.scan_number == 1
    market = first.result.markets[0]
    assert market.asset == "BTC/USDT"
    assert market.diagnostics is not None
    assert market.diagnostics.status == "timeout"
    assert "hard execution budget" in market.diagnostics.error

    second = engine.scan_market(1, now_ms=2_000)
    assert second.scan_number == 2
    assert second.result.markets[0].asset == "ETH/USDT"
    assert second.result.markets[0].diagnostics.status == "timeout"
