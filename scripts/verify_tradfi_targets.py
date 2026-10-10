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


def _market_kind(market: dict) -> str:
    info = market.get("info") or {}
    market_type = str(market.get("type") or "").lower()
    contract = str(
        info.get("contractType")
        or info.get("instType")
        or info.get("symbolType")
        or ""
    ).lower()
    if market_type == "swap" or contract in {"swap", "perpetual", "linearperpetual", "inverseperpetual"}:
        return "perpetual"
    if market_type == "future" or contract in {"future", "futures", "delivery"}:
        return "future"
    if market_type in {"spot", "margin"}:
        return "spot"
    return market_type or "other"


def _is_active_derivative(market: dict) -> bool:
    return bool(market.get("active")) and _market_kind(market) in {"perpetual", "future"}


def _rwa_flag(market: dict) -> str:
    info = market.get("info") or {}
    value = info.get("isRwa")
    if value is None:
        return "-"
    return str(value)


def _compact(market: dict) -> str:
    info = market.get("info") or {}
    symbol = market.get("symbol") or market.get("id")
    return (
        f"{symbol} | {_market_kind(market)} | "
        f"quote={market.get('quote') or '-'} | settle={market.get('settle') or '-'} | "
        f"active={market.get('active')} | isRwa={_rwa_flag(market)}"
    )


def _candidate_rank(target: dict, market: dict, score: int) -> tuple:
    kind = _market_kind(market)
    quote = str(market.get("quote") or "").upper()
    settle = str(market.get("settle") or "").upper()
    # Prefer perpetuals and USDT settlement, then futures and USD/USDC.
    kind_rank = {"perpetual": 30, "future": 20}.get(kind, 0)
    settle_rank = {"USDT": 6, "USDC": 5, "USD": 4}.get(settle, 0)
    quote_rank = {"USDT": 3, "USDC": 2, "USD": 1}.get(quote, 0)
    return (-score, -kind_rank, -settle_rank, -quote_rank, str(market.get("symbol") or market.get("id") or ""))


def _verify_target(target: dict, markets: dict) -> tuple[str, str | None]:
    candidates = []
    for market in markets.values():
        score = _match_score(target, market)
        if score <= 0 or not _is_active_derivative(market):
            continue
        candidates.append((score, market))

    if not candidates:
        return "ABSENT", None

    candidates.sort(key=lambda item: _candidate_rank(target, item[1], item[0]))
    best_score, best = candidates[0]

    # A weak alias hit is never promoted to production automatically.
    if best_score < 90:
        return "REVIEW", _compact(best)

    # RWA metadata, when explicitly exposed, requires human review.
    if _rwa_flag(best).lower() in {"true", "1", "yes"}:
        return "REVIEW", _compact(best)

    return "ACCEPT", _compact(best)


def main() -> None:
    targets = json.loads(TARGETS_PATH.read_text(encoding="utf-8"))["targets"]
    exchanges = {}
    venue_errors = {}

    for venue in VENUES:
        print(f"LOADING {venue} ...", flush=True)
        try:
            exchange = getattr(ccxt, venue)({"enableRateLimit": True, "timeout": 15000})
            markets = exchange.load_markets()
        except Exception as exc:
            exchanges[venue] = None
            venue_errors[venue] = f"{type(exc).__name__}: {str(exc)[:240]}"
            print(f"  UNAVAILABLE: {venue_errors[venue]}", flush=True)
            continue
        exchanges[venue] = markets
        print(f"  markets={len(markets)}", flush=True)

    accepted = review = absent = unavailable = 0

    for target in targets:
        per_venue = []
        for venue in VENUES:
            if exchanges[venue] is None:
                unavailable += 1
                per_venue.append(f"{venue}=UNAVAILABLE ({venue_errors[venue]})")
                continue
            status, candidate = _verify_target(target, exchanges[venue])
            if status == "ACCEPT":
                accepted += 1
                per_venue.append(f"{venue}=ACCEPT {candidate}")
            elif status == "REVIEW":
                review += 1
                per_venue.append(f"{venue}=REVIEW {candidate}")
            else:
                absent += 1
                per_venue.append(f"{venue}=ABSENT")
        print(f"{target['asset']} | {target['name']} | " + " | ".join(per_venue))

    print(
        f"\\nSUMMARY accept={accepted} review={review} absent={absent} "
        f"unavailable={unavailable}"
    )


if __name__ == "__main__":
    main()
