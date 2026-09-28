from pathlib import Path

from scripts.download_ohlcv import symbol_slug


def test_symbol_slug():
    assert symbol_slug("BTC/USDT") == "BTC_USDT"


def test_raw_path_shape():
    root = Path(__file__).resolve().parents[1]
    assert root.name == "aicfa"
