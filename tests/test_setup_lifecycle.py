import asyncio
import tempfile
import time
import unittest
from unittest.mock import patch
from pathlib import Path
from types import SimpleNamespace

import app.main as main
from app.smc.setup_store import SetupStore


class AcceptedLifecycleTests(unittest.TestCase):
    def setUp(self):
        self._original_store = main.setup_store
        self._original_market_data = main.market_data
        self.tmp = tempfile.TemporaryDirectory()
        self.store = SetupStore(Path(self.tmp.name) / "setups.sqlite3")
        main.setup_store = self.store

    def tearDown(self):
        main.setup_store = self._original_store
        main.market_data = self._original_market_data
        self.tmp.cleanup()

    def accepted_setup(self, key="BTCUSDT:scalp:long:OB:1:2"):
        payload = {
            "key": key, "symbol": "BTCUSDT", "profile": "scalp",
            "direction": "long", "status": "ACCEPTED",
            "confirmation_time_ms": 1_000, "confirmation_price": 100.0,
            "stop_price": 95.0, "targets": [110.0, 115.0],
            "score": 7, "zone": [98.0, 101.0], "timeframe": "5m",
        }
        saved, decided = self.store.save_decision(payload, cooldown_minutes=0, max_active=100)
        self.assertTrue(saved)
        self.assertEqual(decided["status"], "ACCEPTED")
        return payload

    def test_existing_fresh_pac_candidate_is_backfilled_to_accepted(self):
        now_ms = int(time.time() * 1000)
        payload = {
            "key": "SOLUSDT:scalp:long:PAC:OB:100:200",
            "symbol": "SOLUSDT", "profile": "scalp", "direction": "long",
            "status": "CANDIDATE", "confirmation_time_ms": now_ms - 10_000,
            "confirmation_price": 100.0, "stop_price": 95.0, "targets": [110.0],
            "score": 7, "zone": [98.0, 101.0], "timeframe": "5m",
        }
        saved, _ = self.store.save_decision(payload, cooldown_minutes=0, max_active=100)
        self.assertTrue(saved)
        migrated = SetupStore(self.store.path)
        active = migrated.list_active()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["status"], "ACCEPTED")
        with migrated._connection() as db:
            events = [
                row["event_type"] for row in db.execute(
                    "SELECT event_type FROM setup_candidate_events WHERE setup_key=?",
                    (payload["key"],),
                ).fetchall()
            ]
        self.assertIn("SETUP_ACCEPTED", events)

    def test_pac_scanner_candidate_enters_accepted_tracking(self):
        now_ms = int(time.time() * 1000)
        candle = SimpleNamespace(
            symbol="BTCUSDT", timeframe="5m", close_time_ms=now_ms - 10_000,
            open_time_ms=now_ms - 310_000, open=100.0, high=101.0,
            low=99.0, close=100.0, volume=10.0,
        )
        payload = {
            "key": "BTCUSDT:scalp:PAC:long:OB:1:2",
            "symbol": "BTCUSDT", "profile": "scalp", "direction": "long",
            "status": "CANDIDATE", "confirmation_time_ms": candle.close_time_ms,
            "confirmation_price": 100.0, "stop_price": 95.0, "targets": [110.0],
            "score": 7, "reasons": ["pac_structure"], "zone": [98.0, 101.0],
            "timeframe": "5m", "evidence": {}, "atr": 1.0,
        }
        candidate = SimpleNamespace(**payload, as_dict=lambda: dict(payload))
        main.market_data = SimpleNamespace(
            candles={("BTCUSDT", "5m"): [candle]},
            exchange_filters={"BTCUSDT": {"tick_size": 0.1}},
        )
        with patch.object(main, "scan_symbol", return_value=[candidate]):
            asyncio.run(main._on_closed_candle(candle))
        active = self.store.list_active()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["status"], "ACCEPTED")
        with self.store._connection() as db:
            event_types = [
                row["event_type"] for row in db.execute(
                    "SELECT event_type FROM setup_candidate_events WHERE setup_key=?",
                    (payload["key"],),
                ).fetchall()
            ]
        self.assertIn("SETUP_ACCEPTED", event_types)

    def candle(self, *, close_time_ms, low, high, close):
        return SimpleNamespace(
            symbol="BTCUSDT", timeframe="1m", close_time_ms=close_time_ms,
            low=low, high=high, close=close,
        )

    def test_accepted_setup_closes_and_is_journaled_at_tp1(self):
        self.accepted_setup()
        main._advance_active_setups(self.candle(
            close_time_ms=2_000, low=100.5, high=111.0, close=110.0
        ), publish=False)
        journal = self.store.list_journal()
        self.assertEqual(len(journal), 1)
        self.assertEqual(journal[0]["final_status"], "TP1")
        self.assertAlmostEqual(journal[0]["gross_r"], 2.0)
        self.assertEqual(self.store.active_count(), 0)

    def test_stop_wins_when_stop_and_target_hit_in_same_candle(self):
        self.accepted_setup()
        main._advance_active_setups(self.candle(
            close_time_ms=2_000, low=94.0, high=111.0, close=105.0
        ), publish=False)
        journal = self.store.list_journal()
        self.assertEqual(len(journal), 1)
        self.assertEqual(journal[0]["final_status"], "SL")

    def test_accepted_setup_expires_after_profile_lifetime(self):
        self.accepted_setup()
        main._advance_active_setups(self.candle(
            close_time_ms=1_000 + 3 * 3_600_000, low=99.0, high=101.0, close=102.0
        ), publish=False)
        journal = self.store.list_journal()
        self.assertEqual(len(journal), 1)
        self.assertEqual(journal[0]["final_status"], "EXPIRED")
        self.assertAlmostEqual(journal[0]["gross_r"], 0.4)


if __name__ == "__main__":
    unittest.main()
