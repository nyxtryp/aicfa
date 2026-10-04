from aicfa.data_requirements import (
    ContextNeed,
    DataKind,
    TimeframeRole,
    default_setup_requirements,
    requirements_for_concepts,
    TradingMode,
)


def test_setup_requirements_are_knowledge_driven():
    plan = default_setup_requirements("BTC")
    assert plan.asset == "BTC"
    assert DataKind.OHLCV in plan.data_kinds
    assert DataKind.TRADES not in plan.data_kinds
    assert DataKind.ORDER_BOOK not in plan.data_kinds
    assert ContextNeed.STRUCTURAL_ANCHORS in plan.context_needs
    assert ContextNeed.CROSS_TIMEFRAME_CONTEXT in plan.context_needs
    assert TimeframeRole.EXECUTION in plan.timeframe_roles
    assert TimeframeRole.HIGHER_STRUCTURE in plan.timeframe_roles
    assert TimeframeRole.LOWER_CONFIRMATION in plan.timeframe_roles
    assert len(plan.concepts) >= 8
    assert plan.required_timeframes == ("1m", "5m", "15m", "1h", "4h", "1d", "1w")


def test_mode_profiles_match_authoritative_timeframe_hierarchies():
    expected = {
        TradingMode.SCALPING: ("15m", "5m", "1m"),
        TradingMode.INTRADAY: ("4h", "1h", "15m", "5m"),
        TradingMode.SWING: ("1d", "4h", "1h"),
        TradingMode.POSITION: ("1w", "1d", "4h"),
    }
    for mode, timeframes in expected.items():
        plan = default_setup_requirements("BTC", mode=mode)
        assert plan.mode is mode
        assert plan.required_timeframes == timeframes



def test_derivatives_knowledge_expands_data_requirements():
    plan = requirements_for_concepts("BTC", ("derivatives.price_oi",))
    assert plan.data_kinds >= {
        DataKind.OHLCV,
        DataKind.FUNDING,
        DataKind.OPEN_INTEREST,
        DataKind.LIQUIDATIONS,
        DataKind.MARK_PRICE,
    }
    assert plan.needs(ContextNeed.POSITIONING_CONTEXT)


def test_requirements_do_not_encode_candle_depth():
    plan = default_setup_requirements("BTC")
    assert not hasattr(plan, "limit")
    assert not hasattr(plan, "candle_count")
    assert not hasattr(plan, "history_length")


def test_unknown_knowledge_concept_is_rejected():
    try:
        requirements_for_concepts("BTC", ("missing.concept",))
    except KeyError:
        pass
    else:
        raise AssertionError("unknown knowledge concept must not be silently ignored")


def test_microstructure_knowledge_maps_to_distinct_data_kinds():
    flow = requirements_for_concepts("BTC", ("microstructure.order_flow",))
    book = requirements_for_concepts("BTC", ("microstructure.order_book",))

    assert flow.data_kinds == {DataKind.OHLCV, DataKind.TRADES}
    assert book.data_kinds == {DataKind.OHLCV, DataKind.ORDER_BOOK}


def test_futures_setup_requires_all_seven_data_blocks():
    plan = default_setup_requirements("BTC", mode=TradingMode.INTRADAY, market_type="futures")
    assert plan.data_kinds == {
        DataKind.OHLCV,
        DataKind.TRADES,
        DataKind.ORDER_BOOK,
        DataKind.FUNDING,
        DataKind.OPEN_INTEREST,
        DataKind.LIQUIDATIONS,
        DataKind.MARK_PRICE,
    }
