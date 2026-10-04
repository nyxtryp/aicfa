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


def test_derivatives_completeness_allows_missing_optional_liquidations():
    frame = pd.DataFrame({
        "timestamp": [1000],
        "funding_rate": [0.001],
        "open_interest": [123.0],
        "mark_price": [50000.0],
        "liquidation_volume": [None],
    })
    complete, missing = derivatives_completeness(frame)
    assert complete, missing
    assert missing == ()


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


def test_bybit_provider_aligns_independent_funding_oi_and_mark_timestamps(monkeypatch):
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
                {"timestamp": "1100", "openInterestValue": "123456"}
            ]},
        },
        "tickers": {
            "retCode": 0,
            "time": 1200,
            "result": {"list": [{"markPrice": "50000", "fundingRate": "0.0012"}]},
        },
    }

    def fake_get(path, params):
        return responses[path]

    monkeypatch.setattr(provider, "_get", fake_get)
    monkeypatch.setattr(
        "aicfa.derivatives_market_data._collect_bybit_liquidations",
        lambda symbol, timeout_seconds: [{
            "timestamp": 1200,
            "liquidation_volume": 2500.0,
            "long_liquidation_volume": 2500.0,
            "short_liquidation_volume": 0.0,
        }],
    )
    frame = provider.fetch_derivatives(symbol="BTCUSDT", limit=10)

    assert frame.iloc[-1]["funding_rate"] == 0.0012
    assert frame.iloc[-1]["open_interest"] == 123456.0
    assert frame.iloc[-1]["mark_price"] == 50000.0
    complete, missing = derivatives_completeness(frame)
    assert complete, missing

def test_ccxt_derivatives_provider_normalizes_funding_oi_and_mark():
    class FakeExchange:
        def __init__(self, *args, **kwargs):
            self.markets = {"BTC/USDT:USDT": {}}
            self.timeout = None
        def load_markets(self):
            return self.markets
        def fetch_funding_rate_history(self, symbol, since, limit):
            return [{"timestamp": 1000, "fundingRate": "0.001"}]
        def fetch_open_interest_history(self, symbol, timeframe, since, limit):
            return [{"timestamp": 1000, "openInterestValue": "1000"}]
        def fetch_funding_rate(self, symbol):
            return {"timestamp": 1000, "fundingRate": 0.001, "markPrice": 50000}

    from aicfa.derivatives_market_data import CcxtDerivativesProvider
    provider = CcxtDerivativesProvider("fake", exchange_factory=lambda exchange_id: FakeExchange())
    frame = provider.fetch_derivatives(symbol="BTC/USDT:USDT", limit=10)
    assert frame["funding_rate"].notna().any()
    assert frame["open_interest"].notna().any()
    assert frame["mark_price"].notna().any()
    assert frame.iloc[-1]["mark_price"] == 50000.0

def test_ccxt_okx_open_interest_history_uses_base_currency():
    class FakeExchange:
        def __init__(self, *args, **kwargs):
            self.markets = {"XAU/USDT:USDT": {}}
            self.timeout = None
            self.seen_oi_symbol = None
        def load_markets(self):
            return self.markets
        def fetch_funding_rate_history(self, symbol, since, limit):
            return [{"timestamp": 1000, "fundingRate": "0.001"}]
        def fetch_open_interest_history(self, symbol, timeframe, since, limit):
            self.seen_oi_symbol = symbol
            return [{"timestamp": 1000, "openInterestValue": "123"}]
        def fetch_funding_rate(self, symbol):
            return {"timestamp": 1000, "fundingRate": 0.001, "markPrice": 3000}

    from aicfa.derivatives_market_data import CcxtDerivativesProvider
    fake = FakeExchange()
    provider = CcxtDerivativesProvider("okx", exchange_factory=lambda exchange_id: fake)
    provider.fetch_derivatives(symbol="XAU/USDT:USDT", limit=10)
    assert fake.seen_oi_symbol == "XAU"


def test_ccxt_derivatives_falls_back_to_current_oi_and_mark_info():
    class FakeExchange:
        def __init__(self, *args, **kwargs):
            self.markets = {"PEPE/USDT:USDT": {}}
            self.timeout = None
        def load_markets(self):
            return self.markets
        def fetch_funding_rate_history(self, symbol, since, limit):
            raise NotImplementedError("history unsupported")
        def fetch_funding_rate(self, symbol):
            return {"timestamp": 2000, "fundingRate": 0.001, "markPrice": None}
        def fetch_open_interest_history(self, symbol, timeframe, since, limit):
            raise NotImplementedError("history unsupported")
        def fetch_open_interest(self, symbol):
            return {"timestamp": 2000, "openInterestValue": "123"}
        def fetch_ticker(self, symbol):
            return {"timestamp": 2000, "last": "2", "info": {"markPx": "2.5"}}

    from aicfa.derivatives_market_data import CcxtDerivativesProvider
    provider = CcxtDerivativesProvider("okx", exchange_factory=lambda exchange_id: FakeExchange())
    frame = provider.fetch_derivatives(symbol="PEPE/USDT:USDT", limit=10)
    assert frame["funding_rate"].notna().any()
    assert frame["open_interest"].notna().any()
    assert frame.iloc[-1]["mark_price"] == 2.5


def test_ccxt_gateio_provider_uses_swap_market_type():
    class FakeExchange:
        def __init__(self, options):
            self.options = options
            self.markets = {}
            self.timeout = None

    seen = {}
    def factory(options):
        seen.update(options)
        return FakeExchange(options)

    from aicfa.derivatives_market_data import CcxtDerivativesProvider
    CcxtDerivativesProvider("gateio", exchange_factory=factory)
    assert seen["options"]["defaultType"] == "swap"

def test_ccxt_gateio_accepts_gate_constructor_alias(monkeypatch):
    class FakeExchange:
        def __init__(self, options):
            self.options = options
            self.markets = {}
            self.timeout = None

    def factory(options):
        return FakeExchange(options)

    fake_ccxt = type("FakeCCXT", (), {"gate": staticmethod(factory)})()
    monkeypatch.setitem(__import__("sys").modules, "ccxt", fake_ccxt)

    from aicfa.derivatives_market_data import CcxtDerivativesProvider
    provider = CcxtDerivativesProvider("gateio")
    assert provider.exchange == "gateio"
    assert provider._exchange.options["options"]["defaultType"] == "swap"


def test_fallback_can_combine_derivative_fields_from_different_venues():
    from aicfa.derivatives_market_data import FallbackDerivativesProvider

    class Provider:
        def __init__(self, exchange, frame):
            self.exchange = exchange
            self.frame = frame

        def fetch_derivatives(self, **kwargs):
            return self.frame

    def frame(**values):
        row = {"timestamp": 1000}
        row.update(values)
        return pd.DataFrame([row])

    provider = FallbackDerivativesProvider(providers=(
        Provider("funding_venue", frame(funding_rate=0.001)),
        Provider("oi_venue", frame(open_interest=123.0)),
        Provider("mark_venue", frame(mark_price=50000.0)),
    ))
    out, sources = provider.fetch_derivatives(
        symbol="XCU/USDT",
        limit=5,
    )
    assert out["funding_rate"].notna().any()
    assert out["open_interest"].notna().any()
    assert out["mark_price"].notna().any()
    assert sources == "funding_venue,oi_venue,mark_venue"


def test_ccxt_provider_uses_explicit_native_futures_symbol():
    class FakeExchange:
        def __init__(self, *args, **kwargs):
            self.markets = {"COPPER/USDT:USDT": {"type": "swap"}}
            self.timeout = None
            self.seen = []

        def load_markets(self):
            return self.markets

        def fetch_funding_rate_history(self, symbol, since, limit):
            self.seen.append(("funding", symbol))
            return [{"timestamp": 1000, "fundingRate": "0.001"}]

        def fetch_open_interest_history(self, symbol, timeframe, since, limit):
            self.seen.append(("oi", symbol))
            return [{"timestamp": 1000, "openInterestValue": "123"}]

        def fetch_funding_rate(self, symbol):
            self.seen.append(("current", symbol))
            return {"timestamp": 1000, "fundingRate": 0.001, "markPrice": 50000}

    from aicfa.derivatives_market_data import CcxtDerivativesProvider
    fake = FakeExchange()
    provider = CcxtDerivativesProvider(
        "bitget",
        exchange_factory=lambda options: fake,
    )
    frame = provider.fetch_derivatives(
        symbol="XCU/USDT",
        native_symbol="COPPER/USDT:USDT",
        limit=5,
    )
    assert frame["open_interest"].notna().any()
    assert all(symbol == "COPPER/USDT:USDT" for _, symbol in fake.seen)
