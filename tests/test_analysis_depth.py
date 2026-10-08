from aicfa.analysis_depth import (
    ContextResolution,
    resolve_analysis_depth,
)
from aicfa.data_requirements import (
    ContextNeed,
    default_setup_requirements,
    requirements_for_concepts,
)


def test_depth_follows_mode_timeframe_roles_not_provider_limit():
    expected_by_mode = {
        "scalping": {"15m": 300, "5m": 400, "1m": 500},
        "intraday": {"4h": 300, "1h": 400, "15m": 500, "5m": 500},
        "swing": {"1d": 300, "4h": 400, "1h": 500},
        "position": {"1w": 300, "1d": 400, "4h": 500},
    }

    for mode, expected in expected_by_mode.items():
        plan = default_setup_requirements("BTCUSDT", mode=mode)
        resolved = resolve_analysis_depth(plan)

        assert tuple(resolved) == plan.required_timeframes
        assert {timeframe: item.minimum_rows for timeframe, item in resolved.items()} == expected
        assert all(item.minimum_rows < 1000 for item in resolved.values())
        assert all(
            any(dep.name == "feature.rolling" and dep.rows == 60 for dep in item.dependencies)
            for item in resolved.values()
        )


def test_mode_less_plan_uses_conservative_depth_when_roles_are_ambiguous():
    plan = default_setup_requirements("BTCUSDT")
    resolved = resolve_analysis_depth(plan)

    # Without a trading mode, a timeframe-to-role mapping is ambiguous.
    # The resolver deliberately avoids guessing and uses the conservative depth.
    assert tuple(resolved) == plan.required_timeframes
    assert {item.minimum_rows for item in resolved.values()} == {500}


def test_setup_requirements_request_adaptive_event_and_active_state_context():
    plan = default_setup_requirements("BTCUSDT", mode="intraday")
    resolved = resolve_analysis_depth(plan)

    assert all(item.requires_event_context for item in resolved.values())
    assert all(item.requires_active_state for item in resolved.values())
    assert all(item.adaptive for item in resolved.values())
    assert all(
        ContextResolution.ACTIVE_LIFECYCLE_STATE in item.resolutions
        for item in resolved.values()
    )


def test_requirement_without_active_zones_does_not_invent_lifecycle_depth():
    plan = requirements_for_concepts("BTCUSDT", ("market_structure.bos",))
    resolved = resolve_analysis_depth(plan)

    assert all(item.requires_event_context for item in resolved.values())
    assert all(not item.requires_active_state for item in resolved.values())
    assert all(item.adaptive for item in resolved.values())


def test_empty_timeframe_selection_is_rejected():
    plan = default_setup_requirements("BTCUSDT")
    try:
        resolve_analysis_depth(plan, timeframes=())
    except ValueError as exc:
        assert str(exc) == "analysis depth requires at least one timeframe"
    else:
        raise AssertionError("expected ValueError")
