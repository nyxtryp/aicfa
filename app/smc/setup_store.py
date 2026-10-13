"""SQLite persistence for deterministic scanner candidates and audit events."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Mapping


class SetupStore:
    def __init__(self, database_path: str | Path) -> None:
        self.path = str(database_path)
        with self._connection() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS setup_candidates (
                    setup_key TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    profile TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    status TEXT NOT NULL,
                    confirmation_time_ms INTEGER NOT NULL,
                    score INTEGER NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at_ms INTEGER NOT NULL DEFAULT (CAST(strftime('%s','now') AS INTEGER) * 1000),
                    updated_at_ms INTEGER NOT NULL DEFAULT (CAST(strftime('%s','now') AS INTEGER) * 1000)
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS setup_candidate_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    setup_key TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    event_time_ms INTEGER NOT NULL,
                    payload_json TEXT NOT NULL
                )
            """)
            db.execute("CREATE INDEX IF NOT EXISTS idx_setup_candidates_status_time ON setup_candidates(status, confirmation_time_ms DESC)")
            db.execute("CREATE INDEX IF NOT EXISTS idx_setup_candidate_events_key_time ON setup_candidate_events(setup_key, event_time_ms)")

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=10000")
        return db

    @contextmanager
    def _connection(self):
        db = self._connect()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def save_candidate(self, payload: Mapping[str, Any]) -> bool:
        """Insert once; return False on replay so candle redelivery cannot duplicate it."""
        key = str(payload["key"])
        encoded = json.dumps(dict(payload), separators=(",", ":"), sort_keys=True)
        with self._connect() as db:
            cursor = db.execute(
                """INSERT OR IGNORE INTO setup_candidates
                   (setup_key,symbol,profile,direction,status,confirmation_time_ms,score,payload_json)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (key, payload["symbol"], payload["profile"], payload["direction"],
                 payload["status"], int(payload["confirmation_time_ms"]),
                 int(payload["score"]), encoded),
            )
            if cursor.rowcount != 1:
                return False
            db.execute(
                "INSERT INTO setup_candidate_events(setup_key,event_type,event_time_ms,payload_json) VALUES (?,?,?,?)",
                (key, "CANDIDATE_DETECTED", int(payload["confirmation_time_ms"]), encoded),
            )
            return True

    def list_candidates(self, *, limit: int = 200) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT payload_json FROM setup_candidates ORDER BY confirmation_time_ms DESC LIMIT ?",
                (max(1, min(int(limit), 1000)),),
            ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def event_count(self, setup_key: str) -> int:
        with self._connect() as db:
            row = db.execute(
                "SELECT COUNT(*) AS n FROM setup_candidate_events WHERE setup_key=?",
                (setup_key,),
            ).fetchone()
        return int(row["n"])
