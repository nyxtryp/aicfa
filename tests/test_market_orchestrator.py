from types import SimpleNamespace

import pandas as pd
import pytest

from aicfa.data_requirements import TradingMode
from aicfa.setup_analysis import SetupCandidate, SetupLevel
from aicfa.market_orchestrator import (
    PRIMARY_TRADING_MODES,
    analyze_market_horizons,
    scan_markets,
    scan_universe,
)
from aicfa.market_universe import MarketUniverse, MonitoredMarket
from aicfa.setup_lifecycle import SetupLifecycle, SetupLifecycleStatus
from aicfa.market_data_router import FallbackMarketDataProvider



class SnapshotProvider:
    exchange = "test"

    def __init__(self):
        self.ohlcv_calls = []

    def resolve_symbol(self, asset, *, market_type):
        return asset

    def fetch_ohlcv(self, **kwargs):
        self.ohlcv_calls.append(kwargs)
        return pd.DataFrame({
            "timestamp": [1], "open": [100.0], "high": [101.0],
            "low": [99.0], "close": [100.5], "volume": [10.0],
        })


def _provider():
    return FallbackMarketDataProvider([SnapshotProvider()])

def _candidate(direction="long", scenario="continuation"):
    return SetupCandidate(
        scenario=scenario,
        supporting_concepts=("market_structure.bos", "displacement", "liquidity.sweep"),
        zone_concepts=("order_block.bullish", "imbalance.fvg"),
        zone_locations=("order_block.bullish: discount",),
        entry_condition=("zone reaction/confirmation is required",),
        invalidation=("previous low breaks the setup",),
        targets=("next liquidity",),
        rationale=("BOS followed by displacement",),
        direction=direction,
    )


def _fake_result(asset: str, mode: TradingMode, *, candidate=None, decision="WAIT"):
    execution = {
        TradingMode.INTRADAY: "5m",
        TradingMode.SWING: "1h",
        TradingMode.POSITION: "4h",
    }[mode]
    return SimpleNamespace(
        symbol=f"{asset}/USDT" if "/" not in asset else asset,
        mode=mode,
        request=SimpleNamespace(market_type="spot"),
        analysis=None,
        frames={execution: pd.DataFrame({"close": [101.0]})},
        decision=decision,
        setup_assessment=SimpleNamespace(
            decision=SimpleNamespace(value="ready" if candidate is not None and decision == "LONG" else "wait"),
            candidates=() if candidate is None else (candidate,),
        ),
        diagnostics=SimpleNamespace(
            block_timings=tuple(SimpleNamespace(status="prefetched") for _ in range(4)),
            feature_duration_ms=0.1,
            evidence_duration_ms=0.1,
            setup_duration_ms=0.1,
            refetched_timeframes=(),
        ),
    )


def test_one_market_runs_all_three_primary_horizons(monkeypatch):
    calls = []

    def fake_find_setup(request, **kwargs):
        calls.append(request.mode)
        candidate = _candidate()
        return _fake_result(request.asset, request.mode, candidate=candidate, decision="LONG")

    monkeypatch.setattr("aicfa.market_orchestrator.find_setup", fake_find_setup)

    result = analyze_market_horizons("BTC/USDT", provider=_provider(), now_ms=1000)

    assert [item.mode for item in result.results] == list(PRIMARY_TRADING_MODES)
    assert calls == list(PRIMARY_TRADING_MODES)
    assert [item.mode for item in result.setups] == list(PRIMARY_TRADING_MODES)
    assert [item.description.horizon for item in result.setups] == list(PRIMARY_TRADING_MODES)
    assert all(item.description.direction == "long" for item in result.setups)


def test_multiple_markets_keep_results_independent(monkeypatch):
    def fake_find_setup(request, **kwargs):
        candidate = _candidate()
        return _fake_result(request.asset, request.mode, candidate=candidate, decision="LONG")

    monkeypatch.setattr("aicfa.market_orchestrator.find_setup", fake_find_setup)

    result = scan_markets(["BTC/USDT", "ETH/USDT"], provider=_provider(), now_ms=1000)

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
        candidate = _candidate(
            "long" if request.mode is not TradingMode.POSITION else "short",
            request.mode.value,
        )
        return _fake_result(request.asset, request.mode, candidate=candidate, decision="LONG")

    monkeypatch.setattr("aicfa.market_orchestrator.find_setup", fake_find_setup)

    result = analyze_market_horizons("SOL/USDT", provider=_provider(), now_ms=1000)

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

    result = scan_universe(universe, provider=_provider(), now_ms=1000)

    assert [market.asset for market in result.markets] == ["BTC/USDT", "ETH/USDT"]
    assert calls == [
        ("BTC/USDT", "spot"),
        ("BTC/USDT", "spot"),
        ("BTC/USDT", "spot"),
        ("ETH/USDT", "futures"),
        ("ETH/USDT", "futures"),
        ("ETH/USDT", "futures"),
    ]


def test_orchestrator_updates_existing_lifecycle_without_duplicate(monkeypatch):
    lifecycle = SetupLifecycle()

    def fake_find_setup(request, **kwargs):
        return _fake_result(request.asset, request.mode, candidate=_candidate(), decision="LONG")

    monkeypatch.setattr("aicfa.market_orchestrator.find_setup", fake_find_setup)

    first = analyze_market_horizons("BTC/USDT", provider=_provider(), now_ms=1_000, lifecycle=lifecycle)
    second = analyze_market_horizons("BTC/USDT", now_ms=2_000, lifecycle=lifecycle)

    assert len(first.setups) == 3
    assert len(second.setups) == 3
    assert all(item.identity is not None for item in second.setups)
    assert all(
        item.lifecycle_result is not None
        and item.lifecycle_result.status is SetupLifecycleStatus.ACTIVE
        for item in second.setups
    )
    assert len(lifecycle.active_setups(symbol="BTC/USDT")) == 3


def test_orchestrator_keeps_two_same_horizon_geometries_independent(monkeypatch):
    lifecycle = SetupLifecycle()
    first = _candidate()
    second = SetupCandidate(**{
        **first.__dict__,
        "entry_zone": (
            SetupLevel(96.0, "15m", "second FVG low"),
            SetupLevel(98.0, "15m", "second FVG high"),
        ),
        "invalidation_level": SetupLevel(92.0, "5m", "second invalidation"),
        "target_levels": (
            SetupLevel(108.0, "4h", "second target 1"),
            SetupLevel(115.0, "1d", "second target 2"),
        ),
    })

    def fake_find_setup(request, **kwargs):
        candidate = first if request.mode is TradingMode.SWING else second
        return _fake_result(request.asset, request.mode, candidate=candidate, decision="LONG")

    monkeypatch.setattr("aicfa.market_orchestrator.find_setup", fake_find_setup)

    result = analyze_market_horizons("BTC/USDT", provider=_provider(), now_ms=1_000, lifecycle=lifecycle)

    assert len(result.lifecycle_results) == 3
    assert len(lifecycle.active_setups(symbol="BTC/USDT", horizon="intraday")) == 1
    assert len(lifecycle.active_setups(symbol="BTC/USDT", horizon="swing")) == 1
    assert len(lifecycle.active_setups(symbol="BTC/USDT", horizon="position")) == 1


def test_one_market_acquires_full_primary_snapshot_once(monkeypatch):
    provider = _provider()
    calls = []

    def fake_find_setup(request, **kwargs):
        calls.append((request.mode, tuple(kwargs["prefetched_frames"])))
        return _fake_result(request.asset, request.mode, decision="WAIT")

    monkeypatch.setattr("aicfa.market_orchestrator.find_setup", fake_find_setup)

    result = analyze_market_horizons("BTC/USDT", provider=provider, now_ms=10_000_000_000)

    assert len(result.results) == 3
    assert all(keys == ("1w", "1d", "4h", "1h", "15m", "5m") for _, keys in calls)
    assert len(provider.providers[0].ohlcv_calls) == 6


def test_market_diagnostics_expose_snapshot_and_horizon_timings(monkeypatch):
    provider = _provider()

    def fake_find_setup(request, **kwargs):
        return _fake_result(request.asset, request.mode, decision="WAIT")

    monkeypatch.setattr("aicfa.market_orchestrator.find_setup", fake_find_setup)

    result = analyze_market_horizons("BTC/USDT", provider=provider, now_ms=1000)

    assert result.diagnostics is not None
    assert result.diagnostics.total_duration_ms >= 0
    assert result.diagnostics.snapshot_duration_ms >= 0
    assert [item.timeframe for item in result.diagnostics.snapshot_metrics] == ["1w", "1d", "4h", "1h", "15m", "5m"]
    assert [item.rows for item in result.diagnostics.snapshot_metrics] == [1] * 6
    assert len(result.diagnostics.horizon_timings) == 3
    assert all(item.duration_ms >= 0 for item in result.diagnostics.horizon_timings)
    assert all(item.setup_count == 0 for item in result.diagnostics.horizon_timings)
    assert result.diagnostics.refetched_between_horizons is False
    assert result.diagnostics.status == "completed"
    assert result.diagnostics.error == ""
    assert len(result.diagnostics.block_timings) == 12
    assert result.diagnostics.feature_duration_ms >= 0
    assert result.diagnostics.evidence_duration_ms >= 0
    assert result.diagnostics.setup_duration_ms >= 0
    assert result.diagnostics.lifecycle_event_count == 0
    assert all(item.status == "prefetched" for item in result.diagnostics.block_timings)


def test_one_market_computes_primary_features_once(monkeypatch):
    class FeatureSnapshotProvider(SnapshotProvider):
        def fetch_ohlcv(self, **kwargs):
            self.ohlcv_calls.append(kwargs)
            rows = max(int(kwargs.get("limit") or 240), 1000)
            return pd.DataFrame({
                "timestamp": list(range(1, rows + 1)),
                "open": [100.0] * rows,
                "high": [101.0] * rows,
                "low": [99.0] * rows,
                "close": [100.5] * rows,
                "volume": [10.0] * rows,
            })

    provider = FallbackMarketDataProvider([FeatureSnapshotProvider()])
    calls = []

    def fake_completed_ohlcv(frame, *, timeframe, now_ms):
        return frame

    def fake_build_features(frame):
        calls.append(len(frame))
        return frame.copy()

    def fake_find_setup(request, **kwargs):
        return _fake_result(request.asset, request.mode, decision="WAIT")

    monkeypatch.setattr("aicfa.market_orchestrator.completed_ohlcv", fake_completed_ohlcv)
    monkeypatch.setattr("aicfa.market_orchestrator.build_features", fake_build_features)
    monkeypatch.setattr("aicfa.market_orchestrator.find_setup", fake_find_setup)

    analyze_market_horizons("BTC/USDT", provider=provider, now_ms=1000)

    assert len(calls) == 6
