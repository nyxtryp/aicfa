import json

import pytest

from aicfa.market_universe import MarketUniverse, MonitoredMarket, load_market_universe


def test_universe_normalizes_assets_and_preserves_market_type():
    universe = MarketUniverse.from_assets([" btc/usdt ", "ETH-USDT"], market_type="spot")

    assert universe.assets == ("BTC/USDT", "ETH/USDT")
    assert universe.market_types == ("spot", "spot")


def test_universe_rejects_duplicate_markets():
    with pytest.raises(ValueError, match="duplicate"):
        MarketUniverse((
            MonitoredMarket("BTC/USDT"),
            MonitoredMarket("btc-usdt"),
        ))


def test_universe_requires_base_quote_pair():
    with pytest.raises(ValueError, match="base/quote"):
        MonitoredMarket("BTC")


def test_universe_loads_json_configuration(tmp_path):
    path = tmp_path / "markets.json"
    path.write_text(
        json.dumps({
            "markets": [
                {"asset": "BTC/USDT", "market_type": "spot"},
                {"asset": "ETH/USDT", "market_type": "futures"},
            ]
        }),
        encoding="utf-8",
    )

    universe = load_market_universe(path)

    assert universe.markets == (
        MonitoredMarket("BTC/USDT", "spot"),
        MonitoredMarket("ETH/USDT", "futures"),
    )


def test_universe_rejects_invalid_json_shape(tmp_path):
    path = tmp_path / "markets.json"
    path.write_text(json.dumps({"assets": ["BTC/USDT"]}), encoding="utf-8")

    with pytest.raises(ValueError, match="markets"):
        load_market_universe(path)


def test_universe_supports_tradfi_metadata_and_native_symbols():
    market = MonitoredMarket(
        "AAPL/USDT",
        market_type="futures",
        asset_class="tradfi",
        category="stock",
        instrument_type="perpetual",
        venue_symbols=(("bybit", "AAPLUSDT"), ("okx", "AAPLUSD")),
    )

    assert market.asset_class == "tradfi"
    assert market.category == "stock"
    assert market.instrument_type == "perpetual"
    assert market.venue_symbols == (
        ("bybit", "AAPLUSDT"),
        ("okx", "AAPLUSD"),
    )


def test_universe_loads_tradfi_metadata_without_changing_crypto_defaults(tmp_path):
    path = tmp_path / "markets.json"
    path.write_text(
        json.dumps({
            "markets": [
                {"asset": "BTC/USDT", "market_type": "spot"},
                {
                    "asset": "SPX/USDT",
                    "market_type": "futures",
                    "asset_class": "tradfi",
                    "category": "index",
                    "instrument_type": "perpetual",
                    "venue_symbols": {
                        "bybit": "SPXUSDT",
                        "okx": "SPXUSD",
                    },
                },
            ]
        }),
        encoding="utf-8",
    )

    universe = load_market_universe(path)

    assert universe.markets[0] == MonitoredMarket("BTC/USDT", "spot")
    assert universe.markets[1].asset_class == "tradfi"
    assert universe.markets[1].venue_symbols == (
        ("bybit", "SPXUSDT"),
        ("okx", "SPXUSD"),
    )


def test_universe_rejects_duplicate_native_venues():
    with pytest.raises(ValueError, match="duplicate venues"):
        MonitoredMarket(
            "AAPL/USDT",
            market_type="futures",
            asset_class="tradfi",
            category="stock",
            venue_symbols=(("bybit", "AAPLUSDT"), ("BYBIT", "AAPLUSDT")),
        )
