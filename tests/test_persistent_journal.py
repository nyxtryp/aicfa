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
