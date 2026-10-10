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


REGISTRY_REVISION = 6

# Revision 3 introduced the lifecycle-owned setup queue. Those ACTIVE/TP1_HIT
# records are real trade lifecycles and must survive a code deploy. Older
# revisions may contain analytical candidates that were never lifecycle-
# activated, so they are intentionally not migrated.
_MIGRATABLE_PREVIOUS_REVISIONS = {3, 4, 5}
_MIGRATABLE_LIFECYCLE_STATUSES = {"active", "tp1_hit"}


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
        # Entry-zone coordinates change as analysis refreshes. They describe
        # geometry, not identity; including them created a journal row on each
        # small price-level update.
        return "|".join((
            str(asset), str(market_type), normalized.value, scenario, direction,
            profile.structure_timeframe,
        ))

    @staticmethod
    def _key_from_identity(identity: Any) -> str | None:
        if identity is None:
            return None
        return "|".join((
            str(identity.symbol), str(identity.market_type),
            normalize_trading_mode(identity.horizon).value,
            str(getattr(identity, "scenario", "")).strip().lower(),
            str(identity.direction).strip().lower(),
            mode_timeframe_profile(normalize_trading_mode(identity.horizon)).structure_timeframe,
        ))

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

    @staticmethod
    def _migrate_lifecycle_records(records: dict[str, dict[str, Any]]) -> bool:
        """Migrate lifecycle-owned setups while preserving their POI identity."""
        changed = False
        for old_key, record in list(records.items()):
            try:
                revision = int(record.get("strategy_revision", 0))
            except (TypeError, ValueError):
                revision = 0
            lifecycle_status = str(record.get("lifecycle_status", "")).lower()
            if revision not in _MIGRATABLE_PREVIOUS_REVISIONS:
                continue
            # Revisions 3/4 only persisted lifecycle-owned active records.
            # Revision 5 also accumulated terminal entries; retain them as
            # historical outcomes, but separate MISSED_BY_PRICE in the UI.
            if revision in {3, 4} and lifecycle_status not in _MIGRATABLE_LIFECYCLE_STATUSES:
                continue
            if revision == 5 and str(record.get("status", "")).upper() not in {
                "ACTIVE", "TP1_HIT", "COMPLETED", "INVALIDATED", "EXPIRED", "MISSED_BY_PRICE"
            }:
                continue
            setup = record.get("setup", {})
            candidate = setup.get("candidate", {}) if isinstance(setup, dict) else {}
            new_key = "|".join((
                str(record.get("asset", "")),
                str(record.get("market_type", "spot")),
                str(record.get("mode", "intraday")),
                str(record.get("scenario", "")).strip().lower(),
                str(record.get("direction", "")).strip().lower(),
                str(record.get("structural_timeframe", "")),
            ))
            record["strategy_revision"] = REGISTRY_REVISION
            record["setup_id"] = new_key
            previous = records.get(new_key)
            if previous is not None and previous is not record:
                previous_time = int(previous.get("closed_at_ms") or previous.get("last_seen_at_ms") or previous.get("created_at_ms") or 0)
                current_time = int(record.get("closed_at_ms") or record.get("last_seen_at_ms") or record.get("created_at_ms") or 0)
                if current_time < previous_time:
                    records.pop(old_key, None)
                    changed = True
                    continue
            records[new_key] = record
            if new_key != old_key:
                records.pop(old_key, None)
            changed = True
        return changed

    def _current_revision_records(self) -> dict[str, dict[str, Any]]:
        records = self.read()
        if self._migrate_lifecycle_records(records):
            self._write(records)
        return {
            key: value
            for key, value in records.items()
            if int(value.get("strategy_revision", 0)) == REGISTRY_REVISION
        }

    def record_scan(self, state: Any) -> None:
        records = self._current_revision_records()
        now_ms = int(state.scanned_at_ms)

        state_markets = tuple(state.result.markets)
        scanned_assets: set[str] = set()
        for market in state_markets:
            scanned_assets.add(str(market.asset))
            asset = market.asset
            diagnostics = getattr(market, "diagnostics", None)
            scan_status = str(getattr(diagnostics, "status", "completed")).strip().lower()
            market_scan_succeeded = scan_status not in {"error", "timeout"}
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
                previous = records.get(key, {})
                created_at = int(previous.get("created_at_ms", now_ms))
                status = "ACTIVE"
                lifecycle = getattr(setup, "lifecycle_result", None)
                lifecycle_status = getattr(getattr(lifecycle, "status", None), "value", None)
                # A setup candidate is only actionable after the lifecycle
                # engine has actually activated it at the POI. A structural
                # hypothesis still waiting for price to reach its entry zone
                # must not enter the terminal setup queue.
                if lifecycle_status not in {"active", "tp1_hit", "missed_by_price"}:
                    continue
                status = (
                    "TP1_HIT" if lifecycle_status == "tp1_hit"
                    else "MISSED_BY_PRICE" if lifecycle_status == "missed_by_price"
                    else "ACTIVE"
                )
                payload = _jsonable(setup)
                result = next((item for item in getattr(market, "results", ()) if getattr(item, "mode", None) == getattr(setup, "mode", None)), None)
                if result is not None:
                    payload["chart"] = _visual_geometry(result, candidate)
                market_keys.add(key)
                records[key] = {
                    **previous,
                    "strategy_revision": REGISTRY_REVISION,
                    "setup_id": key,
                    "asset": asset,
                    "market_type": market_type,
                    "mode": normalize_trading_mode(setup.mode).value,
                    "scenario": str(getattr(candidate, "scenario", "")),
                    "direction": str(getattr(candidate, "direction", "")).upper(),
                    "structural_timeframe": mode_timeframe_profile(normalize_trading_mode(setup.mode)).structure_timeframe,
                    "status": status,
                    "lifecycle_status": lifecycle_status or "active",
                    "closed_at_ms": now_ms if lifecycle_status == "missed_by_price" else previous.get("closed_at_ms"),
                    "outcome_reason": str(getattr(lifecycle, "reason", "") or "") if lifecycle_status == "missed_by_price" else previous.get("outcome_reason", ""),
                    "created_at_ms": created_at,
                    "last_seen_at_ms": now_ms,
                    "last_confirmed_at_ms": now_ms,
                    "last_checked_at_ms": now_ms,
                    "last_scan_number": int(state.scan_number),
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
                if status in {"invalidated", "completed", "expired", "missed_by_price"}:
                    record["status"] = status.upper()
                    record["lifecycle_status"] = status
                    record["closed_at_ms"] = now_ms
                    record["outcome_reason"] = str(getattr(lifecycle, "reason", "") or "")
                elif status in {"active", "tp1_hit"} and record.get("status") not in {"INVALIDATED", "COMPLETED", "EXPIRED", "MISSED_BY_PRICE"}:
                    # Keep TP1_HIT distinct from ACTIVE: the original entry is
                    # no longer actionable once price has reached TP1, even
                    # though the setup may remain alive toward later targets.
                    record["status"] = "TP1_HIT" if status == "tp1_hit" else "ACTIVE"
                    record["lifecycle_status"] = status
                    record["last_lifecycle_at_ms"] = now_ms

            # A failed/timeout scan provides no evidence that an existing setup
            # is stale. Preserve its last known lifecycle until a successful
            # analysis of that same market can confirm or invalidate it.
            if market_scan_succeeded:
                for key, record in records.items():
                    if str(record.get("asset", "")) != str(asset):
                        continue
                    if str(record.get("status", "")).upper() in {"INVALIDATED", "COMPLETED", "EXPIRED", "MISSED_BY_PRICE"}:
                        continue
                    if key not in market_keys and key not in active_lifecycle_keys:
                        record["status"] = "STALE"
                        record["lifecycle_status"] = "stale"
                        record["last_checked_at_ms"] = now_ms

        # Only a complete universe pass can stale records for markets absent
        # from the result. The production rotation/manual endpoints normally
        # provide one-market snapshots; treating those as a full scan used to
        # erase every other market's active setups on each request.
        full_scan_marker = getattr(state, "is_full_universe_scan", None)
        if full_scan_marker is None:
            universe_size = getattr(state, "universe_size", None)
            is_full_universe_scan = (
                universe_size is None
                or len(state_markets) >= int(universe_size)
            )
        else:
            is_full_universe_scan = bool(full_scan_marker)

        if is_full_universe_scan:
            for key, record in records.items():
                if str(record.get("asset", "")) in scanned_assets:
                    continue
                if str(record.get("status", "")).upper() in {"INVALIDATED", "COMPLETED", "EXPIRED", "MISSED_BY_PRICE"}:
                    continue
                record["status"] = "STALE"
                record["lifecycle_status"] = "stale"
                record["last_checked_at_ms"] = now_ms

        self._write(records)

    def record_lifecycle_results(self, results: tuple[Any, ...], *, now_ms: int) -> None:
        """Apply price-stream lifecycle transitions to the durable current projection."""
        records = self._current_revision_records()
        changed = False
        for result in results:
            identity = getattr(result, "identity", None)
            key = self._key_from_identity(identity)
            if not key or key not in records:
                continue
            status = getattr(getattr(result, "status", None), "value", None)
            if status is None:
                continue
            record = records[key]
            record["last_checked_at_ms"] = int(now_ms)
            record["last_lifecycle_at_ms"] = int(now_ms)
            if status in {"active", "tp1_hit", "invalidated", "completed", "expired", "missed_by_price"}:
                record["lifecycle_status"] = status
                record["status"] = "TP1_HIT" if status == "tp1_hit" else status.upper()
                if status in {"invalidated", "completed", "expired", "missed_by_price"}:
                    record["closed_at_ms"] = int(now_ms)
                    record["outcome_reason"] = str(getattr(result, "reason", "") or "")
                changed = True
        if changed:
            self._write(records)

    def current(self) -> tuple[dict[str, Any], ...]:
        # Actionable state is lifecycle-owned. Do not expire a real active
        # setup merely because a wall-clock TTL elapsed between rotations;
        # the lifecycle engine must invalidate it from actual price action.
        records = []
        for record in self._current_revision_records().values():
            if str(record.get("status", "")).upper() != "ACTIVE":
                continue
            records.append(record)
        records.sort(key=lambda x: -int(x.get("last_seen_at_ms", 0)))
        return tuple(records)



__all__ = ["SetupRegistry"]
