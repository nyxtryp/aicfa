import tempfile
import unittest
from pathlib import Path

from app.smc.setup_store import SetupStore


class SetupDecisionStoreTests(unittest.TestCase):
    def candidate(self, key, symbol="BTCUSDT", profile="scalp", status="ACCEPTED"):
        return {
            "key": key, "symbol": symbol, "profile": profile, "direction": "long",
            "status": status, "confirmation_time_ms": 1_000_000,
            "score": 8, "zone_key": f"{symbol}:{profile}:long:100:101",
            "confirmation_price": 100.0, "stop_price": 95.0,
            "targets": [110.0, 115.0, 120.0], "gross_r": 0.0, "commission_r": 0.0,
        }

    def test_global_and_symbol_profile_caps_are_atomic(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SetupStore(Path(directory) / "setups.sqlite3")
            inserted, first = store.save_decision(self.candidate("one"), cooldown_minutes=30)
            self.assertTrue(inserted)
            self.assertEqual(first["status"], "ACCEPTED")
            inserted, second = store.save_decision(self.candidate("two"), cooldown_minutes=30)
            self.assertTrue(inserted)
            self.assertEqual(second["status"], "REJECTED")
            self.assertIn("active_setup_for_symbol_profile", second["decision_reasons"])
            self.assertEqual(store.active_count(), 1)

    def test_lifecycle_transition_writes_realized_journal_once(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SetupStore(Path(directory) / "setups.sqlite3")
            candidate = self.candidate("one")
            self.assertTrue(store.save_decision(candidate, cooldown_minutes=30)[0])
            closed = dict(candidate, status="CLOSED", net_r=1.2)
            journal = {
                "key": "one", "symbol": "BTCUSDT", "profile": "scalp",
                "direction": "long", "final_status": "TP3",
                "opened_at_ms": 1_000_000, "closed_at_ms": 2_000_000,
                "gross_r": 1.3, "commission_r": 0.1, "net_r": 1.2,
            }
            self.assertTrue(store.transition("one", closed, event_type="TP3",
                                             event_time_ms=2_000_000, final_journal=journal))
            self.assertEqual(store.list_active(), [])
            self.assertEqual(store.list_journal(), [journal])
            self.assertFalse(store.transition("one", closed, event_type="TP3",
                                              event_time_ms=2_000_001, final_journal=journal))


if __name__ == "__main__":
    unittest.main()
