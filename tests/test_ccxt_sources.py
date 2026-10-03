from aicfa.ccxt_sources import build_ccxt_registry, build_ccxt_sources
from aicfa.market_source_registry import MarketCapability


class FakeExchange:
    has = {
        "fetchOHLCV": True,
        "fetchTrades": True,
        "fetchOrderBook": True,
        "fetchFundingRate": True,
        "fetchOpenInterest": True,
        "fetchLiquidations": True,
        "fetchMarkPrice": True,
    }

    def __init__(self):
        self.timeout = None
        self.markets = {}

    def load_markets(self):
        return {}


def fake_factory(_exchange_id):
    return FakeExchange()


def test_ccxt_sources_build_descriptors_from_exchange_capabilities(monkeypatch):
    from aicfa.ccxt_market_data import CcxtMarketDataProvider
    monkeypatch.setattr("aicfa.ccxt_sources.CcxtMarketDataProvider",
        lambda exchange_id, timeout_seconds: CcxtMarketDataProvider(
            exchange_id, timeout_seconds=timeout_seconds, exchange_factory=fake_factory))
    sources = build_ccxt_sources(["fake"], timeout_seconds=3)
    assert len(sources) == 1
    assert sources[0].descriptor.name == "fake"
    assert MarketCapability.OHLCV in sources[0].descriptor.capabilities
    assert MarketCapability.ORDER_BOOK in sources[0].descriptor.capabilities


def test_ccxt_registry_orders_sources_by_priority(monkeypatch):
    from aicfa.ccxt_market_data import CcxtMarketDataProvider
    monkeypatch.setattr("aicfa.ccxt_sources.CcxtMarketDataProvider",
        lambda exchange_id, timeout_seconds: CcxtMarketDataProvider(
            exchange_id, timeout_seconds=timeout_seconds, exchange_factory=fake_factory))
    registry = build_ccxt_registry(["second", "first"])
    assert [source.name for source in registry.sources] == ["second", "first"]
