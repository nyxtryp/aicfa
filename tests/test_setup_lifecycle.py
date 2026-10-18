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
        saved, decided = self.store.save_decision(payload, cooldown_minutes=0)
        self.assertTrue(saved)
        self.assertEqual(decided["status"], "ACCEPTED")
        return payload

    def test_existing_candidate_is_not_backfilled_to_accepted(self):
        now_ms = int(time.time() * 1000)
        payload = {
            "key": "SOLUSDT:scalp:long:PAC:OB:100:200",
            "symbol": "SOLUSDT", "profile": "scalp", "direction": "long",
            "status": "CANDIDATE", "confirmation_time_ms": now_ms - 10_000,
            "confirmation_price": 100.0, "stop_price": 95.0, "targets": [110.0],
            "score": 7, "zone": [98.0, 101.0], "timeframe": "5m",
        }
        saved, _ = self.store.save_decision(payload, cooldown_minutes=0)
        self.assertTrue(saved)
        reopened = SetupStore(self.store.path)
        self.assertEqual(reopened.list_active(), [])
        self.assertEqual(reopened.list_monitored(), [])

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

    def test_pac_candidate_with_stop_below_minimum_is_not_accepted(self):
        now_ms = int(time.time() * 1000)
        candle = SimpleNamespace(
            symbol="BTCUSDT", timeframe="5m", close_time_ms=now_ms - 10_000,
            open_time_ms=now_ms - 310_000, open=100.0, high=101.0,
            low=99.0, close=100.0, volume=10.0,
        )
        payload = {
            "key": "BTCUSDT:scalp:long:PAC:OB:tight-stop",
            "symbol": "BTCUSDT", "profile": "scalp", "direction": "long",
            "status": "CANDIDATE", "confirmation_time_ms": candle.close_time_ms,
            "confirmation_price": 100.0, "stop_price": 99.9, "targets": [110.0],
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
        self.assertEqual(self.store.list_active(), [])

    def test_first_sync_migration_preserves_live_accepted_and_clears_old_results(self):
        legacy_path = Path(self.tmp.name) / "legacy.sqlite3"
        legacy = SetupStore(legacy_path)
        stale_payload = {
            "key": "SOLUSDT:intraday:short:PAC:old:setup",
            "symbol": "SOLUSDT", "profile": "intraday", "direction": "short",
            "status": "ACCEPTED", "confirmation_time_ms": int(time.time() * 1000) - 60_000,
            "confirmation_price": 100.0, "stop_price": 105.0, "targets": [90.0],
            "score": 8, "zone": [99.0, 101.0], "timeframe": "15m",
        }
        import json
        with legacy._connection() as db:
            db.execute("DROP TABLE setup_store_meta")
            db.execute(
                """INSERT INTO setup_candidates
                   (setup_key,symbol,profile,direction,status,confirmation_time_ms,score,zone_key,payload_json)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (stale_payload["key"], stale_payload["symbol"], stale_payload["profile"],
                 stale_payload["direction"], "ACCEPTED", stale_payload["confirmation_time_ms"],
                 8, "old-zone", json.dumps(stale_payload)),
            )
            db.execute(
                """INSERT INTO setup_candidate_events(setup_key,event_type,event_time_ms,payload_json)
                   VALUES (?,?,?,?)""",
                (stale_payload["key"], "SETUP_ACCEPTED", stale_payload["confirmation_time_ms"], json.dumps(stale_payload)),
            )
            db.execute(
                """INSERT INTO setup_journal
                   (setup_key,symbol,profile,direction,final_status,opened_at_ms,closed_at_ms,
                    gross_r,commission_r,net_r,payload_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (stale_payload["key"], "SOLUSDT", "intraday", "short", "TP1",
                 stale_payload["confirmation_time_ms"] - 10_000, stale_payload["confirmation_time_ms"],
                 2.0, 0.2, 1.8, json.dumps(stale_payload)),
            )
        clean = SetupStore(legacy_path)
        self.assertEqual([x["key"] for x in clean.list_active()], [stale_payload["key"]])
        self.assertEqual(clean.list_journal(), [])
        self.assertEqual([x["key"] for x in clean.list_candidates()], [stale_payload["key"]])
        fresh = {
            "key": "ETHUSDT:scalp:long:PAC:fresh:setup",
            "symbol": "ETHUSDT", "profile": "scalp", "direction": "long",
            "status": "ACCEPTED", "confirmation_time_ms": int(time.time() * 1000),
            "confirmation_price": 100.0, "stop_price": 95.0, "targets": [110.0],
            "score": 7, "zone": [98.0, 101.0], "timeframe": "5m",
        }
        saved, _ = clean.save_decision(fresh, cooldown_minutes=0)
        self.assertTrue(saved)
        reopened = SetupStore(legacy_path)
        self.assertEqual({x["key"] for x in reopened.list_active()}, {fresh["key"], stale_payload["key"]})
        self.assertEqual(reopened.list_journal(), [])

    def test_active_panel_and_accepted_api_are_the_same_set(self):
        now_ms = int(time.time() * 1000)
        for symbol, profile, direction in (
            ("SOLUSDT", "scalp", "long"),
            ("BTCUSDT", "scalp", "short"),
            ("ETHUSDT", "intraday", "long"),
        ):
            payload = {
                "key": f"{symbol}:{profile}:{direction}:PAC:fresh",
                "symbol": symbol, "profile": profile, "direction": direction,
                "status": "ACCEPTED", "confirmation_time_ms": now_ms,
                "confirmation_price": 100.0,
                "stop_price": 95.0 if direction == "long" else 105.0,
                "targets": [110.0 if direction == "long" else 90.0],
                "score": 7, "zone": [98.0, 101.0], "timeframe": "5m",
            }
            saved, _ = self.store.save_decision(payload, cooldown_minutes=0)
            self.assertTrue(saved)
        connected_status = {"groups": {"tradfi": {"status": "connected"}, "crypto": {"status": "connected"}}}
        with patch.object(main.market_data, "status", return_value=connected_status):
            panels = asyncio.run(main.setup_candidates())
            accepted = asyncio.run(main.active_setups())
        panel_keys = [x["key"] for x in panels["candidates"]]
        accepted_keys = [x["key"] for x in accepted["setups"]]
        self.assertEqual(panel_keys, accepted_keys)
        self.assertEqual(panels["candidates"], accepted["setups"])
        self.assertEqual(len(panel_keys), 3)
        self.assertEqual(sum(x["profile"] == "scalp" for x in panels["candidates"]), 2)
        self.assertEqual(sum(x["profile"] == "intraday" for x in panels["candidates"]), 1)

    def test_more_than_one_hundred_distinct_setups_are_not_capped(self):
        now_ms = int(time.time() * 1000)
        for index in range(105):
            symbol = f"TEST{index}USDT"
            payload = {
                "key": f"{symbol}:scalp:long:PAC:{index}",
                "symbol": symbol, "profile": "scalp", "direction": "long",
                "status": "ACCEPTED", "confirmation_time_ms": now_ms + index,
                "confirmation_price": 100.0, "stop_price": 95.0, "targets": [110.0],
                "score": 7, "zone": [98.0, 101.0], "timeframe": "5m",
            }
            saved, _ = self.store.save_decision(payload, cooldown_minutes=0)
            self.assertTrue(saved, symbol)
        self.assertEqual(self.store.active_count(), 105)
        self.assertEqual(len(self.store.list_active()), 105)

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
        # Closed setups must disappear from both profile panels and Accepted.
        self.assertEqual(self.store.active_count(), 0)
        self.assertEqual(self.store.list_active(), [])
        self.assertEqual(self.store.list_monitored(), [])
        self.assertEqual(self.store.list_candidates(), [])
        connected_status = {"groups": {"tradfi": {"status": "connected"}, "crypto": {"status": "connected"}}}
        with patch.object(main.market_data, "status", return_value=connected_status):
            panels = asyncio.run(main.setup_candidates())
            accepted = asyncio.run(main.active_setups())
        self.assertEqual(panels["candidates"], [])
        self.assertEqual(accepted["setups"], [])

    def test_stop_wins_when_stop_and_target_hit_in_same_candle(self):
        self.accepted_setup()
        main._advance_active_setups(self.candle(
            close_time_ms=2_000, low=94.0, high=111.0, close=105.0
        ), publish=False)
        journal = self.store.list_journal()
        self.assertEqual(len(journal), 1)
        self.assertEqual(journal[0]["final_status"], "SL")
        self.assertEqual(self.store.active_count(), 0)
        self.assertEqual(self.store.list_active(), [])
        self.assertEqual(self.store.list_monitored(), [])
        self.assertEqual(self.store.list_candidates(), [])

    def test_accepted_setup_expires_after_profile_lifetime(self):
        self.accepted_setup()
        main._advance_active_setups(self.candle(
            close_time_ms=1_000 + 3 * 3_600_000, low=99.0, high=101.0, close=102.0
        ), publish=False)
        journal = self.store.list_journal()
        self.assertEqual(len(journal), 1)
        self.assertEqual(journal[0]["final_status"], "EXPIRED")
        self.assertAlmostEqual(journal[0]["gross_r"], 0.4)
        self.assertEqual(self.store.active_count(), 0)
        self.assertEqual(self.store.list_active(), [])
        self.assertEqual(self.store.list_monitored(), [])
        self.assertEqual(self.store.list_candidates(), [])


    def test_accepted_setup_survives_close_outside_zone_until_sl_tp_or_expiry(self):
        self.accepted_setup()
        main._advance_active_setups(self.candle(
            close_time_ms=2_000, low=96.0, high=99.0, close=97.0
        ), publish=False)
        active = self.store.list_active()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["status"], "ACCEPTED")
        self.assertEqual(self.store.list_journal(), [])

    def test_opposite_choch_does_not_invalidate_accepted_setup(self):
        self.accepted_setup()
        candle = SimpleNamespace(
            symbol="BTCUSDT", timeframe="5m", close_time_ms=2_000,
        )
        main.market_data = SimpleNamespace(candles={
            ("BTCUSDT", "5m"): [SimpleNamespace(
                open=100.0, high=102.0, low=98.0, close=99.0,
                volume=10.0, open_time_ms=1_000, close_time_ms=2_000,
            )] * 40
        })
        with patch.object(main, "analyze_smc", return_value=SimpleNamespace(
            structure_breaks=[SimpleNamespace(kind="CHoCH", direction="bearish")]
        )):
            asyncio.run(main._invalidate_on_opposite_choch(candle))
        active = self.store.list_active()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["status"], "ACCEPTED")
        self.assertEqual(self.store.list_journal(), [])

    def test_invalidated_accepted_setup_is_not_a_strategy_result(self):
        payload = self.accepted_setup("BTCUSDT:scalp:long:OB:invalidated")
        invalidated = dict(payload)
        invalidated.update({
            "status": "INVALIDATED", "final_status": "INVALIDATED",
            "closed_at_ms": 2_000, "gross_r": 0.0,
            "commission_r": 0.0, "net_r": 0.0,
        })
        journal = {
            "key": payload["key"], "symbol": payload["symbol"],
            "profile": payload["profile"], "direction": payload["direction"],
            "timeframe": payload["timeframe"], "final_status": "INVALIDATED",
            "opened_at_ms": payload["confirmation_time_ms"], "closed_at_ms": 2_000,
            "gross_r": 0.0, "commission_r": 0.0, "net_r": 0.0,
        }
        self.assertTrue(self.store.transition(
            payload["key"], invalidated, event_type="INVALIDATED",
            event_time_ms=2_000, final_journal=journal,
        ))
        self.assertEqual(self.store.list_journal(), [])
        self.assertEqual(self.store.active_count(), 0)


if __name__ == "__main__":
    unittest.main()
