"""Consistent daily SQLite backups with integrity verification and retention."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_RETENTION_DAYS = 14


def create_verified_backup(
    database_path: str | Path,
    backup_directory: str | Path | None = None,
    *,
    retention_days: int = DEFAULT_RETENTION_DAYS,
    now: datetime | None = None,
) -> Path:
    """Create a consistent online SQLite backup, verify it, then publish atomically."""
    source = Path(database_path)
    if not source.is_file():
        raise FileNotFoundError(source)
    if retention_days < 1:
        raise ValueError("retention_days must be at least 1")

    directory = Path(backup_directory) if backup_directory else source.parent / "backups"
    directory.mkdir(parents=True, exist_ok=True)
    timestamp = now or datetime.now(timezone.utc)
    stamp = timestamp.astimezone(timezone.utc).strftime("%Y-%m-%d")
    destination = directory / f"candles-{stamp}.sqlite3"
    temporary = directory / f".candles-{stamp}.sqlite3.tmp"

    try:
        with sqlite3.connect(str(source), timeout=30) as source_db:
            with sqlite3.connect(str(temporary), timeout=30) as backup_db:
                source_db.backup(backup_db)
                integrity = backup_db.execute("PRAGMA integrity_check").fetchone()
                if not integrity or integrity[0] != "ok":
                    raise sqlite3.DatabaseError(f"backup integrity check failed: {integrity}")
                tables = backup_db.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='candles'"
                ).fetchone()
                if not tables:
                    raise sqlite3.DatabaseError("backup is missing candles table")
                backup_db.execute("SELECT COUNT(*) FROM candles").fetchone()
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink()

    cutoff = timestamp.timestamp() - retention_days * 86400
    for old_backup in directory.glob("candles-*.sqlite3"):
        if old_backup == destination:
            continue
        try:
            if old_backup.stat().st_mtime < cutoff:
                old_backup.unlink()
        except FileNotFoundError:
            pass
    return destination
