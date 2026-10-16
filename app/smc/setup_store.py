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
                    zone_key TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL,
                    created_at_ms INTEGER NOT NULL DEFAULT (CAST(strftime('%s','now') AS INTEGER) * 1000),
                    updated_at_ms INTEGER NOT NULL DEFAULT (CAST(strftime('%s','now') AS INTEGER) * 1000)
                )
            """)
            db.execute("""
                CREATE TABLE IF NOT EXISTS setup_journal (
                    setup_key TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    profile TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    final_status TEXT NOT NULL,
                    opened_at_ms INTEGER NOT NULL,
                    closed_at_ms INTEGER NOT NULL,
                    gross_r REAL NOT NULL,
                    commission_r REAL NOT NULL,
                    net_r REAL NOT NULL,
                    payload_json TEXT NOT NULL
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
            columns = {row["name"] for row in db.execute("PRAGMA table_info(setup_candidates)").fetchall()}
            if "zone_key" not in columns:
                db.execute("ALTER TABLE setup_candidates ADD COLUMN zone_key TEXT NOT NULL DEFAULT ''")
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
        with self._connection() as db:
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


    def active_count(self) -> int:
        with self._connection() as db:
            return int(db.execute(
                "SELECT COUNT(*) FROM setup_candidates WHERE status IN ('ACCEPTED','ACTIVE','TP1','TP2')"
            ).fetchone()[0])

    def save_decision(self, payload: Mapping[str, Any], *, cooldown_minutes: int, max_active: int = 8) -> tuple[bool, dict[str, Any]]:
        """Persist one decision atomically with global cap, symbol/profile and zone cooldown gates."""
        key = str(payload["key"])
        decided = dict(payload)
        zone_key = str(payload.get("zone_key") or "|".join(map(str, payload.get("zone", []))))
        encoded = json.dumps(decided, separators=(",", ":"), sort_keys=True)
        timestamp = int(payload["confirmation_time_ms"])
        with self._connection() as db:
            if db.execute("SELECT 1 FROM setup_candidates WHERE setup_key=?", (key,)).fetchone():
                return False, decided
            decision_reasons = list(decided.get("decision_reasons", []))
            gate_reasons: list[str] = []
            status = str(decided.get("status", "REJECTED"))
            if status == "ACCEPTED":
                active = int(db.execute(
                    "SELECT COUNT(*) FROM setup_candidates WHERE status IN ('ACCEPTED','ACTIVE','TP1','TP2')"
                ).fetchone()[0])
                if active >= max_active:
                    gate_reasons.append("active_setup_limit_reached")
                if db.execute(
                    "SELECT 1 FROM setup_candidates WHERE symbol=? AND profile=? AND status IN ('ACCEPTED','ACTIVE','TP1','TP2') LIMIT 1",
                    (decided["symbol"], decided["profile"]),
                ).fetchone():
                    gate_reasons.append("active_setup_for_symbol_profile")
            if status in ("ACCEPTED", "CANDIDATE"):
                cooldown_ms = max(0, int(cooldown_minutes)) * 60_000
                if cooldown_ms and db.execute(
                    "SELECT 1 FROM setup_candidates WHERE symbol=? AND profile=? AND zone_key=? AND status NOT IN ('REJECTED','MISSED_PRICE') AND confirmation_time_ms>=? LIMIT 1",
                    (decided["symbol"], decided["profile"], zone_key, timestamp - cooldown_ms),
                ).fetchone():
                    gate_reasons.append("cooldown_active")
            if gate_reasons:
                decided["status"] = "REJECTED"
                decided["decision_reasons"] = list(dict.fromkeys(decision_reasons + gate_reasons))
            elif decision_reasons:
                decided["decision_reasons"] = list(dict.fromkeys(decision_reasons))
            encoded = json.dumps(decided, separators=(",", ":"), sort_keys=True)
            cursor = db.execute(
                """INSERT OR IGNORE INTO setup_candidates
                   (setup_key,symbol,profile,direction,status,confirmation_time_ms,score,zone_key,payload_json)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (key, decided["symbol"], decided["profile"], decided["direction"],
                 decided["status"], timestamp, int(decided.get("score", 0)), zone_key, encoded),
            )
            if cursor.rowcount != 1:
                return False, decided
            db.execute(
                "INSERT INTO setup_candidate_events(setup_key,event_type,event_time_ms,payload_json) VALUES (?,?,?,?)",
                (key, "SETUP_" + str(decided["status"]), timestamp, encoded),
            )
            return True, decided

    def list_candidates(self, *, limit: int = 200, include_rejected: bool = False) -> list[dict[str, Any]]:
        with self._connection() as db:
            if include_rejected:
                rows = db.execute(
                    """SELECT payload_json FROM setup_candidates
                       WHERE payload_json NOT LIKE '%tradfi_market_closed%'
                         AND payload_json NOT LIKE '%market_hours_unverified%'
                       ORDER BY confirmation_time_ms DESC LIMIT ?""",
                    (max(1, min(int(limit), 1000)),),
                ).fetchall()
            else:
                rows = db.execute(
                    "SELECT payload_json FROM setup_candidates WHERE status IN ('CANDIDATE','ACCEPTED','ACTIVE','TP1','TP2') ORDER BY confirmation_time_ms DESC LIMIT ?",
                    (max(1, min(int(limit), 1000)),),
                ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]


    def list_active(self, *, limit: int = 200) -> list[dict[str, Any]]:
        with self._connection() as db:
            rows = db.execute(
                "SELECT payload_json FROM setup_candidates WHERE status IN ('ACCEPTED','TP1','TP2') ORDER BY confirmation_time_ms DESC LIMIT ?",
                (max(1, min(int(limit), 1000)),),
            ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def transition(self, setup_key: str, payload: Mapping[str, Any], *, event_type: str,
                   event_time_ms: int, final_journal: Mapping[str, Any] | None = None) -> bool:
        encoded = json.dumps(dict(payload), separators=(",", ":"), sort_keys=True)
        with self._connection() as db:
            row = db.execute("SELECT status,payload_json FROM setup_candidates WHERE setup_key=?", (setup_key,)).fetchone()
            if row is None or row["status"] not in ("ACCEPTED", "TP1", "TP2"):
                return False
            existing_payload = json.loads(row["payload_json"])
            previous_event_ms = int(existing_payload.get("last_event_time_ms", existing_payload.get("confirmation_time_ms", 0)))
            if row["status"] == str(payload["status"]) and int(event_time_ms) <= previous_event_ms:
                return False
            db.execute(
                "UPDATE setup_candidates SET status=?, payload_json=?, updated_at_ms=? WHERE setup_key=?",
                (str(payload["status"]), encoded, int(event_time_ms), setup_key),
            )
            db.execute(
                "INSERT INTO setup_candidate_events(setup_key,event_type,event_time_ms,payload_json) VALUES (?,?,?,?)",
                (setup_key, event_type, int(event_time_ms), encoded),
            )
            if final_journal is not None:
                journal = dict(final_journal)
                db.execute(
                    """INSERT OR REPLACE INTO setup_journal
                       (setup_key,symbol,profile,direction,final_status,opened_at_ms,closed_at_ms,gross_r,commission_r,net_r,payload_json)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                    (setup_key, journal["symbol"], journal["profile"], journal["direction"],
                     journal["final_status"], int(journal["opened_at_ms"]), int(journal["closed_at_ms"]),
                     float(journal["gross_r"]), float(journal["commission_r"]), float(journal["net_r"]),
                     json.dumps(journal, separators=(",", ":"), sort_keys=True)),
                )
            return True

    def list_journal(self, *, limit: int = 200) -> list[dict[str, Any]]:
        with self._connection() as db:
            rows = db.execute(
                "SELECT payload_json FROM setup_journal ORDER BY closed_at_ms DESC LIMIT ?",
                (max(1, min(int(limit), 1000)),),
            ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def event_count(self, setup_key: str) -> int:
        with self._connection() as db:
            row = db.execute(
                "SELECT COUNT(*) AS n FROM setup_candidate_events WHERE setup_key=?",
                (setup_key,),
            ).fetchone()
        return int(row["n"])
