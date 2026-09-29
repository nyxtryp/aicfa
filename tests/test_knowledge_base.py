from dataclasses import FrozenInstanceError

import pytest

from aicfa.knowledge_base import KNOWLEDGE_BASE_V1, KnowledgeEntry, find_knowledge, get_knowledge


def test_knowledge_base_covers_core_domains():
    domains = {entry.domain for entry in KNOWLEDGE_BASE_V1}
    assert len(KNOWLEDGE_BASE_V1) >= 10
    assert {"market_structure", "liquidity", "imbalance", "order_block", "premium_discount", "price_action", "wyckoff", "derivatives", "risk"} <= domains


def test_entries_are_structured_and_immutable():
    entry = get_knowledge("market_structure.bos")
    assert isinstance(entry, KnowledgeEntry)
    assert all((entry.definition, entry.observable_evidence, entry.relationships, entry.confirmations, entry.invalidations, entry.counterexamples, entry.setup_relevance))
    with pytest.raises(FrozenInstanceError):
        entry.name = "changed"


def test_lookup_uses_stable_id():
    assert get_knowledge("liquidity.sweep").name == "Liquidity Sweep"
    with pytest.raises(KeyError):
        get_knowledge("missing.entry")


def test_find_knowledge_filters_descriptive_knowledge_only():
    entries = find_knowledge(domain="market_structure", query="break")
    assert entries
    assert all(entry.domain == "market_structure" for entry in entries)
    assert all(not entry.id.endswith(".signal") for entry in entries)


def test_knowledge_has_no_market_history_dependency():
    for entry in KNOWLEDGE_BASE_V1:
        assert not hasattr(entry, "ohlcv")
        assert not hasattr(entry, "historical_outcomes")
