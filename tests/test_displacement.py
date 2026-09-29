import numpy as np
import pandas as pd
import pytest

from aicfa.displacement import build_displacement


def frame(opens, highs, lows, closes, volumes):
    n = len(closes)
    return pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=n, freq="min", tz="UTC").astype("int64") // 10**6,
        "open": np.asarray(opens, dtype=float),
        "high": np.asarray(highs, dtype=float),
        "low": np.asarray(lows, dtype=float),
        "close": np.asarray(closes, dtype=float),
        "volume": np.asarray(volumes, dtype=float),
    })


def baseline_frame(n=21):
    close = np.full(n, 100.5)
    return frame(
        np.full(n, 100.0),
        np.full(n, 101.0),
        np.full(n, 99.0),
        close,
        np.full(n, 10.0),
    )


def test_displacement_requires_multiple_factors():
    df = baseline_frame()
    df.loc[20, ["open", "high", "low", "close", "volume"]] = [100.0, 104.5, 99.5, 104.0, 20.0]

    r = build_displacement(df)
    assert r.loc[20, "displacement_range_expansion"] >= 1.5
    assert r.loc[20, "displacement_body_expansion"] >= 1.5
    assert r.loc[20, "displacement_close_efficiency"] >= 0.6
    assert r.loc[20, "displacement_relative_volume"] >= 1.2
    assert r.loc[20, "impulsive_close_up"] == 1
    assert r.loc[20, "displacement_up"] == 1
    assert r.loc[20, "displacement_down"] == 0


def test_large_candle_without_volume_is_not_displacement():
    df = baseline_frame()
    df.loc[20, ["open", "high", "low", "close", "volume"]] = [100.0, 104.5, 99.5, 104.0, 10.0]

    r = build_displacement(df)
    assert r.loc[20, "displacement_range_expansion"] >= 1.5
    assert r.loc[20, "displacement_body_expansion"] >= 1.5
    assert r.loc[20, "displacement_close_efficiency"] >= 0.6
    assert r.loc[20, "displacement_relative_volume"] < 1.2
    assert r.loc[20, "displacement_up"] == 0


def test_downward_displacement_is_directional():
    df = baseline_frame()
    df.loc[20, ["open", "high", "low", "close", "volume"]] = [100.5, 101.0, 96.0, 97.0, 20.0]

    r = build_displacement(df)
    assert r.loc[20, "displacement_down"] == 1
    assert r.loc[20, "displacement_up"] == 0
    assert r.loc[20, "directional_displacement"] < 0


def test_displacement_references_are_strictly_past_only():
    df = baseline_frame(40)
    altered = df.copy()
    altered.loc[30:, ["high", "low", "close", "volume"]] *= [1000, 0.001, 500, 100]

    a = build_displacement(df)
    b = build_displacement(altered)
    pd.testing.assert_frame_equal(a.iloc[:30], b.iloc[:30], check_dtype=False)


def test_displacement_bos_relationship_is_causal():
    opens = [100, 100, 102, 101, 101, 103.5]
    highs = [101, 103, 105, 103, 102, 108]
    lows = [99, 99, 101, 100, 100, 103]
    closes = [100, 102, 104, 101, 101, 107.5]
    volumes = [10, 10, 10, 10, 10, 20]

    r = build_displacement(
        frame(opens, highs, lows, closes, volumes),
        baseline=5,
    )
    assert r.loc[5, "displacement_up"] == 1
    assert r.loc[5, "displacement_bos_up"] == 1
    assert r.loc[5, "displacement_bos_down"] == 0


def test_invalid_parameters():
    df = baseline_frame()
    with pytest.raises(ValueError):
        build_displacement(df, baseline=1)
    with pytest.raises(ValueError):
        build_displacement(df, relative_volume_threshold=0)
    with pytest.raises(ValueError):
        build_displacement(df, impulsive_close_threshold=1.0)
    with pytest.raises(ValueError):
        build_displacement(frame(
            [1, 1], [2, 2], [0, 0], [1, 1], [-1, 1]
        ))
