from __future__ import annotations

import json

from aicfa.persistent_journal import PersistentJournal


def test_journal_appends_and_reads_recent_events(tmp_path):
    journal = PersistentJournal(tmp_path / "journal" / "events.jsonl")

    journal.append("scan", 1000, {"scan_number": 1, "markets": []})
    journal.append("lifecycle", 1100, {"asset": "ETH/USDT", "status": "active"})

    records = journal.read()
    assert len(records) == 2
    assert records[0]["event_type"] == "scan"
    assert records[1]["payload"]["asset"] == "ETH/USDT"
    assert (tmp_path / "journal" / "events.jsonl").exists()


def test_journal_is_jsonl_and_keeps_latest_limit(tmp_path):
    journal = PersistentJournal(tmp_path / "events.jsonl")
    for index in range(3):
        journal.append("scan", index, {"index": index})

    records = journal.read(limit=2)
    assert [item["payload"]["index"] for item in records] == [1, 2]
    assert all(json.dumps(item) for item in records)


def test_visual_market_geometry_projects_smc_objects_to_candle_time():
    import pandas as pd
    from types import SimpleNamespace

    from aicfa.persistent_journal import _visual_market_geometry

    frame = pd.DataFrame(
        {
            "timestamp": [1_000, 2_000, 3_000],
            "open": [100.0, 101.0, 102.0],
            "high": [101.0, 103.0, 104.0],
            "low": [99.0, 100.0, 101.0],
            "close": [100.5, 102.0, 103.5],
            "fvg_bullish": [1, 0, 0],
            "fvg_bullish_low": [99.5, 99.5, 99.5],
            "fvg_bullish_high": [100.5, 100.5, 100.5],
            "fvg_active": [1, 1, 1],
            "order_block_bullish": [1, 0, 0],
            "order_block_bullish_low": [98.0, 98.0, 98.0],
            "order_block_bullish_high": [99.0, 99.0, 99.0],
            "order_block_active": [1, 1, 1],
            "bos_up": [0, 1, 0],
            "bos_up_reference_pivot_index": [0, 0, 0],
            "active_buy_liquidity_price": [97.0, 97.0, 97.5],
            "active_sell_liquidity_price": [105.0, 105.0, 106.0],
        }
    )

    geometry = _visual_market_geometry(SimpleNamespace(frames={"1h": frame}))

    assert geometry["zones"]
    assert {item["type"] for item in geometry["zones"]} == {"fvg", "ob"}
    assert geometry["events"][0]["type"] == "BOS"
    assert geometry["events"][0]["price"] == 101.0
    assert {item["type"] for item in geometry["liquidity"]} == {"buy", "sell"}
    assert all(item["timeEnd"] == 3_000 for item in geometry["zones"])
