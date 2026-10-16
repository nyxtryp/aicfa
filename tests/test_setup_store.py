import tempfile
import unittest
from pathlib import Path

from app.smc.setup_store import SetupStore


class SetupStoreTests(unittest.TestCase):
    def test_candidate_insert_is_idempotent_and_audited(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SetupStore(Path(directory) / "setups.sqlite3")
            payload = {
                "key": "BTCUSDT:scalp:long:OB:1:2",
                "symbol": "BTCUSDT",
                "profile": "scalp",
                "direction": "long",
                "status": "CANDIDATE",
                "confirmation_time_ms": 2000,
                "confirmation_price": 100.0,
                "stop_price": 95.0,
                "targets": [110.0],
                "score": 7,
                "reasons": ["sweep"],
                "zone": [98.0, 101.0],
                "timeframe": "5m",
            }
            self.assertTrue(store.save_candidate(payload))
            self.assertFalse(store.save_candidate(payload))
            self.assertEqual(store.list_candidates(), [payload])
            self.assertEqual(store.event_count(payload["key"]), 1)

    def test_cooldown_rejections_are_not_persisted(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SetupStore(Path(directory) / "setups.sqlite3")
            first = {
                "key": "BTCUSDT:scalp:long:OB:1:2",
                "symbol": "BTCUSDT",
                "profile": "scalp",
                "direction": "long",
                "status": "CANDIDATE",
                "confirmation_time_ms": 2000,
                "confirmation_price": 100.0,
                "stop_price": 95.0,
                "targets": [110.0],
                "score": 7,
                "reasons": [],
                "zone": [98.0, 101.0],
                "timeframe": "5m",
            }
            saved, _ = store.save_decision(first, cooldown_minutes=30)
            self.assertTrue(saved)

            repeated = dict(first)
            repeated.update({
                "key": "BTCUSDT:scalp:long:OB:1:3",
                "confirmation_time_ms": 2500,
            })
            saved, decision = store.save_decision(repeated, cooldown_minutes=30)
            self.assertFalse(saved)
            self.assertEqual(decision["status"], "REJECTED")
            self.assertIn("cooldown_active", decision["decision_reasons"])
            self.assertEqual(len(store.list_candidates(include_rejected=True)), 1)
            self.assertEqual(store.event_count(repeated["key"]), 0)

    def test_rejected_decisions_are_not_persisted(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SetupStore(Path(directory) / "setups.sqlite3")
            base = {
                "key": "SAMSUNGUSDT:scalp:long:OB:1:2",
                "symbol": "SAMSUNGUSDT",
                "profile": "scalp",
                "direction": "long",
                "status": "REJECTED",
                "confirmation_time_ms": 2000,
                "confirmation_price": 162.71,
                "stop_price": 162.67,
                "targets": [163.0],
                "score": 6,
                "reasons": ["sweep"],
                "zone": [162.6, 162.8],
                "timeframe": "5m",
                "decision_reasons": ["tradfi_market_closed"],
            }
            saved, returned = store.save_decision(base, cooldown_minutes=30)
            self.assertFalse(saved)
            self.assertEqual(returned["status"], "REJECTED")
            self.assertEqual(store.list_candidates(include_rejected=True), [])
            self.assertEqual(store.event_count(base["key"]), 0)

            normal = dict(base)
            normal.update({
                "key": "BTCUSDT:scalp:long:OB:1:2",
                "symbol": "BTCUSDT",
                "decision_reasons": ["risk_reward_below_minimum"],
            })
            saved, _ = store.save_decision(normal, cooldown_minutes=30)
            self.assertFalse(saved)
            self.assertEqual(store.list_candidates(include_rejected=True), [])


if __name__ == "__main__":
    unittest.main()
