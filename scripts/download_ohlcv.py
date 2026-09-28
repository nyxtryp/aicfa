#!/usr/bin/env python3
"""Download historical OHLCV data for AICFA.

Examples:
    python scripts/download_ohlcv.py --symbols BTC/USDT ETH/USDT
    python scripts/download_ohlcv.py --symbols BTC/USDT --timeframes 15m 1h 4h
    python scripts/download_ohlcv.py --all --timeframes 15m 1h 4h

The downloader is incremental: existing CSV data is preserved and only
missing candles after the latest saved timestamp are requested.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import ccxt
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
DEFAULT_TIMEFRAMES = ["15m", "1h", "4h"]
LIMIT = 1000
PAUSE_SECONDS = 0.2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download AICFA OHLCV data")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--symbols",
        nargs="+",
        help="Symbols such as BTC/USDT ETH/USDT",
    )
    group.add_argument(
        "--all",
        action="store_true",
        help="Download all active USDT spot symbols available on Binance",
    )
    parser.add_argument(
        "--timeframes",
        nargs="+",
        default=DEFAULT_TIMEFRAMES,
        help="Timeframes to download (default: 15m 1h 4h)",
    )
    parser.add_argument(
        "--since",
        type=str,
        default=None,
        help="Initial UTC date, e.g. 2020-01-01. Ignored when data already exists.",
    )
    return parser.parse_args()


def make_exchange() -> ccxt.Exchange:
    exchange = ccxt.binance({
        "enableRateLimit": True,
        "options": {"defaultType": "spot"},
    })
    exchange.load_markets()
    return exchange


def normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper()


def symbol_slug(symbol: str) -> str:
    return normalize_symbol(symbol).replace("/", "_")


def get_symbols(exchange: ccxt.Exchange, requested: list[str] | None, all_symbols: bool) -> list[str]:
    if not all_symbols:
        symbols = [normalize_symbol(symbol) for symbol in requested or []]
    else:
        symbols = sorted(
            market["symbol"]
            for market in exchange.markets.values()
            if market.get("spot")
            and market.get("active", True)
            and market.get("quote") == "USDT"
        )

    missing = [symbol for symbol in symbols if symbol not in exchange.markets]
    if missing:
        raise ValueError(f"Symbols not found on Binance: {', '.join(missing[:20])}")

    return symbols


def timeframe_ms(exchange: ccxt.Exchange, timeframe: str) -> int:
    milliseconds = exchange.parse_timeframe(timeframe) * 1000
    if not milliseconds:
        raise ValueError(f"Unsupported timeframe: {timeframe}")
    return milliseconds


def load_existing(path: Path) -> pd.DataFrame | None:
    if not path.exists() or path.stat().st_size == 0:
        return None

    df = pd.read_csv(path)
    if df.empty:
        return None

    required = ["timestamp", "datetime", "open", "high", "low", "close", "volume"]
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise ValueError(f"{path} is missing columns: {missing}")

    df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce").astype("Int64")
    df = df.dropna(subset=["timestamp"]).copy()
    df["timestamp"] = df["timestamp"].astype("int64")
    return df


def fetch_all(
    exchange: ccxt.Exchange,
    symbol: str,
    timeframe: str,
    since_ms: int,
    until_ms: int,
) -> list[list[float]]:
    rows: list[list[float]] = []
    cursor = since_ms
    step = timeframe_ms(exchange, timeframe)

    while cursor < until_ms:
        batch = exchange.fetch_ohlcv(
            symbol,
            timeframe=timeframe,
            since=cursor,
            limit=LIMIT,
        )

        if not batch:
            break

        fresh = [row for row in batch if row[0] < until_ms]
        if not fresh:
            break

        rows.extend(fresh)

        last_timestamp = fresh[-1][0]
        next_cursor = last_timestamp + step
        if next_cursor <= cursor:
            break

        cursor = next_cursor
        print(
            f"    {symbol} {timeframe}: "
            f"{pd.to_datetime(last_timestamp, unit='ms', utc=True).isoformat()}",
            flush=True,
        )

        if len(batch) < LIMIT:
            break

        time.sleep(PAUSE_SECONDS)

    return rows


def save_data(path: Path, rows: list[list[float]], existing: pd.DataFrame | None) -> int:
    new_df = pd.DataFrame(
        rows,
        columns=["timestamp", "open", "high", "low", "close", "volume"],
    )

    if not new_df.empty:
        new_df["timestamp"] = new_df["timestamp"].astype("int64")
        new_df["datetime"] = pd.to_datetime(
            new_df["timestamp"], unit="ms", utc=True
        ).astype(str)
        new_df = new_df[
            ["timestamp", "datetime", "open", "high", "low", "close", "volume"]
        ]

    if existing is not None:
        combined = pd.concat([existing, new_df], ignore_index=True)
    else:
        combined = new_df

    if combined.empty:
        return 0

    combined = (
        combined.drop_duplicates(subset=["timestamp"], keep="last")
        .sort_values("timestamp")
        .reset_index(drop=True)
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_csv(path, index=False)
    return len(new_df)


def download_one(
    exchange: ccxt.Exchange,
    symbol: str,
    timeframe: str,
    initial_since_ms: int | None,
) -> None:
    path = RAW_DIR / symbol_slug(symbol) / f"{timeframe}.csv"
    existing = load_existing(path)

    step = timeframe_ms(exchange, timeframe)
    now_ms = exchange.milliseconds()

    if existing is not None and not existing.empty:
        latest = int(existing["timestamp"].max())
        since_ms = latest + step
    elif initial_since_ms is not None:
        since_ms = initial_since_ms
    else:
        # Default: one year of history for a first test.
        since_ms = now_ms - 365 * 24 * 60 * 60 * 1000

    if since_ms >= now_ms:
        print(f"  {symbol} {timeframe}: already up to date")
        return

    print(f"  {symbol} {timeframe}: downloading...")
    rows = fetch_all(exchange, symbol, timeframe, since_ms, now_ms)
    added = save_data(path, rows, existing)
    print(f"  {symbol} {timeframe}: +{added} candles -> {path}")


def main() -> None:
    args = parse_args()
    exchange = make_exchange()

    symbols = get_symbols(exchange, args.symbols, args.all)

    invalid_timeframes = [
        timeframe for timeframe in args.timeframes
        if timeframe not in exchange.timeframes
    ]
    if invalid_timeframes:
        raise ValueError(
            f"Unsupported Binance timeframes: {', '.join(invalid_timeframes)}"
        )

    initial_since_ms = (
        exchange.parse8601(f"{args.since}T00:00:00Z")
        if args.since
        else None
    )

    print(f"Exchange: Binance spot")
    print(f"Symbols: {len(symbols)}")
    print(f"Timeframes: {', '.join(args.timeframes)}")
    print(f"Raw data: {RAW_DIR}")
    print()

    for symbol in symbols:
        for timeframe in args.timeframes:
            try:
                download_one(exchange, symbol, timeframe, initial_since_ms)
            except ccxt.BaseError as exc:
                print(f"  ERROR {symbol} {timeframe}: {exc}")
            except Exception as exc:
                print(f"  ERROR {symbol} {timeframe}: {exc}")

    print("\nDone.")


if __name__ == "__main__":
    main()
