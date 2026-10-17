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

    def test_store_initialization_removes_old_rejections(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "setups.sqlite3"
            store = SetupStore(path)
            with store._connection() as db:
                db.execute(
                    "INSERT INTO setup_candidates (setup_key,symbol,profile,direction,status,confirmation_time_ms,score,zone_key,payload_json) VALUES (?,?,?,?,?,?,?,?,?)",
                    ("old-rejected", "BTCUSDT", "scalp", "long", "REJECTED", 2000, 3, "zone", "{}"),
                )
                db.execute(
                    "INSERT INTO setup_candidate_events (setup_key,event_type,event_time_ms,payload_json) VALUES (?,?,?,?)",
                    ("old-rejected", "SETUP_REJECTED", 2000, "{}"),
                )
            store = SetupStore(path)
            self.assertEqual(store.list_candidates(include_rejected=True), [])
            self.assertEqual(store.event_count("old-rejected"), 0)

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


    def test_rr_floor_rejects_new_candidate_below_149(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SetupStore(Path(directory) / "setups.sqlite3")
            payload = {
                "key": "ETHUSDT:scalp:long:OB:1:2", "symbol": "ETHUSDT",
                "profile": "scalp", "direction": "long", "status": "CANDIDATE",
                "confirmation_time_ms": 2000, "confirmation_price": 100.0,
                "stop_price": 95.0, "targets": [107.0], "score": 7,
                "zone": [98.0, 101.0], "timeframe": "5m",
            }
            saved, decision = store.save_decision(payload, cooldown_minutes=0)
            self.assertFalse(saved)
            self.assertEqual(decision["status"], "REJECTED")
            self.assertIn("rr_below_minimum", decision["decision_reasons"])
            self.assertEqual(store.list_candidates(), [])

    def test_legacy_active_below_rr_floor_is_quarantined(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "setups.sqlite3"
            store = SetupStore(path)
            payload = {
                "key": "SOLUSDT:scalp:short:legacy", "symbol": "SOLUSDT",
                "profile": "scalp", "direction": "short", "status": "CANDIDATE",
                "confirmation_time_ms": 2000, "confirmation_price": 100.0,
                "stop_price": 105.0, "targets": [94.0], "score": 7,
                "zone": [101.0, 103.0], "timeframe": "5m",
            }
            with store._connection() as db:
                db.execute(
                    "INSERT INTO setup_candidates (setup_key,symbol,profile,direction,status,confirmation_time_ms,score,zone_key,payload_json) VALUES (?,?,?,?,?,?,?,?,?)",
                    (payload["key"], payload["symbol"], payload["profile"], payload["direction"], "CANDIDATE", 2000, 7, "legacy", __import__("json").dumps(payload)),
                )
            store = SetupStore(path)
            self.assertEqual(store.list_candidates(), [])
            with store._connection() as db:
                row = db.execute("SELECT status,payload_json FROM setup_candidates WHERE setup_key=?", (payload["key"],)).fetchone()
            self.assertEqual(row["status"], "REJECTED")
            self.assertIn("rr_below_minimum_or_unverifiable_legacy", row["payload_json"])

    def test_candidate_closure_does_not_enter_strategy_journal(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SetupStore(Path(directory) / "setups.sqlite3")
            payload = {
                "key": "BTCUSDT:scalp:long:OB:3:4", "symbol": "BTCUSDT",
                "profile": "scalp", "direction": "long", "status": "CANDIDATE",
                "confirmation_time_ms": 2000, "confirmation_price": 100.0,
                "stop_price": 95.0, "targets": [110.0], "score": 7,
                "zone": [98.0, 101.0], "timeframe": "5m",
            }
            self.assertTrue(store.save_candidate(payload))
            self.assertEqual(store.list_monitored(), [])
            closed = dict(payload, status="CLOSED", final_status="TP1", closed_at_ms=3000)
            journal = {
                "key": payload["key"], "symbol": "BTCUSDT", "profile": "scalp",
                "direction": "long", "timeframe": "5m", "final_status": "TP1",
                "confirmation_price": 100.0, "stop_price": 95.0, "targets": [110.0],
                "zone": [98.0, 101.0], "opened_at_ms": 2000, "closed_at_ms": 3000,
                "gross_r": 2.0, "commission_r": 0.02, "net_r": 1.98,
            }
            self.assertTrue(store.transition(payload["key"], closed, event_type="TP1", event_time_ms=3000, final_journal=journal))
            self.assertEqual(store.list_candidates(), [])
            self.assertEqual(store.list_journal(), [])

    def test_accepted_setup_is_journaled_only_when_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SetupStore(Path(directory) / "setups.sqlite3")
            payload = {
                "key": "ETHUSDT:intraday:long:OB:3:4", "symbol": "ETHUSDT",
                "profile": "intraday", "direction": "long", "status": "ACCEPTED",
                "confirmation_time_ms": 2000, "confirmation_price": 100.0,
                "stop_price": 95.0, "targets": [110.0], "score": 8,
                "zone": [98.0, 101.0], "timeframe": "15m",
            }
            self.assertTrue(store.save_decision(payload, cooldown_minutes=0)[0])
            closed = dict(payload, status="CLOSED", final_status="TP1", closed_at_ms=3000)
            journal = {
                "key": payload["key"], "symbol": "ETHUSDT", "profile": "intraday",
                "direction": "long", "timeframe": "15m", "final_status": "TP1",
                "confirmation_price": 100.0, "stop_price": 95.0, "targets": [110.0],
                "zone": [98.0, 101.0], "opened_at_ms": 2000, "closed_at_ms": 3000,
                "gross_r": 2.0, "commission_r": 0.02, "net_r": 1.98,
            }
            self.assertTrue(store.transition(payload["key"], closed, event_type="TP1", event_time_ms=3000, final_journal=journal))
            self.assertEqual(store.list_journal()[0]["final_status"], "TP1")

if __name__ == "__main__":
    unittest.main()
