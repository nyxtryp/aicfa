import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from app.backup import create_verified_backup
from app.market_data import ClosedCandle, SQLiteCandleStore


class SQLiteBackupTests(unittest.TestCase):
    def test_backup_is_consistent_and_restores_candles(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = SQLiteCandleStore(root / "candles.db")
            store.initialize()
            candle = ClosedCandle(
                symbol="BTCUSDT",
                timeframe="1m",
                open_time_ms=1_791_000_000_000,
                close_time_ms=1_791_000_059_999,
                open=Decimal("100"),
                high=Decimal("105"),
                low=Decimal("99"),
                close=Decimal("103"),
                volume=Decimal("12.5"),
            )
            store.upsert_many([candle])
            backup = create_verified_backup(
                store.path,
                root / "backups",
                now=datetime(2026, 10, 13, tzinfo=timezone.utc),
            )
            self.assertTrue(backup.is_file())
            store.close()

            with sqlite3.connect(str(backup)) as restored:
                self.assertEqual(restored.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                self.assertEqual(restored.execute("SELECT COUNT(*) FROM candles").fetchone()[0], 1)
                row = restored.execute(
                    "SELECT symbol, timeframe, open_time_ms, close FROM candles"
                ).fetchone()
            self.assertEqual(row, ("BTCUSDT", "1m", 1_791_000_000_000, "103"))

    def test_backup_refuses_missing_database(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(FileNotFoundError):
                create_verified_backup(Path(temporary) / "missing.sqlite3")

    def test_backup_retention_removes_only_old_backups(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = SQLiteCandleStore(root / "candles.db")
            source.initialize()
            source.close()
            backup_dir = root / "backups"
            backup_dir.mkdir()
            old = backup_dir / "candles-old.sqlite3"
            old.write_bytes(b"old")
            old.touch()
            import os
            old_timestamp = datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp()
            os.utime(old, (old_timestamp, old_timestamp))
            recent = backup_dir / "candles-recent.sqlite3"
            recent.write_bytes(b"keep")
            now = datetime(2026, 10, 13, tzinfo=timezone.utc)

            create_verified_backup(source.path, backup_dir, retention_days=14, now=now)

            self.assertFalse(old.exists())
            self.assertTrue(recent.exists())
            self.assertTrue((backup_dir / "candles-2026-10-13.sqlite3").exists())


if __name__ == "__main__":
    unittest.main()
