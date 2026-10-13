import tempfile
import unittest
from decimal import Decimal
from unittest.mock import patch

from app.main import _advance_active_setups
from app.market_data import ClosedCandle
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


    def test_global_active_cap_is_eight(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SetupStore(Path(directory) / "setups.sqlite3")
            for index in range(8):
                inserted, payload = store.save_decision(
                    self.candidate(f"key-{index}", symbol=f"SYM{index}"),
                    cooldown_minutes=30,
                )
                self.assertTrue(inserted)
                self.assertEqual(payload["status"], "ACCEPTED")
            inserted, ninth = store.save_decision(
                self.candidate("key-9", symbol="SYM9"), cooldown_minutes=30
            )
            self.assertTrue(inserted)
            self.assertEqual(ninth["status"], "REJECTED")
            self.assertIn("active_setup_limit_reached", ninth["decision_reasons"])
            self.assertEqual(store.active_count(), 8)

    def test_zone_cooldown_survives_setup_completion(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SetupStore(Path(directory) / "setups.sqlite3")
            first = self.candidate("first")
            self.assertTrue(store.save_decision(first, cooldown_minutes=30)[0])
            closed = dict(first, status="CLOSED")
            self.assertTrue(store.transition("first", closed, event_type="CLOSED",
                                             event_time_ms=1_100_000))
            second = self.candidate("second")
            second["confirmation_time_ms"] = 1_200_000
            inserted, decision = store.save_decision(second, cooldown_minutes=30)
            self.assertTrue(inserted)
            self.assertEqual(decision["status"], "REJECTED")
            self.assertIn("cooldown_active", decision["decision_reasons"])

    def test_expiry_realizes_remaining_position_at_last_close(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SetupStore(Path(directory) / "setups.sqlite3")
            candidate = self.candidate("expires")
            self.assertTrue(store.save_decision(candidate, cooldown_minutes=30)[0])
            candle = ClosedCandle(
                symbol="BTCUSDT", timeframe="1m",
                open_time_ms=11_840_000, close_time_ms=11_899_999,
                open=Decimal("104"), high=Decimal("105"),
                low=Decimal("102"), close=Decimal("105"),
                volume=Decimal("10"),
            )
            with patch("app.main._get_setup_store", return_value=store):
                _advance_active_setups(candle, publish=False)
            self.assertEqual(store.list_active(), [])
            journal = store.list_journal()[0]
            self.assertEqual(journal["final_status"], "EXPIRED")
            self.assertAlmostEqual(journal["gross_r"], 1.0)
            self.assertGreater(journal["commission_r"], 0)
            self.assertAlmostEqual(journal["net_r"], journal["gross_r"] - journal["commission_r"])

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
