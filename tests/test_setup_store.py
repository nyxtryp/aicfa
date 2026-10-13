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


if __name__ == "__main__":
    unittest.main()
