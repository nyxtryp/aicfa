from aicfa.market_source_registry import (
    MarketCapability,
    MarketSourceRegistry,
    SourceDescriptor,
    default_market_source_registry,
)


def test_default_registry_is_priority_ordered():
    names = [source.name for source in default_market_source_registry().sources]
    assert names == [
        "binance",
        "bybit",
        "bitget",
        "kraken",
        "kucoin",
        "gate",
        "mexc",
        "coinlore",
        "coingecko",
    ]


def test_capability_fallback_keeps_specialized_sources_ahead_of_aggregators():
    registry = default_market_source_registry()
    chain = registry.fallback_chain(
        required={
            MarketCapability.SYMBOLS,
            MarketCapability.OHLCV,
            MarketCapability.ORDER_BOOK,
            MarketCapability.FUNDING,
        }
    )
    assert [source.name for source in chain] == [
        "binance",
        "bybit",
        "bitget",
        "kucoin",
        "gate",
        "mexc",
    ]


def test_registry_does_not_select_source_missing_required_capability():
    registry = MarketSourceRegistry(
        [
            SourceDescriptor(
                "primary",
                10,
                frozenset({MarketCapability.SYMBOLS, MarketCapability.OHLCV}),
            ),
            SourceDescriptor(
                "fallback",
                20,
                frozenset({
                    MarketCapability.SYMBOLS,
                    MarketCapability.OHLCV,
                    MarketCapability.TRADES,
                }),
            ),
        ]
    )
    assert registry.best(
        required={
            MarketCapability.SYMBOLS,
            MarketCapability.OHLCV,
            MarketCapability.TRADES,
        }
    ).name == "fallback"


def test_registry_rejects_duplicate_names():
    try:
        MarketSourceRegistry(
            [
                SourceDescriptor("same", 10, frozenset()),
                SourceDescriptor("same", 20, frozenset()),
            ]
        )
    except ValueError as exc:
        assert "unique" in str(exc)
    else:
        raise AssertionError("duplicate source names must fail")
