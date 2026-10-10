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
    monkeypatch.setattr(server, "_scanner_health", lambda: {
        "ok": True,
        "scanner": "running",
        "automatic_worker_running": True,
    })

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
                expected_count = len(json.loads(
                    (server.ROOT.parent / "config" / "market_universe.json").read_text(
                        encoding="utf-8"
                    )
                )["markets"])
                assert len(payload["markets"]) == expected_count
                break
            except Exception:
                time.sleep(0.05)
        else:
            process.terminate()
            try:
                _, stderr = process.communicate(timeout=1)
            except subprocess.TimeoutExpired:
                process.kill()
                _, stderr = process.communicate(timeout=1)
            raise AssertionError(f"web server did not start: {stderr}")
    finally:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)



def test_web_health_does_not_report_live_when_scanner_worker_is_stopped(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    journal = PersistentJournal(data_dir / "journal" / "events.jsonl")
    journal.append("scan", 123, {"scan_number": 1, "markets": []})
    monkeypatch.setattr(server, "DATA_DIR", data_dir)
    monkeypatch.setattr(server, "_scanner_health", lambda: {
        "ok": True,
        "scanner": "stopped",
        "automatic_worker_running": False,
        "last_scan_status": "restarting",
    })

    health = json.loads(server._journal_payload("/api/health", {}))

    assert health["journal_ok"] is True
    assert health["automatic_worker_running"] is False
    assert health["scanner_ok"] is False
    assert health["ok"] is False



def test_market_prices_are_cached_across_concurrent_poll_intervals(monkeypatch):
    calls = []
    server._MARKET_PRICES_CACHE = None
    monkeypatch.setattr(server, "_market_prices_uncached", lambda: calls.append(1) or b'{"prices":{"0":100}}')
    monkeypatch.setattr(server, "_MARKET_PRICES_CACHE_TTL_SECONDS", 10.0)

    first = server._market_prices()
    second = server._market_prices()

    assert first == second == b'{"prices":{"0":100}}'
    assert len(calls) == 1
    server._MARKET_PRICES_CACHE = None



def test_trade_monitor_api_returns_all_current_revision_lifecycles_and_keeps_mode(tmp_path, monkeypatch):
    from aicfa.setup_registry import SetupRegistry, REGISTRY_REVISION

    data_dir = tmp_path / "data"
    registry = SetupRegistry(data_dir / "journal" / "setup_registry.json")
    registry._write({
        "BTC|SCALPING": {
            "strategy_revision": REGISTRY_REVISION,
            "setup_id": "BTC|SCALPING",
            "asset": "BTC/USDT",
            "mode": "scalping",
            "direction": "LONG",
            "status": "ACTIVE",
            "created_at_ms": 100,
            "last_seen_at_ms": 200,
            "setup": {"candidate": {"direction": "long", "entry_zone": [], "target_levels": []}},
        },
        "ETH|POSITION": {
            "strategy_revision": REGISTRY_REVISION,
            "setup_id": "ETH|POSITION",
            "asset": "ETH/USDT",
            "mode": "position",
            "direction": "SHORT",
            "status": "COMPLETED",
            "created_at_ms": 50,
            "closed_at_ms": 300,
            "setup": {"candidate": {"direction": "short", "entry_zone": [], "target_levels": []}},
        },
        "STALE|SWING": {
            "strategy_revision": REGISTRY_REVISION,
            "setup_id": "STALE|SWING",
            "asset": "XRP/USDT",
            "mode": "swing",
            "status": "STALE",
            "setup": {},
        },
        "OLD|INTRADAY": {
            "strategy_revision": 1,
            "setup_id": "OLD|INTRADAY",
            "asset": "OLD/USDT",
            "mode": "intraday",
            "status": "ACTIVE",
            "setup": {},
        },
    })
    monkeypatch.setattr(server, "DATA_DIR", data_dir)
    monkeypatch.setenv("AICFA_DATA_DIR", str(data_dir))

    payload = json.loads(server._journal_payload("/api/journal/trade-monitor", {}))
    records = payload["setups"]

    assert {item["mode"] for item in records} == {"scalping", "position"}
    assert {item["status"] for item in records} == {"ACTIVE", "COMPLETED"}
    assert next(item for item in records if item["status"] == "COMPLETED")["closed_at_ms"] == 300
