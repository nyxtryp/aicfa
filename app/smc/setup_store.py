"""SQLite persistence for deterministic scanner candidates and audit events."""
from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Mapping


MINIMUM_RR = 1.49


def _actual_rr(payload: Mapping[str, Any]) -> float:
    """Recalculate RR from entry, stop and TP1; never trust a stale stored RR field."""
    try:
        entry = float(payload["confirmation_price"])
        stop = float(payload["stop_price"])
        targets = payload.get("targets") or []
        target = float(targets[0])
        risk = abs(entry - stop)
        if risk <= 0:
            return 0.0
        direction = str(payload.get("direction", "")).lower()
        if (direction == "long" and not (stop < entry < target)) or (
            direction == "short" and not (target < entry < stop)
        ):
            return 0.0
        return abs(target - entry) / risk
    except (KeyError, TypeError, ValueError, IndexError, OverflowError):
        return 0.0


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
            db.execute("""
                CREATE TABLE IF NOT EXISTS setup_store_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            # Rebuild the accepted/results boundary without deleting live setups.
            # Accepted/active setups remain paper-tracked; only completed accepted
            # setups belong in the strategy journal. Legacy CANDIDATE rows are not
            # promoted and are removed from the live source.
            if db.execute(
                "SELECT 1 FROM setup_store_meta WHERE key='accepted_source_sync_v1'"
            ).fetchone() is None:
                db.execute("DELETE FROM setup_journal")
                db.execute(
                    "DELETE FROM setup_candidate_events WHERE setup_key IN "
                    "(SELECT setup_key FROM setup_candidates WHERE status NOT IN ('ACCEPTED','ACTIVE','TP1','TP2'))"
                )
                db.execute(
                    "DELETE FROM setup_candidates WHERE status NOT IN ('ACCEPTED','ACTIVE','TP1','TP2')"
                )
                db.execute(
                    "INSERT INTO setup_store_meta(key, value) VALUES ('accepted_source_sync_v1', 'done')"
                )
            # Versioned cleanup also runs on databases where v1 was already marked
            # complete: reset stale strategy history, but retain all live accepted rows.
            if db.execute(
                "SELECT 1 FROM setup_store_meta WHERE key='accepted_source_sync_v2'"
            ).fetchone() is None:
                db.execute("DELETE FROM setup_journal")
                db.execute(
                    "DELETE FROM setup_candidate_events WHERE setup_key IN "
                    "(SELECT setup_key FROM setup_candidates WHERE status NOT IN ('ACCEPTED','ACTIVE','TP1','TP2'))"
                )
                db.execute(
                    "DELETE FROM setup_candidates WHERE status NOT IN ('ACCEPTED','ACTIVE','TP1','TP2')"
                )
                now_ms = int(time.time() * 1000)
                retained = db.execute(
                    "SELECT setup_key,payload_json,confirmation_time_ms FROM setup_candidates "
                    "WHERE status IN ('ACCEPTED','ACTIVE','TP1','TP2')"
                ).fetchall()
                for row in retained:
                    payload = json.loads(row["payload_json"])
                    if _actual_rr(payload) < MINIMUM_RR:
                        continue
                    exists = db.execute(
                        "SELECT 1 FROM setup_candidate_events WHERE setup_key=? AND event_type='SETUP_ACCEPTED' LIMIT 1",
                        (row["setup_key"],),
                    ).fetchone()
                    if exists is None:
                        db.execute(
                            "INSERT INTO setup_candidate_events(setup_key,event_type,event_time_ms,payload_json) VALUES (?,?,?,?)",
                            (row["setup_key"], "SETUP_ACCEPTED", int(row["confirmation_time_ms"] or now_ms),
                             json.dumps(payload, separators=(",", ":"), sort_keys=True)),
                        )
                db.execute(
                    "INSERT INTO setup_store_meta(key, value) VALUES ('accepted_source_sync_v2', 'done')"
                )
            # One-time cleanup for rejected attempts accumulated by older releases.
            rejected_keys = [
                row["setup_key"]
                for row in db.execute("SELECT setup_key FROM setup_candidates WHERE status='REJECTED'").fetchall()
            ]
            if rejected_keys:
                db.executemany("DELETE FROM setup_candidate_events WHERE setup_key=?", [(key,) for key in rejected_keys])
                db.executemany("DELETE FROM setup_candidates WHERE setup_key=?", [(key,) for key in rejected_keys])
            # Quarantine legacy active records that do not meet today's RR floor.
            # Preserve their audit trail, but never let them reappear in active panels.
            active_rows = db.execute(
                "SELECT setup_key,payload_json FROM setup_candidates WHERE status IN ('CANDIDATE','ACCEPTED','ACTIVE','TP1','TP2')"
            ).fetchall()
            now_ms = int(time.time() * 1000)
            for row in active_rows:
                payload = json.loads(row["payload_json"])
                if _actual_rr(payload) >= 1.49:
                    continue
                payload["status"] = "REJECTED"
                payload["final_status"] = "REJECTED"
                payload["closed_at_ms"] = now_ms
                payload["decision_reasons"] = list(dict.fromkeys(
                    list(payload.get("decision_reasons", [])) + ["rr_below_minimum_or_unverifiable_legacy"]
                ))
                encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True)
                db.execute(
                    "UPDATE setup_candidates SET status='REJECTED',payload_json=?,updated_at_ms=? WHERE setup_key=?",
                    (encoded, now_ms, row["setup_key"]),
                )
                db.execute(
                    "INSERT INTO setup_candidate_events(setup_key,event_type,event_time_ms,payload_json) VALUES (?,?,?,?)",
                    (row["setup_key"], "LEGACY_RR_QUARANTINED", now_ms, encoded),
                )
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
        if str(payload.get("status", "")).upper() in {"CANDIDATE", "ACCEPTED", "ACTIVE", "TP1", "TP2"} and _actual_rr(payload) < MINIMUM_RR:
            return False
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
                "SELECT COUNT(*) FROM setup_candidates WHERE lower(profile) IN ('scalp','intraday') AND status IN ('ACCEPTED','ACTIVE','TP1','TP2')"
            ).fetchone()[0])

    def save_decision(self, payload: Mapping[str, Any], *, cooldown_minutes: int) -> tuple[bool, dict[str, Any]]:
        """Persist one eligible setup; panel and tracking views read the same accepted rows."""
        key = str(payload["key"])
        decided = dict(payload)
        zone_key = str(payload.get("zone_key") or "|".join(map(str, payload.get("zone", []))))
        encoded = json.dumps(decided, separators=(",", ":"), sort_keys=True)
        timestamp = int(payload["confirmation_time_ms"])
        # Rejected attempts are diagnostic counters, not durable setup records.
        # Do not write them to setup_candidates or setup_candidate_events.
        if str(decided.get("status", "REJECTED")).upper() == "REJECTED":
            return False, decided
        if str(decided.get("status", "")).upper() in {"CANDIDATE", "ACCEPTED", "ACTIVE", "TP1", "TP2"} and _actual_rr(decided) < MINIMUM_RR:
            decided["status"] = "REJECTED"
            decided["decision_reasons"] = list(dict.fromkeys(
                list(decided.get("decision_reasons", [])) + ["rr_below_minimum"]
            ))
            return False, decided
        with self._connection() as db:
            if db.execute("SELECT 1 FROM setup_candidates WHERE setup_key=?", (key,)).fetchone():
                return False, decided
            decision_reasons = list(decided.get("decision_reasons", []))
            gate_reasons: list[str] = []
            status = str(decided.get("status", "REJECTED"))
            if status == "ACCEPTED":
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
            # Cooldown and other store-level gates can reject a candidate here;
            # those decisions must also remain transient.
            if str(decided.get("status", "")).upper() == "REJECTED":
                return False, decided
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

    def list_candidates(self, *, limit: int | None = None, include_rejected: bool = False) -> list[dict[str, Any]]:
        """List persisted scanner candidates; no implicit row cap when limit is omitted."""
        limit_sql = ""
        params: tuple[Any, ...] = ()
        if limit is not None:
            limit_sql = " LIMIT ?"
            params = (max(1, int(limit)),)
        with self._connection() as db:
            if include_rejected:
                query = (
                    """SELECT payload_json FROM setup_candidates
                       WHERE payload_json NOT LIKE '%tradfi_market_closed%'
                         AND payload_json NOT LIKE '%market_hours_unverified%'
                       ORDER BY confirmation_time_ms DESC"""
                    + limit_sql
                )
            else:
                query = (
                    """SELECT payload_json FROM setup_candidates
                       WHERE status IN ('CANDIDATE','ACCEPTED','ACTIVE','TP1','TP2')
                       ORDER BY confirmation_time_ms DESC"""
                    + limit_sql
                )
            rows = db.execute(query, params).fetchall()
        return [
            payload for row in rows
            if _actual_rr(payload := json.loads(row["payload_json"])) >= MINIMUM_RR
        ]

    def list_active(self, *, limit: int | None = None) -> list[dict[str, Any]]:
        """The canonical live panel set: every accepted, still-tracked SCALP/INTRADAY setup."""
        limit_sql = ""
        params: tuple[Any, ...] = ()
        if limit is not None:
            limit_sql = " LIMIT ?"
            params = (max(1, int(limit)),)
        with self._connection() as db:
            query = (
                """SELECT payload_json FROM setup_candidates
                   WHERE lower(profile) IN ('scalp','intraday')
                     AND status IN ('ACCEPTED','ACTIVE','TP1','TP2')
                   ORDER BY confirmation_time_ms DESC"""
                + limit_sql
            )
            rows = db.execute(query, params).fetchall()
        return [
            payload for row in rows
            if _actual_rr(payload := json.loads(row["payload_json"])) >= MINIMUM_RR
        ]

    def list_monitored(self, *, limit: int | None = None) -> list[dict[str, Any]]:
        """Accepted setups only; unaccepted historical candidates are never paper-tracked."""
        limit_sql = ""
        params: tuple[Any, ...] = ()
        if limit is not None:
            limit_sql = " LIMIT ?"
            params = (max(1, int(limit)),)
        with self._connection() as db:
            query = (
                """SELECT payload_json FROM setup_candidates
                   WHERE lower(profile) IN ('scalp','intraday')
                     AND status IN ('ACCEPTED','ACTIVE','TP1','TP2')
                   ORDER BY confirmation_time_ms DESC"""
                + limit_sql
            )
            rows = db.execute(query, params).fetchall()
        return [
            payload for row in rows
            if _actual_rr(payload := json.loads(row["payload_json"])) >= MINIMUM_RR
        ]

    def transition(self, setup_key: str, payload: Mapping[str, Any], *, event_type: str,
                   event_time_ms: int, final_journal: Mapping[str, Any] | None = None) -> bool:
        encoded = json.dumps(dict(payload), separators=(",", ":"), sort_keys=True)
        with self._connection() as db:
            row = db.execute("SELECT status,payload_json FROM setup_candidates WHERE setup_key=?", (setup_key,)).fetchone()
            if row is None or row["status"] not in ("CANDIDATE", "ACCEPTED", "ACTIVE", "TP1", "TP2"):
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
            # Only setups that entered the Accepted panel can become strategy results.
            # A legacy CANDIDATE that closes during shadow tracking is not a journal trade.
            was_accepted = row["status"] in ("ACCEPTED", "ACTIVE", "TP1", "TP2")
            if (final_journal is not None and was_accepted
                    and str(final_journal.get("final_status", "")).upper() in {"TP1", "SL", "EXPIRED"}):
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

    def list_journal(self, *, limit: int | None = None) -> list[dict[str, Any]]:
        """Return only finalized trades from the fresh accepted-tracking generation."""
        limit_sql = ""
        params: tuple[Any, ...] = ()
        if limit is not None:
            limit_sql = " LIMIT ?"
            params = (max(1, int(limit)),)
        with self._connection() as db:
            query = (
                """SELECT j.payload_json FROM setup_journal AS j
                   JOIN setup_candidates AS c ON c.setup_key=j.setup_key
                   WHERE lower(c.profile) IN ('scalp','intraday')
                     AND lower(j.profile) IN ('scalp','intraday')
                     AND upper(j.final_status) IN ('TP1','SL','EXPIRED')
                     AND EXISTS (
                         SELECT 1 FROM setup_candidate_events AS e
                         WHERE e.setup_key=j.setup_key AND e.event_type='SETUP_ACCEPTED'
                     )
                   ORDER BY j.closed_at_ms DESC"""
                + limit_sql
            )
            rows = db.execute(query, params).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]

    def event_count(self, setup_key: str) -> int:
        with self._connection() as db:
            row = db.execute(
                "SELECT COUNT(*) AS n FROM setup_candidate_events WHERE setup_key=?",
                (setup_key,),
            ).fetchone()
        return int(row["n"])
