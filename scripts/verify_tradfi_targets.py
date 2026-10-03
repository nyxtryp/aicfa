#!/usr/bin/env python3
"""Verify the approved TradFi targets against live venue metadata.

Verification only: no production mappings or universe changes.
Output is intentionally compact: one best candidate per venue/target,
or MULTIPLE/ABSENT when the native metadata is ambiguous.
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
    base, _quote = asset.split("/", 1)
    name = target["name"].upper()
    aliases = {base, _norm(base), _norm(name)}
    if target["category"] == "fx":
        aliases.update({_norm(asset), _norm(asset.replace("/", ""))})
    special = {
        "WTI": {"CL", "WTIOIL", "OILWTI", "OIL"},
        "BRENT": {"BZ", "BRENTOIL", "OILBRENT"},
        "NATGAS": {"NG", "NGAS", "NATURALGAS"},
        "XAU": {"GOLD", "XAUT"},
        "XAG": {"SILVER"},
        "XCU": {"COPPER"},
        "XPT": {"PLATINUM"},
        "XPD": {"PALLADIUM"},
        "SPX": {"SP500", "SPX500"},
        "NDX": {"NAS100", "NASDAQ100", "NASDAQ"},
        "DJIA": {"DJ30", "US30", "DOW"},
        "RUT": {"US2000", "RUSSELL2000"},
        "DAX": {"DE40", "GER40"},
        "FTSE": {"UK100", "FTSE100"},
        "CAC": {"FR40", "CAC40"},
        "NIKKEI": {"JP225", "JPN225", "NIKKEI225"},
        "STOXX50": {"EU50", "STOXX50", "SX5E"},
        "VIX": {"VOLATILITY", "VIX"},
    }
    aliases.update(special.get(base, set()))
    return {a for a in aliases if a}


def _fields(market: dict) -> list[str]:
    info = market.get("info") or {}
    return [
        str(market.get("symbol", "")),
        str(market.get("id", "")),
        str(market.get("base", "")),
        str(info.get("baseCoin", "")),
        str(info.get("instId", "")),
        str(info.get("instFamily", "")),
        str(info.get("uly", "")),
        str(info.get("displayName", "")),
        str(info.get("displayNameEn", "")),
    ]


def _match_score(target: dict, market: dict) -> int:
    aliases = _target_aliases(target)
    fields = [_norm(value) for value in _fields(market) if value]
    category = target["category"]
    score = 0

    for field in fields:
        for alias in aliases:
            if field == alias:
                score = max(score, 100)
            elif field.startswith(alias + "USDT"):
                score = max(score, 90)
            elif field.startswith(alias + "USD"):
                score = max(score, 85)
            elif field.startswith(alias + "USDC"):
                score = max(score, 80)
            elif field.startswith(alias + "PERP"):
                score = max(score, 75)

    # FX must actually contain the two currencies in a native field.
    if category == "fx":
        base, quote = target["asset"].upper().split("/", 1)
        pair = _norm(base + quote)
        reverse = _norm(quote + base)
        if any(pair in field or reverse in field for field in fields):
            score = max(score, 100)

    return score


def _compact(market: dict) -> str:
    info = market.get("info") or {}
    symbol = market.get("symbol") or market.get("id")
    kind = market.get("type") or "-"
    contract = (
        info.get("contractType")
        or info.get("instType")
        or info.get("symbolType")
        or "-"
    )
    quote = market.get("quote") or "-"
    settle = market.get("settle") or "-"
    active = market.get("active")
    return (
        f"{symbol} | type={kind} | contract={contract} | "
        f"quote={quote} | settle={settle} | active={active}"
    )


def main() -> None:
    targets = json.loads(TARGETS_PATH.read_text(encoding="utf-8"))["targets"]
    exchanges = {}

    for venue in VENUES:
        exchange = getattr(ccxt, venue)({"enableRateLimit": True})
        print(f"LOADING {venue} ...", flush=True)
        markets = exchange.load_markets()
        exchanges[venue] = markets
        print(f"  markets={len(markets)}", flush=True)

    confirmed = multiple = absent = 0

    for target in targets:
        per_venue = []
        for venue in VENUES:
            scored = []
            for market in exchanges[venue].values():
                score = _match_score(target, market)
                if score:
                    scored.append((score, _compact(market), market))

            # Prefer the strongest exact/native-looking candidates.
            scored.sort(key=lambda item: (-item[0], item[1]))
            top = scored[:5]

            # Deduplicate by native symbol/id.
            unique = []
            seen = set()
            for score, compact, market in top:
                key = str(market.get("id") or market.get("symbol"))
                if key not in seen:
                    seen.add(key)
                    unique.append((score, compact))

            if not unique:
                status = "ABSENT"
                absent += 1
            elif len(unique) == 1:
                status = f"CONFIRMED {unique[0][1]}"
                confirmed += 1
            else:
                candidates = " || ".join(item[1] for item in unique[:3])
                status = f"MULTIPLE {candidates}"
                multiple += 1

            per_venue.append(f"{venue}={status}")

        print(f"{target['asset']} | {target['name']} | " + " | ".join(per_venue))

    print(
        f"\nSUMMARY confirmed={confirmed} multiple={multiple} absent={absent}"
    )


if __name__ == "__main__":
    main()
