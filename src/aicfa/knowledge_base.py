from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class KnowledgeEntry:
    id: str
    domain: str
    name: str
    definition: str
    observable_evidence: tuple[str, ...]
    relationships: tuple[str, ...]
    confirmations: tuple[str, ...]
    invalidations: tuple[str, ...]
    counterexamples: tuple[str, ...]
    setup_relevance: str


def _entry(id: str, domain: str, name: str, definition: str, evidence: Iterable[str], relationships: Iterable[str], confirmations: Iterable[str], invalidations: Iterable[str], counterexamples: Iterable[str], relevance: str) -> KnowledgeEntry:
    return KnowledgeEntry(id, domain, name, definition, tuple(evidence), tuple(relationships), tuple(confirmations), tuple(invalidations), tuple(counterexamples), relevance)


KNOWLEDGE_BASE_V1: tuple[KnowledgeEntry, ...] = (
    _entry("market_structure.bos", "market_structure", "Break of Structure", "A confirmed break of a structurally relevant swing point in the direction of the active structural leg.", ("swing highs and lows", "candle close beyond relevant swing", "displacement"), ("market_structure.hh_hl_lh_ll", "liquidity.sweep", "displacement", "order_block"), ("decisive close", "follow-through displacement"), ("wick-only break", "temporary sweep"), ("range breakout can fail", "lower-timeframe break can conflict with higher timeframe"), "Supports continuation or transition analysis; never an entry by itself."),
    _entry("market_structure.choch", "market_structure", "Change of Character", "A structural break that warns that prior directional behavior may be changing.", ("failure of prior sequence", "protected swing break", "reaction after liquidity event"), ("liquidity.sweep", "displacement", "market_structure.bos"), ("break with follow-through", "rejection of prior state"), ("isolated wick", "break without follow-through"), ("local CHoCH may only be a correction inside larger trend",), "Transition hypothesis requiring context and confirmation."),
    _entry("liquidity.sweep", "liquidity", "Liquidity Sweep", "A move through an identifiable liquidity area followed by evidence of rejection or repricing away from that area.", ("equal highs/lows", "previous highs/lows", "wick through liquidity", "close back through level"), ("market_structure.choch", "displacement", "order_block", "imbalance.fvg"), ("rejection", "displacement away", "structural confirmation"), ("sustained acceptance beyond level",), ("not every breakout is a sweep", "wick alone does not establish intent"), "Potential trap/reversal or continuation context after liquidity is consumed."),
    _entry("imbalance.fvg", "imbalance", "Fair Value Gap", "A three-candle price inefficiency where neighboring ranges leave a non-overlapping price area.", ("three-candle displacement", "non-overlapping ranges", "gap between candle extremes"), ("displacement", "liquidity.sweep", "order_block", "premium_discount.dealing_range"), ("strong displacement", "alignment with broader structure"), ("decisive acceptance through zone",), ("FVG does not guarantee retracement", "multiple FVGs have different relevance"), "Potential reaction or mitigation zone; direction requires context."),
    _entry("order_block.bullish", "order_block", "Bullish Order Block", "A contextual price area associated with the last meaningful bearish candle before bullish displacement that changes or continues structure.", ("candidate candle before displacement", "bullish expansion", "structural relevance"), ("displacement", "market_structure.bos", "liquidity.sweep", "imbalance.fvg"), ("displacement from zone", "strong reaction at zone"), ("decisive invalidation through zone", "structural context breaks"), ("not every opposite candle is an order block",), "Potential demand/reaction area validated by structure and response."),
    _entry("premium_discount.dealing_range", "premium_discount", "Premium / Discount", "A framework dividing a defined dealing range into premium, equilibrium and discount relative to structural endpoints.", ("range high/low", "equilibrium", "current price location"), ("market_structure", "liquidity", "order_block", "imbalance.fvg"), ("structurally meaningful range", "direction consistent with context"), ("range becomes invalid", "major structural expansion"), ("premium is not automatically short", "discount is not automatically long"), "Provides location and context, not standalone direction."),
    _entry("price_action.rejection", "price_action", "Price Rejection", "A visible failure to sustain trade beyond a level or zone, evidenced by candle behavior and subsequent response.", ("wick/close relationship", "follow-through", "reaction at known level"), ("liquidity.sweep", "order_block", "imbalance.fvg", "volume"), ("rejection at meaningful context", "subsequent displacement"), ("continued acceptance beyond level",), ("single rejection candle can be noise", "rejection without location is weak evidence"), "Can confirm a zone reaction but is not a standalone signal."),
    _entry("wyckoff.spring", "wyckoff", "Spring", "A Wyckoff-style failure below range support followed by recovery into the range, interpreted only within range context.", ("defined trading range", "support violation", "reclaim into range"), ("liquidity.sweep", "market_structure.choch", "volume", "price_action.rejection"), ("reclaim plus sustained response",), ("acceptance below range", "continued markdown"), ("support break and reclaim is not automatically a Spring",), "Can strengthen a range-reversal hypothesis when full context is visible."),
    _entry("derivatives.price_oi", "derivatives", "Price / Open Interest Relationship", "A contextual relationship between price movement and changes in open interest; it describes positioning behavior rather than predicting direction by itself.", ("price change", "OI change", "time sequence"), ("market_structure", "liquidity", "funding", "liquidations"), ("relationship persists", "alignment with visible price behavior"), ("missing or stale OI", "insufficient evidence"), ("same combination can mean different things in different contexts",), "Adds positioning context to a price hypothesis; never creates a signal alone."),
    _entry("risk.invalidation", "risk", "Setup Invalidation", "A clearly defined condition showing that evidence supporting a proposed setup is no longer valid.", ("structural break", "zone failure", "acceptance beyond invalidation"), ("market_structure", "liquidity", "order_block", "imbalance.fvg"), ("defined before entry", "observable condition"), ("explicitly abandon thesis once condition occurs",), ("moving invalidation to preserve a thesis", "arbitrary invalidation"), "Every actionable setup must state what makes the thesis wrong; otherwise WAIT is preferred."),
)


def get_knowledge(entry_id: str) -> KnowledgeEntry:
    for entry in KNOWLEDGE_BASE_V1:
        if entry.id == entry_id:
            return entry
    raise KeyError(entry_id)


def find_knowledge(*, domain: str | None = None, query: str | None = None) -> tuple[KnowledgeEntry, ...]:
    normalized = query.lower().strip() if query else None
    results = []
    for entry in KNOWLEDGE_BASE_V1:
        if domain is not None and entry.domain != domain:
            continue
        if normalized is not None:
            haystack = " ".join((entry.id, entry.domain, entry.name, entry.definition, *entry.observable_evidence, *entry.relationships)).lower()
            if normalized not in haystack:
                continue
        results.append(entry)
    return tuple(results)
