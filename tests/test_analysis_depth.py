from aicfa.analysis_depth import (
    ContextResolution,
    resolve_analysis_depth,
)
from aicfa.data_requirements import (
    ContextNeed,
    default_setup_requirements,
    requirements_for_concepts,
)


def test_depth_is_derived_from_feature_dependencies_not_provider_limit():
    plan = default_setup_requirements("BTCUSDT")
    resolved = resolve_analysis_depth(plan)

    assert tuple(resolved) == plan.required_timeframes
    assert {item.minimum_rows for item in resolved.values()} == {120, 180, 240}
    assert resolved["1w"].minimum_rows == 120
    assert resolved["1d"].minimum_rows == 180
    assert resolved["1h"].minimum_rows == 240
    assert all(item.minimum_rows < 1000 for item in resolved.values())
    assert all(
        any(dep.name == "feature.rolling" and dep.rows == 60 for dep in item.dependencies)
        for item in resolved.values()
    )


def test_setup_requirements_request_adaptive_event_and_active_state_context():
    plan = default_setup_requirements("BTCUSDT")
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
