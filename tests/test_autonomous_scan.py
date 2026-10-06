from types import SimpleNamespace

import pandas as pd

from aicfa.autonomous_scan import AutonomousScanEngine
from aicfa.data_requirements import TradingMode
from aicfa.market_universe import MarketUniverse, MonitoredMarket
from aicfa.setup_analysis import SetupCandidate, SetupLevel



class SnapshotProvider:
    exchange = "test"

    def resolve_symbol(self, asset, *, market_type):
        return asset

    def fetch_ohlcv(self, **kwargs):
        return pd.DataFrame({
            "timestamp": [1], "open": [100.0], "high": [101.0],
            "low": [99.0], "close": [100.5], "volume": [10.0],
        })

def _candidate():
    return SetupCandidate(
        scenario="continuation",
        supporting_concepts=("market_structure.bos", "liquidity.sweep"),
        zone_concepts=("imbalance.fvg",),
        zone_locations=("15m",),
        entry_condition=("zone reaction",),
        invalidation=("previous low",),
        targets=("liquidity",),
        rationale=("BOS + displacement",),
        direction="long",
        entry_zone=(
            SetupLevel(100.0, "15m", "FVG low"),
            SetupLevel(102.0, "15m", "FVG high"),
        ),
        invalidation_level=SetupLevel(95.0, "5m", "previous low"),
        target_levels=(
            SetupLevel(110.0, "4h", "previous high"),
            SetupLevel(120.0, "1d", "previous high"),
        ),
    )


def _result(asset, mode):
    execution = {
        TradingMode.INTRADAY: "5m",
        TradingMode.SWING: "1h",
        TradingMode.POSITION: "4h",
    }[mode]
    candidate = _candidate()
    return SimpleNamespace(
        symbol=asset,
        mode=mode,
        request=SimpleNamespace(market_type="spot"),
        analysis=pd.DataFrame({"timestamp": [1_000]}),
        frames={execution: pd.DataFrame({"close": [101.0]})},
        decision="LONG",
        setup_assessment=SimpleNamespace(
            decision=SimpleNamespace(value="ready"),
            candidates=(candidate,),
        ),
    )


def test_scan_once_reuses_lifecycle_state(monkeypatch):
    monkeypatch.setattr("aicfa.autonomous_scan.build_public_market_data_provider", lambda **kwargs: SnapshotProvider())
    calls = []

    def fake_find_setup(request, **kwargs):
        calls.append((request.asset, request.mode))
        return _result(request.asset, request.mode)

    monkeypatch.setattr("aicfa.market_orchestrator.find_setup", fake_find_setup)

    universe = MarketUniverse((
        MonitoredMarket("BTC/USDT"),
        MonitoredMarket("ETH/USDT"),
    ))
    engine = AutonomousScanEngine(universe)

    first = engine.scan_once(now_ms=1_000)
    second = engine.scan_once(now_ms=2_000)

    assert first.scan_number == 1
    assert second.scan_number == 2
    assert engine.last_state == second
    assert len(calls) == 12
    assert len(engine.active_setups()) == 6


def test_distinct_geometries_remain_independent_across_scans(monkeypatch):
    monkeypatch.setattr("aicfa.autonomous_scan.build_public_market_data_provider", lambda **kwargs: SnapshotProvider())
    first = _candidate()
    second = SetupCandidate(
        **{
            **first.__dict__,
            "entry_zone": (
                SetupLevel(96.0, "15m", "second FVG low"),
                SetupLevel(98.0, "15m", "second FVG high"),
            ),
            "invalidation_level": SetupLevel(92.0, "5m", "second invalidation"),
        }
    )
    calls = {"count": 0}

    def fake_find_setup(request, **kwargs):
        calls["count"] += 1
        candidate = second if request.mode is TradingMode.INTRADAY and calls["count"] > 3 else first
        return SimpleNamespace(
            symbol=request.asset,
            mode=request.mode,
            request=SimpleNamespace(market_type="spot"),
            analysis=pd.DataFrame({"timestamp": [1_000 + calls["count"]]}),
            frames={
                {TradingMode.INTRADAY: "5m", TradingMode.SWING: "1h", TradingMode.POSITION: "4h"}[request.mode]:
                pd.DataFrame({"close": [101.0]})
            },
            decision="LONG",
            setup_assessment=SimpleNamespace(
                decision=SimpleNamespace(value="ready"),
                candidates=(candidate,),
            ),
        )

    monkeypatch.setattr("aicfa.market_orchestrator.find_setup", fake_find_setup)

    engine = AutonomousScanEngine(MarketUniverse((MonitoredMarket("BTC/USDT"),)))
    engine.scan_once(now_ms=1_000)
    engine.scan_once(now_ms=2_000)

    assert len(engine.active_setups(symbol="BTC/USDT")) == 4


def test_run_forever_can_be_stopped_after_a_scan(monkeypatch):
    monkeypatch.setattr("aicfa.autonomous_scan.build_public_market_data_provider", lambda **kwargs: SnapshotProvider())
    def fake_find_setup(request, **kwargs):
        return _result(request.asset, request.mode)

    monkeypatch.setattr("aicfa.market_orchestrator.find_setup", fake_find_setup)

    universe = MarketUniverse((MonitoredMarket("BTC/USDT"),))
    engine = AutonomousScanEngine(universe)

    sleeps = []
    engine.run_forever(
        interval_seconds=5,
        should_stop=lambda: engine.scan_number >= 1,
        sleep=sleeps.append,
    )

    assert engine.scan_number == 1
    assert sleeps == []


def test_scan_batch_rotates_20_markets_and_revisits_after_ten_batches(monkeypatch):
    monkeypatch.setattr("aicfa.autonomous_scan.build_public_market_data_provider", lambda **kwargs: SnapshotProvider())
    calls = []

    def fake_find_setup(request, **kwargs):
        calls.append(request.asset)
        return _result(request.asset, request.mode)

    monkeypatch.setattr("aicfa.market_orchestrator.find_setup", fake_find_setup)

    assets = tuple(f"COIN{i:03d}/USDT" for i in range(199))
    engine = AutonomousScanEngine(
        MarketUniverse(tuple(MonitoredMarket(asset) for asset in assets))
    )

    states = [
        engine.scan_batch(i, batch_size=20, now_ms=1_000 + i * 60_000)
        for i in range(10)
    ]

    assert [len(state.result.markets) for state in states] == [20] * 9 + [19]
    assert [state.result.markets[0].asset for state in states] == [
        "COIN000/USDT",
        "COIN020/USDT",
        "COIN040/USDT",
        "COIN060/USDT",
        "COIN080/USDT",
        "COIN100/USDT",
        "COIN120/USDT",
        "COIN140/USDT",
        "COIN160/USDT",
        "COIN180/USDT",
    ]
    assert len(calls) == 199 * 3
    assert set(calls) == set(assets)

    eleventh = engine.scan_batch(0, batch_size=20, now_ms=601_000)
    assert len(eleventh.result.markets) == 20
    assert eleventh.result.markets[0].asset == "COIN000/USDT"


def test_run_forever_batches_scans_one_market_sequentially(monkeypatch):
    monkeypatch.setattr("aicfa.autonomous_scan.build_public_market_data_provider", lambda **kwargs: SnapshotProvider())
    def fake_find_setup(request, **kwargs):
        return _result(request.asset, request.mode)

    monkeypatch.setattr("aicfa.market_orchestrator.find_setup", fake_find_setup)

    assets = tuple(f"COIN{i:03d}/USDT" for i in range(3))
    engine = AutonomousScanEngine(
        MarketUniverse(tuple(MonitoredMarket(asset) for asset in assets))
    )

    seen = []
    sleeps = []

    engine.run_forever_batches(
        interval_seconds=60,
        batch_size=1,
        on_scan=lambda state: seen.append(state.result.markets[0].asset),
        should_stop=lambda: len(seen) >= 5,
        sleep=sleeps.append,
    )

    assert seen == [
        "COIN000/USDT",
        "COIN001/USDT",
        "COIN002/USDT",
        "COIN000/USDT",
        "COIN001/USDT",
    ]
    assert sleeps == [60, 60, 60, 60]

def test_run_forever_batches_continues_after_market_error(monkeypatch):
    monkeypatch.setattr(
        "aicfa.autonomous_scan.build_public_market_data_provider",
        lambda **kwargs: SnapshotProvider(),
    )

    assets = tuple(f"COIN{i:03d}/USDT" for i in range(2))
    engine = AutonomousScanEngine(
        MarketUniverse(tuple(MonitoredMarket(asset) for asset in assets))
    )

    calls = []
    errors = []

    def fake_scan_market(index, *, now_ms=None):
        asset = engine.universe.markets[index].asset
        calls.append(asset)
        if asset == "COIN000/USDT" and calls.count(asset) == 1:
            raise RuntimeError("temporary provider failure")
        return SimpleNamespace(
            scan_number=len(calls),
            result=SimpleNamespace(
                markets=(SimpleNamespace(asset=asset, diagnostics=None, setups=()),)
            ),
        )

    monkeypatch.setattr(engine, "scan_market", fake_scan_market)

    engine.run_forever_batches(
        interval_seconds=0,
        batch_size=1,
        on_error=lambda asset, exc: errors.append((asset, str(exc))),
        should_stop=lambda: len(calls) >= 3,
    )

    assert calls == [
        "COIN000/USDT",
        "COIN001/USDT",
        "COIN000/USDT",
    ]
    assert errors == [("COIN000/USDT", "temporary provider failure")]

