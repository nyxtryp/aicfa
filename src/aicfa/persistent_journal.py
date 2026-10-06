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


def _visual_geometry(result: Any, candidate: Any) -> dict[str, Any]:
    """Serialize causal setup geometry for the terminal chart.

    Geometry is derived from the same feature frames already used by the setup
    engine. The browser only projects these values onto the chart; it never
    recomputes trading logic.
    """
    analyses = getattr(result, "analysis", None)
    # FindSetupResult exposes the execution analysis directly. Other
    # timeframe analyses are reconstructed only from the already-fetched
    # frames when possible; missing feature geometry is simply omitted.
    frames = getattr(result, "frames", {}) or {}
    direction = getattr(candidate, "direction", None)
    source_tfs = tuple(getattr(candidate, "source_timeframes", ()) or ())
    zone_concepts = tuple(getattr(candidate, "zone_concepts", ()) or ())
    structure_tf = getattr(result, "mode", None)
    del structure_tf

    def numeric(value: Any) -> float | None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if number == number and abs(number) != float("inf") else None

    def ts(value: Any) -> int | None:
        try:
            number = int(value)
        except (TypeError, ValueError):
            return None
        return number

    # The setup engine's entry levels already identify the exact source TF.
    # Keep those levels as explicit chart geometry as well.
    entry = tuple(getattr(candidate, "entry_zone", ()) or ())
    zones: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []

    # Find the most recent active directional OB/FVG in a fetched frame.
    # This is intentionally best-effort: the setup remains valid even if a
    # particular visual enrichment is unavailable.
    for timeframe in source_tfs:
        frame = frames.get(timeframe)
        if frame is None or getattr(frame, "empty", True):
            continue
        columns = set(frame.columns)
        if "timestamp" not in columns:
            continue
        ordered = frame.sort_values("timestamp").reset_index(drop=True)

        families = []
        if direction == "long":
            if "imbalance.fvg" in zone_concepts or "imbalance.fvg" in getattr(candidate, "supporting_concepts", ()):
                families.append(("fvg", "fvg_bullish", "fvg_bullish_low", "fvg_bullish_high", "fvg_bullish_creation_timestamp"))
            if "order_block.bullish" in zone_concepts:
                families.append(("ob", "order_block_bullish", "order_block_bullish_low", "order_block_bullish_high", None))
        elif direction == "short":
            if "imbalance.fvg" in zone_concepts or "imbalance.fvg" in getattr(candidate, "supporting_concepts", ()):
                families.append(("fvg", "fvg_bearish", "fvg_bearish_low", "fvg_bearish_high", "fvg_bearish_creation_timestamp"))
            if "order_block.bearish" in zone_concepts:
                families.append(("ob", "order_block_bearish", "order_block_bearish_low", "order_block_bearish_high", None))

        for kind, event_col, low_col, high_col, creation_col in families:
            if event_col not in columns or low_col not in columns or high_col not in columns:
                continue
            active_col = "fvg_active" if kind == "fvg" else "order_block_active"
            selected = None
            for i in range(len(ordered) - 1, -1, -1):
                row = ordered.iloc[i]
                active = numeric(row.get(active_col, 0)) if active_col in columns else 1.0
                low = numeric(row.get(low_col))
                high = numeric(row.get(high_col))
                if active and low is not None and high is not None:
                    selected = (i, low, high)
                    break
            if selected is None:
                continue
            i, low, high = selected
            start = None
            if creation_col and creation_col in columns:
                start = ts(ordered.iloc[i].get(creation_col))
            if start is None:
                for j in range(i, -1, -1):
                    if numeric(ordered.iloc[j].get(event_col, 0)) == 1:
                        start = ts(ordered.iloc[j].get("timestamp"))
                        break
            end = ts(ordered.iloc[-1].get("timestamp"))
            if start is not None and end is not None:
                zones.append({
                    "type": kind,
                    "priceLow": low,
                    "priceHigh": high,
                    "timeStart": start,
                    "timeEnd": end,
                    "timeframe": timeframe,
                })

        # Structural events: price is the causally referenced swing level.
        for kind, event_col, ref_col, side_col in (
            ("BOS", "bos_up" if direction == "long" else "bos_down",
             "bos_up_reference_pivot_index" if direction == "long" else "bos_down_reference_pivot_index",
             "high" if direction == "long" else "low"),
            ("CHoCH", "choch_up" if direction == "long" else "choch_down",
             "bos_up_reference_pivot_index" if direction == "long" else "bos_down_reference_pivot_index",
             "high" if direction == "long" else "low"),
            ("MSS", "mss_up" if direction == "long" else "mss_down",
             "bos_up_reference_pivot_index" if direction == "long" else "bos_down_reference_pivot_index",
             "high" if direction == "long" else "low"),
        ):
            if event_col not in columns:
                continue
            for i in range(len(ordered) - 1, -1, -1):
                if numeric(ordered.iloc[i].get(event_col, 0)) != 1:
                    continue
                ref = numeric(ordered.iloc[i].get(ref_col, -1)) if ref_col in columns else None
                price = None
                if ref is not None and ref >= 0 and int(ref) < len(ordered):
                    price = numeric(ordered.iloc[int(ref)].get(side_col))
                if price is None:
                    price = numeric(ordered.iloc[i].get(side_col))
                start = ts(ordered.iloc[i].get("timestamp"))
                end = ts(ordered.iloc[-1].get("timestamp"))
                if price is not None and start is not None and end is not None:
                    events.append({
                        "type": kind,
                        "price": price,
                        "timeStart": start,
                        "timeEnd": end,
                        "timeframe": timeframe,
                    })
                break

    # Deduplicate visual objects by their stable geometry.
    unique_zones = {json.dumps(z, sort_keys=True): z for z in zones}
    unique_events = {json.dumps(e, sort_keys=True): e for e in events}
    return {
        "zones": list(unique_zones.values()),
        "events": list(unique_events.values()),
        "entry": [
            {
                "price": float(level.value),
                "timeframe": level.timeframe,
                "source": level.source,
            }
            for level in entry
        ],
    }


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
            horizons = []
            for result in getattr(market, "results", ()):
                evidence = getattr(result, "evidence_assessment", None)
                setup = getattr(result, "setup_assessment", None)
                decision = getattr(result, "decision_assessment", None)
                horizons.append({
                    "mode": result.mode,
                    "decision": result.decision,
                    "reason": result.reason,
                    "supported_concepts": getattr(evidence, "supported_concepts", ()),
                    "possible_concepts": getattr(evidence, "possible_concepts", ()),
                    "missing_context": getattr(evidence, "missing_context", ()),
                    "conflicts": getattr(evidence, "conflicts", ()),
                    "setup_decision": getattr(setup, "decision", None),
                    "setup_reasons": getattr(setup, "reasons", ()),
                    "setup_missing_context": getattr(setup, "missing_context", ()),
                    "setup_conflicts": getattr(setup, "conflicts", ()),
                    "decision_action": getattr(decision, "action", None),
                    "decision_reasons": getattr(decision, "reasons", ()),
                })
            result_map = {getattr(result, "mode", None): result for result in getattr(market, "results", ())}
            enriched_setups = []
            for setup in market.setups:
                candidate = getattr(setup, "candidate", None)
                payload = _jsonable(setup)
                result = result_map.get(getattr(setup, "mode", None))
                if result is not None and candidate is not None:
                    payload["chart"] = _visual_geometry(result, candidate)
                enriched_setups.append(payload)
            markets.append({
                "asset": market.asset,
                "diagnostics": diagnostics,
                "setups": enriched_setups,
                "horizons": horizons,
                "lifecycle_results": market.lifecycle_results,
            })
        self.append(
            "scan",
            state.scanned_at_ms,
            {
                "scan_number": state.scan_number,
                "rotation_id": state.rotation_id,
                "queue_position": state.queue_position,
                "universe_size": state.universe_size,
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
