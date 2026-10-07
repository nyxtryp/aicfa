from __future__ import annotations

import json

from aicfa.persistent_journal import PersistentJournal
import web.server as server


def test_web_journal_api_reads_shared_storage_without_feed(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    journal = PersistentJournal(data_dir / "journal" / "events.jsonl")
    journal.append(
        "scan",
        123,
        {
            "scan_number": 1,
            "rotation_id": 1,
            "queue_position": 1,
            "universe_size": 2,
            "markets": [{"asset": "BTC/USDT", "setups": [], "horizons": []}],
        },
    )
    monkeypatch.setattr(server, "DATA_DIR", data_dir)
    monkeypatch.setenv("AICFA_DATA_DIR", str(data_dir))

    health = json.loads(server._journal_payload("/api/health", {}))
    scans = json.loads(server._journal_payload("/api/journal/scans", {"limit": ["10"]}))

    assert health["ok"] is True
    assert len(scans["events"]) == 1
    assert scans["events"][0]["payload"]["markets"][0]["asset"] == "BTC/USDT"
