"""Run a local AICFA SMC backtest against the durable candle database.

Examples:
  python scripts/research_smc.py --symbol BTCUSDT --profile scalp
  python scripts/research_smc.py --symbol BTCUSDT --profile scalp --grid

The live candle table is capped at 500 bars per series. The report always states
the available time span; it must not be presented as a 6-12 month validation.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from app.market_data import CRYPTO_SYMBOLS, TRADFI_SYMBOLS, SQLiteCandleStore
from app.smc.backtest import BacktestConfig, parameter_grid, run_backtest


def iso_ms(value: int) -> str:
    return datetime.fromtimestamp(value / 1000, timezone.utc).isoformat()


def available_history(series: dict[str, tuple]) -> dict:
    result = {}
    for timeframe, rows in series.items():
        result[timeframe] = {
            "candles": len(rows),
            "from_utc": iso_ms(rows[0].open_time_ms) if rows else None,
            "to_utc": iso_ms(rows[-1].close_time_ms) if rows else None,
            "span_days": round((rows[-1].close_time_ms - rows[0].open_time_ms) / 86_400_000, 3) if len(rows) > 1 else 0,
        }
    return result


def grid_report(symbol: str, series: dict[str, tuple], profile: str) -> dict:
    trigger_tf = "5m" if profile == "scalp" else "15m"
    trigger = series.get(trigger_tf, ())
    if len(trigger) < 200:
        return {
            "symbol": symbol, "profile": profile, "status": "insufficient_history_for_grid",
            "trigger_candles": len(trigger), "required_trigger_candles": 200,
        }
    train_end = max(40, int(len(trigger) * 0.60))
    validation_end = max(train_end + 1, int(len(trigger) * 0.80))
    rows = []
    for config in parameter_grid():
        train = run_backtest(
            symbol, series, trigger_timeframe=trigger_tf, profile_name=profile,
            config=config, start_index=40, end_index=train_end,
        )
        validation = run_backtest(
            symbol, series, trigger_timeframe=trigger_tf, profile_name=profile,
            config=config, start_index=train_end + 1, end_index=validation_end,
        )
        test = run_backtest(
            symbol, series, trigger_timeframe=trigger_tf, profile_name=profile,
            config=config, start_index=validation_end + 1, end_index=len(trigger) - 1,
        )
        rows.append({
            "settings": {
                "score_threshold": config.score_threshold,
                "min_rr": config.min_rr,
                "stop_buffer_atr": config.stop_buffer_atr,
            },
            "train": train["metrics"],
            "validation": validation["metrics"],
            "out_of_sample": test["metrics"],
        })
    eligible = [row for row in rows if row["train"]["trades"] >= 20]
    pool = eligible or rows
    best = max(pool, key=lambda row: (
        row["train"]["expectancy_r"],
        row["train"]["profit_factor"] if row["train"]["profit_factor"] is not None else -1,
        row["train"]["trades"],
    ))
    return {
        "symbol": symbol, "profile": profile,
        "status": "selected_on_train_only",
        "selection_sample_sufficient": len(eligible) > 0,
        "train_end_utc": iso_ms(trigger[train_end].close_time_ms),
        "validation_end_utc": iso_ms(trigger[validation_end].close_time_ms),
        "best_train_candidate": best,
        "all_parameter_results": rows,
        "warning": "The out-of-sample segment is reported, not used for parameter selection. A short 500-candle window cannot establish durable profitability.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Cost-aware AICFA SMC strategy replay")
    parser.add_argument("--symbol", default="BTCUSDT", help="One configured symbol, e.g. BTCUSDT")
    parser.add_argument("--all-symbols", action="store_true", help="Run the default strategy on all configured symbols")
    parser.add_argument("--profile", choices=("scalp", "intraday", "both"), default="scalp")
    parser.add_argument("--grid", action="store_true", help="Compare the predeclared 27-setting grid; single symbol only")
    parser.add_argument("--output", default="", help="Optional JSON output path")
    args = parser.parse_args()

    symbols = tuple(dict.fromkeys((*CRYPTO_SYMBOLS, *TRADFI_SYMBOLS))) if args.all_symbols else (args.symbol.upper(),)
    if args.grid and args.all_symbols:
        parser.error("--grid is intentionally single-symbol to avoid an uncontrolled CPU-heavy run")
    profiles = ("scalp", "intraday") if args.profile == "both" else (args.profile,)
    store = SQLiteCandleStore()
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "data_source": "local AICFA SQLite closed candles",
        "database_path": str(store.path),
        "fixed_position": {"margin_usd": 5, "leverage": 10, "notional_usd": 50},
        "fees": {"rate_per_side": 0.0005},
        "slippage_bps_per_side": 2.0,
        "results": [],
    }

    for symbol in symbols:
        needed = ("1m", "5m", "15m", "1h") if "scalp" in profiles else ("15m", "1h", "4h")
        if "intraday" in profiles:
            needed = tuple(dict.fromkeys((*needed, "15m", "1h", "4h")))
        series = {tf: store.load_window(symbol, tf) for tf in needed}
        history = available_history(series)
        for profile in profiles:
            if args.grid:
                result = grid_report(symbol, series, profile)
            else:
                trigger_tf = "5m" if profile == "scalp" else "15m"
                result = run_backtest(
                    symbol, series, trigger_timeframe=trigger_tf, profile_name=profile,
                    config=BacktestConfig(),
                )
            result["available_history"] = history
            report["results"].append(result)

    encoded = json.dumps(report, indent=2, allow_nan=False)
    if args.output:
        path = Path(args.output)
        path.write_text(encoded + "\n", encoding="utf-8")
        print(f"Report written to {path}")
    print(encoded)
    store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
