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


def test_market_price_candidates_normalize_perpetual_symbols():
    assert server._ticker_symbol_candidates({
        "asset": "BTC/USDT",
        "market_type": "futures",
    }) == ("BTCUSDT",)
    assert server._ticker_symbol_candidates({
        "asset": "XAU/USDT",
        "market_type": "futures",
        "venue_symbols": {"bybit": "XAU/USDT:USDT"},
    }) == ("XAUUSDT",)


def test_web_server_entrypoint_starts_outside_pytest_import_path(tmp_path):
    import os
    import socket
    import subprocess
    import sys
    import time
    from urllib.request import urlopen

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    env = os.environ.copy()
    env["PORT"] = str(port)
    env["AICFA_DATA_DIR"] = str(tmp_path / "data")
    process = subprocess.Popen(
        [sys.executable, "web/server.py"],
        cwd=server.ROOT.parent,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            try:
                with urlopen(f"http://127.0.0.1:{port}/api/markets", timeout=1) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                assert response.status == 200
                assert len(payload["markets"]) == 109
                break
            except Exception:
                time.sleep(0.05)
        else:
            stderr = process.stderr.read() if process.stderr else ""
            raise AssertionError(f"web server did not start: {stderr}")
    finally:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)
