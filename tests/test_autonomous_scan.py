from types import SimpleNamespace

import pandas as pd

from aicfa.autonomous_scan import AutonomousScanEngine
from aicfa.data_requirements import TradingMode
from aicfa.market_universe import MarketUniverse, MonitoredMarket
from aicfa.setup_analysis import SetupCandidate, SetupLevel


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
