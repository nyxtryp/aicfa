#!/usr/bin/env python3
"""Read-only smoke replay for the armed-zone gate against persisted VDS candles.

This is a conservative proxy, not a full setup-result equivalence proof: it
counts structural confirmation candles that would be skipped by the zone gate.
It never changes the candle store or contacts an exchange.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aicfa.armed_zones import candle_intersects_armed_zone, extract_active_smc_zones, zones_for_trigger_timeframe
from aicfa.features import build_features
from aicfa.market_data import timeframe_ms, validate_ohlcv


FEATURE_WINDOWS = {
    "1m": 500,
    "5m": 500,
    "15m": 500,
    "1h": 500,
    "4h": 500,
    "1d": 365,
    "1w": 200,
}
CONFIRMATION_COLUMNS = (
    "sweep_high_reclaim",
    "sweep_low_reclaim",
    "choch_up",
    "choch_down",
    "mss_up",
    "mss_down",
    "bos_up",
    "bos_down",
    "smc_sweep_low_reclaim",
    "smc_sweep_high_reclaim",
)
SETUP_CANDIDATE_COLUMNS = (
    "setup_liquidity_reversal_up",
    "setup_liquidity_reversal_down",
    "setup_structure_continuation_up",
    "setup_structure_continuation_down",
    "setup_breakout_retest_up",
    "setup_breakout_retest_down",
    "setup_failed_breakout_up",
    "setup_failed_breakout_down",
    "setup_wyckoff_spring",
    "setup_wyckoff_upthrust",
    "setup_expansion_up",
    "setup_expansion_down",
)


def _load_frames(directory: Path) -> dict[str, pd.DataFrame]:
    frames: dict[str, pd.DataFrame] = {}
    for timeframe, limit in FEATURE_WINDOWS.items():
        path = directory / f"{timeframe}.csv"
        if not path.is_file():
            continue
        try:
            frame = validate_ohlcv(pd.read_csv(path))
        except Exception:
            continue
        if not frame.empty:
            frames[timeframe] = frame.tail(limit).reset_index(drop=True)
    return frames


def _features(frames: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    return {
        timeframe: build_features(frame)
        for timeframe, frame in frames.items()
        if not frame.empty
    }


def _latest_completed(analysis: pd.DataFrame, timeframe: str, event_close_ms: int) -> pd.DataFrame:
    if analysis.empty:
        return analysis
    ready_at = pd.to_numeric(analysis["timestamp"], errors="coerce") + timeframe_ms(timeframe)
    eligible = analysis.loc[ready_at <= event_close_ms]
    return eligible.tail(1).copy()


def _has_flag(row: pd.Series, columns: tuple[str, ...]) -> bool:
    for column in columns:
        value = row.get(column, 0)
        try:
            if float(value) != 0:
                return True
        except (TypeError, ValueError):
            continue
    return False


def _has_confirmation(row: pd.Series) -> bool:
    return _has_flag(row, CONFIRMATION_COLUMNS)


def _has_setup_candidate(row: pd.Series) -> bool:
    return _has_flag(row, SETUP_CANDIDATE_COLUMNS)


def replay_symbol(directory: Path, *, candles: int) -> dict | None:
    frames = _load_frames(directory)
    if "1m" not in frames or "5m" not in frames:
        return None
    analyses = _features(frames)
    summary = {
        "symbol": directory.name.replace("_", "/"),
        "checked_1m": 0,
        "skipped_1m": 0,
        "confirmations_1m": 0,
        "skipped_confirmations_1m": 0,
        "setup_candidates_1m": 0,
        "skipped_setup_candidates_1m": 0,
        "checked_5m": 0,
        "skipped_5m": 0,
        "confirmations_5m": 0,
        "skipped_confirmations_5m": 0,
        "setup_candidates_5m": 0,
        "skipped_setup_candidates_5m": 0,
    }

    for trigger_timeframe, htf_timeframes in (
        ("1m", ("5m", "15m", "1h", "4h", "1d", "1w")),
        ("5m", ("15m", "1h", "4h", "1d", "1w")),
    ):
        trigger_frame = analyses.get(trigger_timeframe)
        if trigger_frame is None or trigger_frame.empty:
            continue
        for _, candle in trigger_frame.tail(candles).iterrows():
            event_close_ms = int(candle["timestamp"]) + timeframe_ms(trigger_timeframe)
            htf_rows: dict[str, pd.DataFrame] = {}
            for timeframe in htf_timeframes:
                analysis = analyses.get(timeframe)
                if analysis is None:
                    continue
                latest = _latest_completed(analysis, timeframe, event_close_ms)
                if not latest.empty:
                    htf_rows[timeframe] = latest
            zones = extract_active_smc_zones(htf_rows)
            gate_zones = zones_for_trigger_timeframe(zones, trigger_timeframe)
            intersects = candle_intersects_armed_zone(
                float(candle["low"]), float(candle["high"]), gate_zones
            )
            confirmation = _has_confirmation(candle)
            setup_candidate = _has_setup_candidate(candle)
            summary[f"checked_{trigger_timeframe}"] += 1
            if confirmation:
                summary[f"confirmations_{trigger_timeframe}"] += 1
            if setup_candidate:
                summary[f"setup_candidates_{trigger_timeframe}"] += 1
            if not intersects:
                summary[f"skipped_{trigger_timeframe}"] += 1
                if confirmation:
                    summary[f"skipped_confirmations_{trigger_timeframe}"] += 1
                if setup_candidate:
                    summary[f"skipped_setup_candidates_{trigger_timeframe}"] += 1

    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("/srv/frostdeploy/aicfa/shared/data"))
    parser.add_argument("--max-symbols", type=int, default=4)
    parser.add_argument("--candles", type=int, default=30)
    args = parser.parse_args()
    if args.max_symbols < 1 or args.candles < 1:
        parser.error("--max-symbols and --candles must be positive")

    raw = args.data_dir / "raw"
    directories = sorted(path for path in raw.iterdir() if path.is_dir()) if raw.is_dir() else []
    summaries = []
    for directory in directories:
        result = replay_symbol(directory, candles=args.candles)
        if result is not None:
            summaries.append(result)
        if len(summaries) >= args.max_symbols:
            break

    if not summaries:
        print(json.dumps({
            "ok": False,
            "error": "no symbols with both 1m and 5m candle history found",
            "data_dir": str(args.data_dir),
        }, indent=2))
        return 2

    totals = {
        key: sum(item[key] for item in summaries)
        for key in (
            "checked_1m", "skipped_1m", "confirmations_1m", "skipped_confirmations_1m",
            "setup_candidates_1m", "skipped_setup_candidates_1m",
            "checked_5m", "skipped_5m", "confirmations_5m", "skipped_confirmations_5m",
            "setup_candidates_5m", "skipped_setup_candidates_5m",
        )
    }
    for trigger in ("1m", "5m"):
        checked = totals[f"checked_{trigger}"]
        totals[f"skip_rate_{trigger}"] = round(totals[f"skipped_{trigger}"] / checked, 4) if checked else 0.0

    print(json.dumps({
        "ok": True,
        "mode": "read-only OHLCV replay; structural confirmation proxy, not full setup equivalence",
        "symbols": len(summaries),
        "candles_per_trigger_max": args.candles,
        "totals": totals,
        "per_symbol": summaries,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
