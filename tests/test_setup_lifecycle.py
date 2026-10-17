import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import app.main as main
from app.smc.setup_store import SetupStore


class AcceptedLifecycleTests(unittest.TestCase):
    def setUp(self):
        self._original_store = main.setup_store
        self.tmp = tempfile.TemporaryDirectory()
        self.store = SetupStore(Path(self.tmp.name) / "setups.sqlite3")
        main.setup_store = self.store

    def tearDown(self):
        main.setup_store = self._original_store
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

    def candle(self, *, close_time_ms, low, high, close):
        return SimpleNamespace(
            symbol="BTCUSDT", timeframe="1m", close_time_ms=close_time_ms,
            low=low, high=high, close=close,
        )

    def test_accepted_setup_is_journaled_only_after_final_close(self):
        self.accepted_setup()
        main._advance_active_setups(self.candle(
            close_time_ms=2_000, low=100.5, high=111.0, close=110.0
        ), publish=False)
        self.assertEqual(self.store.list_candidates()[0]["status"], "TP1")
        self.assertEqual(self.store.list_journal(), [])
        main._advance_active_setups(self.candle(
            close_time_ms=3_000, low=99.0, high=109.0, close=100.0
        ), publish=False)
        journal = self.store.list_journal()
        self.assertEqual(len(journal), 1)
        self.assertEqual(journal[0]["final_status"], "SL")
        self.assertAlmostEqual(journal[0]["gross_r"], 2.0)

    def test_stop_wins_when_stop_and_target_hit_in_same_candle(self):
        self.accepted_setup()
        main._advance_active_setups(self.candle(
            close_time_ms=2_000, low=94.0, high=111.0, close=105.0
        ), publish=False)
        journal = self.store.list_journal()
        self.assertEqual(len(journal), 1)
        self.assertEqual(journal[0]["final_status"], "SL")
        self.assertEqual(self.store.list_candidates()[0]["status"], "SL")

    def test_accepted_setup_expires_after_profile_lifetime(self):
        self.accepted_setup()
        main._advance_active_setups(self.candle(
            close_time_ms=1_000 + 3 * 3_600_000, low=99.0, high=101.0, close=102.0
        ), publish=False)
        journal = self.store.list_journal()
        self.assertEqual(len(journal), 1)
        self.assertEqual(journal[0]["final_status"], "EXPIRED")
        self.assertAlmostEqual(journal[0]["gross_r"], 0.4)
        self.assertEqual(self.store.list_candidates()[0]["status"], "EXPIRED")


if __name__ == "__main__":
    unittest.main()
