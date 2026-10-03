from types import SimpleNamespace

import pytest

from aicfa.data_requirements import TradingMode
from aicfa.market_orchestrator import (
    PRIMARY_TRADING_MODES,
    analyze_market_horizons,
    scan_markets,
    scan_universe,
)
from aicfa.market_universe import MarketUniverse, MonitoredMarket


def _fake_result(asset: str, mode: TradingMode, *, candidate=None, decision="WAIT"):
    return SimpleNamespace(
        symbol=f"{asset}/USDT" if "/" not in asset else asset,
        mode=mode,
        request=SimpleNamespace(market_type="spot"),
        analysis=None,
        decision=decision,
        setup_assessment=SimpleNamespace(
            candidates=() if candidate is None else (candidate,),
        ),
    )


def test_one_market_runs_all_three_primary_horizons(monkeypatch):
    calls = []

    def fake_find_setup(request, **kwargs):
        calls.append(request.mode)
        candidate = SimpleNamespace(name=request.mode.value)
        return _fake_result(request.asset, request.mode, candidate=candidate, decision="LONG")

    monkeypatch.setattr("aicfa.market_orchestrator.find_setup", fake_find_setup)

    result = analyze_market_horizons("BTC/USDT", now_ms=1000)

    assert [item.mode for item in result.results] == list(PRIMARY_TRADING_MODES)
    assert calls == list(PRIMARY_TRADING_MODES)
    assert [item.mode for item in result.setups] == list(PRIMARY_TRADING_MODES)
    assert [item.description.horizon for item in result.setups] == list(PRIMARY_TRADING_MODES)
    assert all(item.description.direction == "long" for item in result.setups)


def test_multiple_markets_keep_results_independent(monkeypatch):
    def fake_find_setup(request, **kwargs):
        candidate = SimpleNamespace(market=request.asset, horizon=request.mode.value)
        return _fake_result(request.asset, request.mode, candidate=candidate, decision="LONG")

    monkeypatch.setattr("aicfa.market_orchestrator.find_setup", fake_find_setup)

    result = scan_markets(["BTC/USDT", "ETH/USDT"], now_ms=1000)

    assert [market.asset for market in result.markets] == ["BTC/USDT", "ETH/USDT"]
    assert len(result.setups) == 6
    assert [item[0] for item in result.setups] == [
        "BTC/USDT", "BTC/USDT", "BTC/USDT",
        "ETH/USDT", "ETH/USDT", "ETH/USDT",
    ]


def test_waiting_horizon_does_not_force_a_signal(monkeypatch):
    def fake_find_setup(request, **kwargs):
        return _fake_result(request.asset, request.mode, decision="WAIT")

    monkeypatch.setattr("aicfa.market_orchestrator.find_setup", fake_find_setup)

    result = analyze_market_horizons("BTC/USDT", now_ms=1000)

    assert result.setups == ()
    assert [item.decision for item in result.results] == ["WAIT", "WAIT", "WAIT"]


def test_distinct_concurrent_horizon_setups_are_preserved(monkeypatch):
    def fake_find_setup(request, **kwargs):
        candidate = SimpleNamespace(
            direction="long" if request.mode is not TradingMode.POSITION else "short",
            entry=request.mode.value,
        )
        return _fake_result(request.asset, request.mode, candidate=candidate, decision="LONG")

    monkeypatch.setattr("aicfa.market_orchestrator.find_setup", fake_find_setup)

    result = analyze_market_horizons("SOL/USDT", now_ms=1000)

    assert len(result.setups) == 3
    assert [item.candidate.direction for item in result.setups] == ["long", "long", "short"]
    assert [item.description.direction for item in result.setups] == ["long", "long", "short"]


def test_primary_orchestrator_rejects_scalping(monkeypatch):
    with pytest.raises(ValueError, match="scalping"):
        analyze_market_horizons(
            "BTC/USDT",
            now_ms=1000,
            modes=(TradingMode.SCALPING,),
        )


def test_configured_market_universe_controls_assets_and_market_type(monkeypatch):
    calls = []

    def fake_find_setup(request, **kwargs):
        calls.append((request.asset, request.market_type))
        return _fake_result(request.asset, request.mode, decision="WAIT")

    monkeypatch.setattr("aicfa.market_orchestrator.find_setup", fake_find_setup)

    universe = MarketUniverse((
        MonitoredMarket("BTC/USDT", "spot"),
        MonitoredMarket("ETH/USDT", "futures"),
    ))

    result = scan_universe(universe, now_ms=1000)

    assert [market.asset for market in result.markets] == ["BTC/USDT", "ETH/USDT"]
    assert calls == [
        ("BTC/USDT", "spot"),
        ("BTC/USDT", "spot"),
        ("BTC/USDT", "spot"),
        ("ETH/USDT", "futures"),
        ("ETH/USDT", "futures"),
        ("ETH/USDT", "futures"),
    ]
