from pathlib import Path

from scripts.download_ohlcv import symbol_slug


def test_symbol_slug():
    assert symbol_slug("BTC/USDT") == "BTC_USDT"


def test_raw_path_shape():
    root = Path(__file__).resolve().parents[1]
    # Local checkouts use the repository name; FrostDeploy runs tests from
    # immutable timestamped release directories under /releases/.
    assert root.name == "aicfa" or root.parent.name == "releases"
