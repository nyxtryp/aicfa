from aicfa.public_market_data import build_public_market_data_provider

def test_public_provider_chain_is_native_first_and_has_unique_venues(monkeypatch):
    class FakeSource:
        def __init__(self, name):
            self.provider = type("Provider", (), {"exchange": name})()
    monkeypatch.setattr(
        "aicfa.public_market_data.build_ccxt_sources",
        lambda ids, timeout_seconds: tuple(FakeSource(name) for name in ids),
    )
    provider = build_public_market_data_provider(timeout_seconds=1)
    names = [item.exchange for item in provider.providers]
    assert names[:2] == ["binance", "bybit"]
    assert len(names) == len(set(names))
    assert "okx" in names
    assert "binance" not in names[2:]
    assert "bybit" not in names[2:]
