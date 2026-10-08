"""Persistent registry for AICFA setup lifecycles shown by the terminal.

The scan journal remains append-only history. This registry is the durable
current-state projection used by the setup queue, so deploys/restarts do not
erase active setups.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .data_requirements import TradingMode, mode_timeframe_profile, normalize_trading_mode
from .persistent_journal import _jsonable, _visual_geometry


TIMEFRAME_MS = {
    "1m": 60_000,
    "5m": 5 * 60_000,
    "15m": 15 * 60_000,
    "1h": 60 * 60_000,
    "4h": 4 * 60 * 60_000,
    "1d": 24 * 60 * 60_000,
    "1w": 7 * 24 * 60 * 60_000,
}

STALE_STRUCTURE_CANDLES = 3
EXPIRE_STRUCTURE_CANDLES = 12
REGISTRY_REVISION = 2


class SetupRegistry:
    """Durable current-state registry keyed by setup identity.

    Identity intentionally excludes prices/timestamps/minor geometry changes:
    asset + market type + mode + scenario + direction + structural timeframe.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_env(cls) -> "SetupRegistry | None":
        explicit = os.getenv("AICFA_SETUP_REGISTRY_PATH")
        data_dir = os.getenv("AICFA_DATA_DIR")
        if explicit:
            return cls(explicit)
        if data_dir:
            return cls(Path(data_dir) / "journal" / "setup_registry.json")
        return None

    @staticmethod
    def identity_key(*, asset: str, market_type: str, mode: TradingMode | str, candidate: Any) -> str:
        normalized = normalize_trading_mode(mode)
        profile = mode_timeframe_profile(normalized)
        scenario = str(getattr(candidate, "scenario", "")).strip().lower()
        direction = str(getattr(candidate, "direction", "")).strip().lower()
        return "|".join((
            str(asset),
            str(market_type),
            normalized.value,
            scenario,
            direction,
            profile.structure_timeframe,
        ))

    @staticmethod
    def _key_from_identity(identity: Any) -> str | None:
        if identity is None:
            return None
        return "|".join((
            str(identity.symbol),
            str(identity.market_type),
            normalize_trading_mode(identity.horizon).value,
            str(getattr(identity, "scenario", "")).strip().lower(),
            str(identity.direction).strip().lower(),
            mode_timeframe_profile(normalize_trading_mode(identity.horizon)).structure_timeframe,
        ))

    @staticmethod
    def _mode_ttl_ms(mode: TradingMode | str) -> tuple[int, int]:
        normalized = normalize_trading_mode(mode)
        tf = mode_timeframe_profile(normalized).structure_timeframe
        candle_ms = TIMEFRAME_MS[tf]
        return (
            STALE_STRUCTURE_CANDLES * candle_ms,
            EXPIRE_STRUCTURE_CANDLES * candle_ms,
        )

    def read(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        records = payload.get("setups", {}) if isinstance(payload, dict) else {}
        return records if isinstance(records, dict) else {}

    def _write(self, records: dict[str, dict[str, Any]]) -> None:
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        temp.write_text(
            json.dumps({"version": 1, "setups": records}, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        temp.replace(self.path)

    def record_scan(self, state: Any) -> None:
        records = {\n            key: value\n            for key, value in self.read().items()\n            if int(value.get("strategy_revision", 0)) == REGISTRY_REVISION\n        }\n        now_ms = int(state.scanned_at_ms)\n
        for market in state.result.markets:
            asset = market.asset
            market_type = "spot"
            market_keys: set[str] = set()
            active_lifecycle_keys: set[str] = set()
            for setup in getattr(market, "setups", ()):
                identity = getattr(setup, "identity", None)
                if identity is not None:
                    market_type = str(identity.market_type)
                candidate = getattr(setup, "candidate", None)
                if candidate is None:
                    continue
                key = self.identity_key(
                    asset=asset,
                    market_type=market_type,
                    mode=setup.mode,
                    candidate=candidate,
                )
                previous = records.get(key, {})\n                created_at = int(previous.get("created_at_ms", now_ms))\n                status = "ACTIVE"
                lifecycle = getattr(setup, "lifecycle_result", None)
                lifecycle_status = getattr(getattr(lifecycle, "status", None), "value", None)
                if lifecycle_status in {"invalidated", "completed", "expired"}:
                    status = lifecycle_status.upper()
                payload = _jsonable(setup)
                result = next((item for item in getattr(market, "results", ()) if getattr(item, "mode", None) == getattr(setup, "mode", None)), None)
                if result is not None:
                    payload["chart"] = _visual_geometry(result, candidate)
                market_keys.add(key)
                stale_after, expire_after = self._mode_ttl_ms(setup.mode)
                records[key] = {
                    **previous,
                    "strategy_revision": REGISTRY_REVISION,\n                    "setup_id": key,
                    "asset": asset,
                    "market_type": market_type,
                    "mode": normalize_trading_mode(setup.mode).value,
                    "scenario": str(getattr(candidate, "scenario", "")),
                    "direction": str(getattr(candidate, "direction", "")).upper(),
                    "structural_timeframe": mode_timeframe_profile(normalize_trading_mode(setup.mode)).structure_timeframe,
                    "status": status,
                    "lifecycle_status": lifecycle_status or "active",
                    "created_at_ms": created_at,
                    "last_seen_at_ms": now_ms,
                    "last_confirmed_at_ms": now_ms,
                    "last_checked_at_ms": now_ms,
                    "last_scan_number": int(state.scan_number),
                    "stale_after_ms": stale_after,
                    "expire_after_ms": expire_after,
                    "setup": payload,
                }

            for lifecycle in getattr(market, "lifecycle_results", ()):
                identity = getattr(lifecycle, "identity", None)
                key = self._key_from_identity(identity)
                if key:
                    active_lifecycle_keys.add(key)
                if not key or key not in records:
                    continue
                status = getattr(getattr(lifecycle, "status", None), "value", None)
                record = records[key]
                record["last_checked_at_ms"] = now_ms
                if status in {"invalidated", "completed", "expired"}:
                    record["status"] = status.upper()
                    record["lifecycle_status"] = status
                elif status in {"active", "tp1_hit"} and record.get("status") not in {"INVALIDATED", "COMPLETED", "EXPIRED"}:
                    # Keep TP1_HIT distinct from ACTIVE: the original entry is
                    # no longer actionable once price has reached TP1, even
                    # though the setup may remain alive toward later targets.
                    record["status"] = "TP1_HIT" if status == "tp1_hit" else "ACTIVE"
                    record["lifecycle_status"] = status
                    record["last_lifecycle_at_ms"] = now_ms

            for key, record in records.items():
                if str(record.get("asset", "")) != str(asset):
                    continue
                if str(record.get("status", "")).upper() in {"INVALIDATED", "COMPLETED", "EXPIRED"}:
                    continue
                if key not in market_keys and key not in active_lifecycle_keys:
                    record["status"] = "STALE"
                    record["lifecycle_status"] = "stale"
                    record["last_checked_at_ms"] = now_ms

        for key, record in records.items():
            status = str(record.get("status", "")).upper()
            if status not in {"ACTIVE", "TP1_HIT", "STALE"}:
                continue
            last_seen = max(
                int(record.get("last_seen_at_ms", record.get("created_at_ms", now_ms))),
                int(record.get("last_lifecycle_at_ms", 0)),
            )
            age = max(0, now_ms - last_seen)
            if age >= int(record.get("expire_after_ms", 0)):
                record["status"] = "EXPIRED"
            elif age >= int(record.get("stale_after_ms", 0)):
                record["status"] = "STALE"

        self._write(records)

    def current(self) -> tuple[dict[str, Any], ...]:
        records = [\n            record for record in self.read().values()\n            if int(record.get("strategy_revision", 0)) == REGISTRY_REVISION\n        ]
        order = {"ACTIVE": 0, "TP1_HIT": 1, "STALE": 2, "INVALIDATED": 3, "COMPLETED": 4, "EXPIRED": 5}
        records.sort(key=lambda x: (order.get(str(x.get("status", "")).upper(), 9), -int(x.get("last_seen_at_ms", 0))))
        return tuple(records)


__all__ = ["SetupRegistry"]
