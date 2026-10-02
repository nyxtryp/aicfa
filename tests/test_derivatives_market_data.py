import pandas as pd

from aicfa.derivatives import build_derivatives
from aicfa.derivatives_evidence import derivatives_completeness, append_derivatives_evidence
from aicfa.derivatives_market_data import BybitDerivativesProvider, _frame
from aicfa.market_evidence import MarketEvidence


def test_derivative_frame_normalizes_numeric_schema():
    frame = _frame([
        {
            "timestamp": "1000",
            "funding_rate": "0.001",
            "open_interest": "123",
            "mark_price": "50000",
            "liquidation_volume": "0",
        }
    ])
    assert tuple(frame.columns) == (
        "timestamp", "funding_rate", "open_interest",
        "liquidation_volume", "long_liquidation_volume",
        "short_liquidation_volume", "mark_price",
    )
    assert frame.iloc[0]["open_interest"] == 123.0
    assert frame.iloc[0]["mark_price"] == 50000.0


def test_derivatives_completeness_rejects_missing_required_source_fields():
    frame = pd.DataFrame({
        "timestamp": [1000],
        "funding_rate": [0.001],
        "open_interest": [123.0],
        "mark_price": [50000.0],
        "liquidation_volume": [None],
    })
    complete, missing = derivatives_completeness(frame)
    assert not complete
    assert "derivatives:liquidation_volume:unavailable" in missing


def test_build_derivatives_is_causal_and_does_not_use_future_observation():
    base = pd.DataFrame({
        "timestamp": pd.to_datetime([1000, 2000, 3000], unit="ms", utc=True),
        "close": [100.0, 101.0, 102.0],
    })
    source = pd.DataFrame({
        "timestamp": pd.to_datetime([1500, 2500], unit="ms", utc=True),
        "funding_rate": [0.001, 0.002],
        "open_interest": [1000.0, 1200.0],
    })
    out = build_derivatives(base, source)
    assert pd.isna(out.iloc[0]["open_interest"])
    assert out.iloc[1]["open_interest"] == 1000.0
    assert out.iloc[2]["open_interest"] == 1200.0


def test_derivatives_evidence_marks_unavailable_data_without_fabrication():
    evidence = MarketEvidence(
        asset="BTCUSDT",
        observations=(),
        timeframes=("1d",),
    )
    result = append_derivatives_evidence(
        evidence,
        pd.DataFrame(),
        timeframe="1d",
    )
    assert result.observations == ()
    assert "derivatives: no observations" in result.missing_context


def test_bybit_provider_normalizes_funding_oi_mark(monkeypatch):
    provider = BybitDerivativesProvider()
    responses = {
        "funding/history": {
            "retCode": 0,
            "result": {"list": [
                {"fundingRateTimestamp": "1000", "fundingRate": "0.001"}
            ]},
        },
        "open-interest": {
            "retCode": 0,
            "result": {"list": [
                {"timestamp": "1000", "openInterestValue": "123456"}
            ]},
        },
        "tickers": {
            "retCode": 0,
            "time": 1100,
            "result": {"list": [{"markPrice": "50000", "fundingRate": "0.0012"}]},
        },
    }

    def fake_get(path, params):
        return responses[path]

    monkeypatch.setattr(provider, "_get", fake_get)
    monkeypatch.setattr(
        "aicfa.derivatives_market_data._collect_bybit_liquidations",
        lambda symbol, timeout_seconds: [],
    )
    frame = provider.fetch_derivatives(symbol="BTCUSDT", limit=10)
    assert set(frame["funding_rate"].dropna()) == {0.001, 0.0012}
    assert 123456.0 in set(frame["open_interest"].dropna())
    assert 50000.0 in set(frame["mark_price"].dropna())
