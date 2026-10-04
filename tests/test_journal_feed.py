from __future__ import annotations

import json
from threading import Thread
from urllib.request import Request, urlopen

from aicfa.journal_feed import create_handler
from aicfa.persistent_journal import PersistentJournal
from http.server import ThreadingHTTPServer


def _server(journal: PersistentJournal):
    server = ThreadingHTTPServer(("127.0.0.1", 0), create_handler(journal))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def _get(server, path: str):
    with urlopen(f"http://127.0.0.1:{server.server_port}{path}", timeout=2) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def test_feed_exposes_events_scans_and_setups(tmp_path):
    journal = PersistentJournal(tmp_path / "events.jsonl")
    journal.append(
        "scan",
        123,
        {
            "scan_number": 1,
            "markets": [
                {
                    "asset": "BTCUSDT",
                    "setups": [{"mode": "intraday", "direction": "long"}],
                    "lifecycle_results": [],
                }
            ],
        },
    )
    journal.append("rotation_cycle", 124, {"cycle_id": 1})

    server, _ = _server(journal)
    try:
        status, events = _get(server, "/api/journal/events?limit=10")
        assert status == 200
        assert len(events["events"]) == 2

        status, scans = _get(server, "/api/journal/scans?limit=10")
        assert status == 200
        assert len(scans["events"]) == 1

        status, setups = _get(server, "/api/journal/setups?limit=10")
        assert status == 200
        assert setups["setups"][0]["asset"] == "BTCUSDT"
        assert setups["setups"][0]["setup"]["direction"] == "long"
    finally:
        server.shutdown()
        server.server_close()


def test_feed_is_read_only_and_has_health(tmp_path):
    journal = PersistentJournal(tmp_path / "events.jsonl")
    server, _ = _server(journal)
    try:
        status, health = _get(server, "/api/health")
        assert status == 200
        assert health["ok"] is True

        request = Request(
            f"http://127.0.0.1:{server.server_port}/api/journal/events",
            method="POST",
        )
        try:
            urlopen(request, timeout=2)
        except Exception as exc:
            assert getattr(exc, "code", None) == 405
    finally:
        server.shutdown()
        server.server_close()
