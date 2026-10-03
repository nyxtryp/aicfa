#!/usr/bin/env python3
"""Verify the approved TradFi targets against live venue metadata.

This is a verification utility only. It does not alter the production universe,
does not create a scanner, and does not write native mappings. Production
mappings are added only after manual review of its compact output.
"""
from __future__ import annotations

import json
from pathlib import Path

import ccxt


ROOT = Path(__file__).resolve().parents[1]
TARGETS_PATH = ROOT / "config" / "tradfi_targets.json"
VENUES = ("bybit", "okx", "bitget", "mexc")


def _norm(value: str) -> str:
    return "".join(ch for ch in value.upper() if ch.isalnum())


def _target_aliases(target: dict) -> set[str]:
    asset = target["asset"].upper()
    base, quote = asset.split("/", 1)
    name = target["name"].upper()
    aliases = {base, _norm(base), _norm(name)}
    if target["category"] == "fx":
        aliases.update({
            _norm(asset),
            _norm(asset.replace("/", "")),
        })
    if base == "WTI":
        aliases.update({"CL", "WTIOIL", "OILWTI", "OIL"})
    elif base == "BRENT":
        aliases.update({"BZ", "BRENTOIL", "OILBRENT"})
    elif base == "NATGAS":
        aliases.update({"NG", "NGAS", "NATURALGAS"})
    elif base == "XAU":
        aliases.update({"GOLD", "XAUT"})
    elif base == "XAG":
        aliases.update({"SILVER"})
    elif base == "XCU":
        aliases.update({"COPPER"})
    elif base == "XPT":
        aliases.update({"PLATINUM"})
    elif base == "XPD":
        aliases.update({"PALLADIUM"})
    elif base == "SPX":
        aliases.update({"SP500", "SPX500"})
    elif base == "NDX":
        aliases.update({"NAS100", "NASDAQ100", "NASDAQ"})
    elif base == "DJIA":
        aliases.update({"DJ30", "US30", "DOW"})
    elif base == "RUT":
        aliases.update({"US2000", "RUSSELL2000"})
    elif base == "DAX":
        aliases.update({"DE40", "GER40"})
    elif base == "FTSE":
        aliases.update({"UK100", "FTSE100"})
    elif base == "CAC":
        aliases.update({"FR40", "CAC40"})
    elif base == "NIKKEI":
        aliases.update({"JP225", "JPN225", "NIKKEI225"})
    elif base == "STOXX50":
        aliases.update({"EU50", "STOXX50", "SX5E"})
    elif base == "VIX":
        aliases.update({"VOLATILITY", "VIX"})
    return {a for a in aliases if a}


def _matches(target: dict, market: dict) -> bool:
    symbol = str(market.get("symbol", ""))
    market_id = str(market.get("id", ""))
    base = str(market.get("base", ""))
    info = market.get("info") or {}
    raw = " ".join(
        [
            symbol,
            market_id,
            base,
            str(info.get("baseCoin", "")),
            str(info.get("instId", "")),
            str(info.get("instFamily", "")),
            str(info.get("uly", "")),
            str(info.get("displayName", "")),
            str(info.get("displayNameEn", "")),
        ]
    ).upper()
    aliases = _target_aliases(target)
    compact = _norm(raw)
    category = target["category"]

    if category == "fx":
        return any(alias in compact for alias in aliases) and (
            "USD" in compact or "USDT" in compact
        )

    # For equities/ETFs/indices/commodities, require a token boundary-like
    # match against the exchange symbol/id/base fields, avoiding generic
    # substring matches such as "ARM" inside unrelated crypto names.
    fields = [_norm(symbol), _norm(market_id), _norm(base)]
    return any(
        field == alias
        or field.startswith(alias + "USD")
        or field.startswith(alias + "USDT")
        or field.startswith(alias + "-USD")
        or field.startswith(alias + "-USDT")
        for field in fields
        for alias in aliases
    )


def _compact(market: dict) -> dict:
    info = market.get("info") or {}
    return {
        "symbol": market.get("symbol"),
        "id": market.get("id"),
        "type": market.get("type"),
        "spot": market.get("spot"),
        "swap": market.get("swap"),
        "future": market.get("future"),
        "base": market.get("base"),
        "quote": market.get("quote"),
        "settle": market.get("settle"),
        "active": market.get("active"),
        "state": info.get("state", info.get("status", info.get("symbolStatus"))),
        "contractType": info.get("contractType"),
        "instType": info.get("instType"),
        "symbolType": info.get("symbolType"),
        "isRwa": info.get("isRwa"),
    }


def main() -> None:
    targets = json.loads(TARGETS_PATH.read_text(encoding="utf-8"))["targets"]
    exchanges = {}
    for venue in VENUES:
        cls = getattr(ccxt, venue)
        exchange = cls({"enableRateLimit": True})
        print(f"LOADING {venue} ...", flush=True)
        markets = exchange.load_markets()
        exchanges[venue] = markets
        print(f"  markets={len(markets)}", flush=True)

    found = 0
    for target in targets:
        print(f"\n{target['asset']} | {target['name']} | {target['category']}")
        for venue in VENUES:
            matches = [
                _compact(market)
                for market in exchanges[venue].values()
                if _matches(target, market)
            ]
            if matches:
                found += 1
                print(f"  {venue}:")
                for item in matches[:12]:
                    print("    " + json.dumps(item, sort_keys=True))
                if len(matches) > 12:
                    print(f"    ... {len(matches) - 12} more")
            else:
                print(f"  {venue}: NONE")
    print(f"\nMATCH-VENUE-TARGETS={found}")


if __name__ == "__main__":
    main()
