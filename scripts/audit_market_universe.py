#!/usr/bin/env python3
"""Audit configured AICFA instruments against live public CCXT market metadata.

This is an audit-only tool: it does not change the configured universe or trade.
Writes a JSON report and a Markdown summary for GitHub Actions artifacts.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import ccxt

ROOT = Path(__file__).resolve().parents[1]
UNIVERSE_PATH = Path(os.environ.get("AICFA_MARKET_UNIVERSE", ROOT / "config/market_universe.json"))
REPORT_DIR = Path(os.environ.get("AICFA_AUDIT_DIR", ROOT / "artifacts/market-audit"))
EXCHANGES = (
    "binance", "bybit", "okx", "bitget", "gate", "kucoin", "mexc",
    "bingx", "htx", "bitmart", "coinex", "whitebit", "bitrue",
    "cryptocom", "kraken", "coinbase", "bitfinex", "bitstamp",
    "gemini", "upbit",
)
MULTIPLIERS = ("1000000", "100000", "10000", "1000", "1M")
ALIASES = {"POL": ("MATIC",), "RENDER": ("RNDR",), "BTC": ("XBT",)}


def canonical_parts(asset: str) -> tuple[str, str]:
    parts = asset.upper().split("/", 1)
    if len(parts) == 2:
        return parts[0], parts[1].split(":", 1)[0]
    return asset.upper(), "USDT"


def eligible(market: dict, market_type: str) -> bool:
    if str(market.get("quote", "")).upper() != "USDT":
        return False
    if market_type == "spot":
        return market.get("spot") is True
    return bool(market.get("contract")) and bool(market.get("swap") or market.get("future"))


def matches(market: dict, base: str, market_type: str) -> bool:
    market_base = str(market.get("base", "")).upper()
    if market_base == base or market_base in ALIASES.get(base, ()):
        return True
    return market_type == "futures" and any(
        market_base.startswith(prefix) and market_base[len(prefix):] == base
        for prefix in MULTIPLIERS
    )


def main() -> int:
    universe = json.loads(UNIVERSE_PATH.read_text(encoding="utf-8"))
    configured = universe.get("markets", [])
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []
    venue_results: dict[str, dict] = {}
    started = time.time()

    for exchange_id in EXCHANGES:
        try:
            exchange_cls = getattr(ccxt, exchange_id, None)
            if exchange_cls is None:
                venue_results[exchange_id] = {"status": "not_in_installed_ccxt"}
                continue
            exchange = exchange_cls({"enableRateLimit": True, "timeout": 15000})
            markets = exchange.load_markets()
            venue_results[exchange_id] = {"status": "loaded", "markets": len(markets)}
        except Exception as exc:
            venue_results[exchange_id] = {
                "status": "load_failed",
                "error": f"{type(exc).__name__}: {str(exc)[:240]}",
            }
            continue

        for item in configured:
            asset = str(item.get("asset", ""))
            market_type = str(item.get("market_type", "futures"))
            asset_class = str(item.get("asset_class", "crypto"))
            base, quote = canonical_parts(asset)
            if quote != "USDT":
                records.append({
                    "asset": asset, "asset_class": asset_class, "market_type": market_type,
                    "exchange": exchange_id, "status": "unsupported_quote",
                    "matched_symbol": "", "reason": f"quote {quote} is not audited",
                })
                continue

            explicit = (item.get("venue_symbols") or {}).get(exchange_id)
            if asset_class != "crypto":
                if not explicit:
                    records.append({
                        "asset": asset, "asset_class": asset_class, "market_type": market_type,
                        "exchange": exchange_id, "status": "not_configured_on_venue",
                        "matched_symbol": "", "reason": "no venue_symbols mapping",
                    })
                    continue
                exact = next((m for m in markets.values() if str(m.get("symbol", "")) == explicit), None)
                if exact and eligible(exact, market_type):
                    status, symbol, reason = "MATCH", explicit, "configured exact venue symbol exists"
                    candidates = []
                else:
                    status, symbol = "MISSING_CONFIGURED_SYMBOL", explicit
                    base_aliases = {
                        "XAU": {"GOLD", "XAUT"},
                        "XAG": {"SILVER"},
                        "XCU": {"COPPER"},
                        "XPT": {"PLATINUM"},
                        "BRENT": {"XBRU", "BZ", "UKOIL", "BRENTOIL"},
                        "NATGAS": {"NG", "NGAS", "NATURALGAS"},
                        "NIKKEI": {"JP225", "JPN225", "NIKKEI225"},
                        "QQQ": {"QQQSTOCK"},
                        "AAPL": {"AAPLSTOCK"},
                        "NVDA": {"NVIDIA", "NVIDIASTOCK"},
                        "AMZN": {"AMZNSTOCK"},
                        "GOOGL": {"GOOGLSTOCK"},
                        "META": {"METASTOCK"},
                        "TSLA": {"TESLA", "TESLASTOCK"},
                        "AVGO": {"AVGOSTOCK"},
                        "AMD": {"AMDSTOCK"},
                        "TSM": {"TSMC", "TSMCSTOCK"},
                        "ASML": {"ASMLSTOCK"},
                        "ORCL": {"ORCLSTOCK"},
                        "NFLX": {"NFLXSTOCK"},
                        "COIN": {"COINBASE", "COINSTOCK"},
                        "SP500": {"US500", "SPX500", "SP500"},
                        "NASDAQ100": {"US100", "NAS100", "NASDAQ100"},
                    }
                    base = asset.split("/", 1)[0].upper()
                    accepted_bases = {base, *base_aliases.get(base, set())}
                    candidates = []
                    for market in markets.values():
                        if not eligible(market, market_type):
                            continue
                        market_base = str(market.get("base", "")).upper()
                        market_id = str(market.get("id", "")).upper()
                        info = market.get("info") or {}
                        display = " ".join(str(info.get(key, "")) for key in (
                            "displayName", "displayNameEn", "baseCoinName", "symbol"
                        )).upper()
                        if market_base in accepted_bases or market_id in accepted_bases:
                            candidates.append(market)
                        elif any(alias and alias in display for alias in accepted_bases):
                            candidates.append(market)
                    candidates.sort(key=lambda m: (
                        0 if str(m.get("base", "")).upper() == base else 1,
                        0 if m.get("active") is True else 1,
                        str(m.get("symbol", "")),
                    ))
                    suggestion_text = ", ".join(
                        f"{m.get('symbol')} [id={m.get('id')}, base={m.get('base')}, active={m.get('active')}]"
                        for m in candidates[:8]
                    )
                    reason = "configured symbol absent or wrong market type"
                    if suggestion_text:
                        reason += "; live candidates: " + suggestion_text
                records.append({
                    "asset": asset, "asset_class": asset_class, "market_type": market_type,
                    "exchange": exchange_id, "status": status,
                    "matched_symbol": symbol, "reason": reason,
                    "candidate_symbols": [str(m.get("symbol", "")) for m in candidates[:8]],
                })
                continue

            candidates = [
                m for m in markets.values()
                if eligible(m, market_type) and matches(m, base, market_type)
            ]
            candidates.sort(key=lambda m: (
                0 if str(m.get("base", "")).upper() == base else 1,
                0 if m.get("active") is not False else 1,
                str(m.get("symbol", "")),
            ))
            if candidates:
                market = candidates[0]
                status = "MATCH" if str(market.get("base", "")).upper() == base else "MATCH_ALIAS"
                records.append({
                    "asset": asset, "asset_class": asset_class, "market_type": market_type,
                    "exchange": exchange_id, "status": status,
                    "matched_symbol": str(market.get("symbol", "")),
                    "reason": f"base={market.get('base')} quote={market.get('quote')} active={market.get('active')}",
                })
            else:
                records.append({
                    "asset": asset, "asset_class": asset_class, "market_type": market_type,
                    "exchange": exchange_id, "status": "NO_MATCH",
                    "matched_symbol": "", "reason": "no eligible USDT market or known ticker alias",
                })

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": round(time.time() - started, 2),
        "universe_path": str(UNIVERSE_PATH),
        "configured_instruments": len(configured),
        "exchanges": venue_results,
        "records": records,
    }
    (REPORT_DIR / "market-audit.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    summary_lines = [
        "# AICFA live market-universe audit",
        "",
        f"- Generated: {report['generated_at']}",
        f"- Configured instruments: {len(configured)}",
        f"- Exchanges loaded: {sum(1 for x in venue_results.values() if x['status'] == 'loaded')}/{len(EXCHANGES)}",
        f"- Duration: {report['duration_seconds']}s",
        "",
        "## Venue status",
        "",
        "| Exchange | Status | Loaded markets | Error |",
        "|---|---|---:|---|",
    ]
    for name, value in venue_results.items():
        summary_lines.append(
            f"| {name} | {value['status']} | {value.get('markets', '')} | {value.get('error', '')} |"
        )
    summary_lines += [
        "",
        "## Instrument coverage by exchange",
        "",
        "| Asset | Class | Exchange | Status | Matched symbol | Reason |",
        "|---|---|---|---|---|---|",
    ]
    for row in records:
        summary_lines.append(
            f"| {row['asset']} | {row['asset_class']} | {row['exchange']} | {row['status']} | "
            f"{row['matched_symbol']} | {row['reason'].replace('|', '/')} |"
        )
    (REPORT_DIR / "summary.md").write_text("\n".join(summary_lines) + "\n", encoding="utf-8")
    matches_count = sum(r["status"].startswith("MATCH") for r in records)
    missing_count = sum(r["status"] in {"NO_MATCH", "MISSING_CONFIGURED_SYMBOL"} for r in records)
    print(f"Configured instruments: {len(configured)}")
    print(f"Venue market lists loaded: {sum(1 for x in venue_results.values() if x['status'] == 'loaded')}/{len(EXCHANGES)}")
    print(f"Matched instrument/venue pairs: {matches_count}")
    print(f"Missing instrument/venue pairs: {missing_count}")
    print(f"Reports: {REPORT_DIR / 'market-audit.json'} and {REPORT_DIR / 'summary.md'}")
    # Audit is diagnostic: API outages should not conceal the report or cancel artifact upload.
    return 0


if __name__ == "__main__":
    sys.exit(main())
