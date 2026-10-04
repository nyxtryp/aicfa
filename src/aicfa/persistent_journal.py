"""Persistent append-only journal for autonomous AICFA scan events.

The journal is intentionally JSONL: each line is one complete immutable event,
so the website feed can read recent events without coupling itself to the
analytical engine or a database.
"""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from enum import Enum
import json
import os
from pathlib import Path
from typing import Any


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {key: _jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


class PersistentJournal:
    """Append-only JSONL journal with a small read API for the future feed."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_env(cls) -> "PersistentJournal | None":
        explicit = os.getenv("AICFA_JOURNAL_PATH")
        data_dir = os.getenv("AICFA_DATA_DIR")
        if explicit:
            return cls(explicit)
        if data_dir:
            return cls(Path(data_dir) / "journal" / "events.jsonl")
        return None

    def append(self, event_type: str, timestamp_ms: int, payload: Any) -> None:
        record = {
            "event_type": str(event_type),
            "timestamp_ms": int(timestamp_ms),
            "payload": _jsonable(payload),
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")

    def read(self, limit: int = 100) -> tuple[dict[str, Any], ...]:
        if limit <= 0 or not self.path.exists():
            return ()
        lines = self.path.read_text(encoding="utf-8").splitlines()
        records: list[dict[str, Any]] = []
        for line in lines[-limit:]:
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                records.append(value)
        return tuple(records)

    def record_scan(self, state: Any) -> None:
        markets = []
        for market in state.result.markets:
            diagnostics = market.diagnostics
            markets.append({
                "asset": market.asset,
                "diagnostics": diagnostics,
                "setups": market.setups,
                "lifecycle_results": market.lifecycle_results,
            })
        self.append(
            "scan",
            state.scanned_at_ms,
            {
                "scan_number": state.scan_number,
                "markets": markets,
            },
        )

    def record_cycle(self, cycle: Any) -> None:
        self.append(
            "rotation_cycle",
            cycle.finished_at_ms,
            cycle,
        )


__all__ = ["PersistentJournal"]
