"""Causal market-structure engine for AICFA.

Swing points are confirmed only after right subsequent candles. External and
internal structure are emitted at the first row where the information is
knowable. Protected levels are created only by a confirmed structural break.

MSS is deliberately displacement-aware: it is emitted only when a structural
shift/break is confirmed on the same row as a supplied causal displacement
event. Without a displacement frame, MSS remains zero rather than being a
renamed CHoCH.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _validate(df: pd.DataFrame) -> pd.DataFrame:
    required = ["timestamp", "open", "high", "low", "close"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    x = (
        df[required].copy()
        .sort_values("timestamp")
        .drop_duplicates("timestamp")
        .reset_index(drop=True)
    )
    for column in required[1:]:
        x[column] = x[column].astype(float)
    if (x["high"] < x[["open", "close"]].max(axis=1)).any():
        raise ValueError("Invalid OHLC: high is below open/close")
    if (x["low"] > x[["open", "close"]].min(axis=1)).any():
        raise ValueError("Invalid OHLC: low is above open/close")
    return x


def _swing_layer(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    *,
    left: int,
    right: int,
    equal_tolerance: float,
) -> dict[str, np.ndarray]:
    """Build one causal swing layer without protected-level semantics."""
    n = len(highs)
    result = {
        name: np.zeros(n, dtype="int8")
        for name in (
            "swing_high", "swing_low", "hh", "hl", "lh", "ll",
            "bos_up", "bos_down", "choch_up", "choch_down",
        )
    }
    result["swing_high_price"] = np.full(n, np.nan)
    result["swing_low_price"] = np.full(n, np.nan)
    # Explicit causal availability metadata. The pivot is at the pivot index,
    # but it is not usable until the confirmation index.
    result["swing_high_pivot_index"] = np.full(n, -1, dtype="int64")
    result["swing_low_pivot_index"] = np.full(n, -1, dtype="int64")
    result["swing_high_confirmation_index"] = np.full(n, -1, dtype="int64")
    result["swing_low_confirmation_index"] = np.full(n, -1, dtype="int64")
    # Structural-break provenance: the reference swing is recorded at the
    # confirmed row that made the level causally available. Event time remains
    # the current break row; pivot time is never used as availability time.
    result["bos_up_reference_pivot_index"] = np.full(n, -1, dtype="int64")
    result["bos_up_reference_confirmation_index"] = np.full(n, -1, dtype="int64")
    result["bos_down_reference_pivot_index"] = np.full(n, -1, dtype="int64")
    result["bos_down_reference_confirmation_index"] = np.full(n, -1, dtype="int64")
    result["structure_direction"] = np.zeros(n, dtype="int8")

    last_high: float | None = None
    last_low: float | None = None
    last_high_pivot_index = -1
    last_low_pivot_index = -1
    last_high_confirmation_index = -1
    last_low_confirmation_index = -1
    direction = 0
    broken_high: float | None = None
    broken_low: float | None = None

    for confirmation in range(left + right, n):
        pivot = confirmation - right
        high_window = highs[pivot - left : pivot + right + 1]
        low_window = lows[pivot - left : pivot + right + 1]
        is_high = (
            highs[pivot] >= np.max(high_window)
            and np.count_nonzero(high_window == highs[pivot]) == 1
        )
        is_low = (
            lows[pivot] <= np.min(low_window)
            and np.count_nonzero(low_window == lows[pivot]) == 1
        )

        if is_high:
            result["swing_high"][confirmation] = 1
            result["swing_high_price"][confirmation] = highs[pivot]
            result["swing_high_pivot_index"][confirmation] = pivot
            result["swing_high_confirmation_index"][confirmation] = confirmation
            if last_high is not None:
                if highs[pivot] > last_high * (1 + equal_tolerance):
                    result["hh"][confirmation] = 1
                elif highs[pivot] < last_high * (1 - equal_tolerance):
                    result["lh"][confirmation] = 1
            last_high = highs[pivot]
            last_high_pivot_index = pivot
            last_high_confirmation_index = confirmation

        if is_low:
            result["swing_low"][confirmation] = 1
            result["swing_low_price"][confirmation] = lows[pivot]
            result["swing_low_pivot_index"][confirmation] = pivot
            result["swing_low_confirmation_index"][confirmation] = confirmation
            if last_low is not None:
                if lows[pivot] > last_low * (1 + equal_tolerance):
                    result["hl"][confirmation] = 1
                elif lows[pivot] < last_low * (1 - equal_tolerance):
                    result["ll"][confirmation] = 1
            last_low = lows[pivot]
            last_low_pivot_index = pivot
            last_low_confirmation_index = confirmation

        if (
            last_high is not None
            and closes[confirmation] > last_high * (1 + equal_tolerance)
            and broken_high != last_high
        ):
            result["bos_up"][confirmation] = 1
            result["bos_up_reference_pivot_index"][confirmation] = last_high_pivot_index
            result["bos_up_reference_confirmation_index"][confirmation] = last_high_confirmation_index
            if direction < 0:
                result["choch_up"][confirmation] = 1
            direction = 1
            broken_high = last_high

        if (
            last_low is not None
            and closes[confirmation] < last_low * (1 - equal_tolerance)
            and broken_low != last_low
        ):
            result["bos_down"][confirmation] = 1
            result["bos_down_reference_pivot_index"][confirmation] = last_low_pivot_index
            result["bos_down_reference_confirmation_index"][confirmation] = last_low_confirmation_index
            if direction > 0:
                result["choch_down"][confirmation] = 1
            direction = -1
            broken_low = last_low

        result["structure_direction"][confirmation] = direction

    return result


def build_structure(
    df: pd.DataFrame,
    *,
    left: int = 2,
    right: int = 2,
    equal_tolerance: float = 0.0,
    internal_left: int = 1,
    internal_right: int = 1,
    displacement: pd.DataFrame | None = None,
    include_internal: bool = True,
    include_protected: bool = True,
    include_timestamps: bool = True,
) -> pd.DataFrame:
    """Build causal external/internal structure and protected levels.

    left/right define external sensitivity. The internal layer defaults to a
    tighter 1/1 swing confirmation and can be configured independently.

    A protected low is created on a bullish BOS from the latest confirmed
    external swing low known at that break. A protected high is created
    symmetrically on a bearish BOS. The level stays active until a later close
    breaks it in the opposite direction.

    When displacement is supplied, MSS is emitted only where CHoCH and a
    same-row directional displacement event coexist. Without displacement,
    MSS remains zero rather than becoming a renamed CHoCH.
    """
    if left < 1 or right < 1:
        raise ValueError("left and right must be positive")
    if internal_left < 1 or internal_right < 1:
        raise ValueError("internal_left and internal_right must be positive")
    if equal_tolerance < 0:
        raise ValueError("equal_tolerance must be non-negative")

    x = _validate(df)
    n = len(x)
    out = x.copy()
    highs = x["high"].to_numpy()
    lows = x["low"].to_numpy()
    closes = x["close"].to_numpy()

    external = _swing_layer(
        highs, lows, closes,
        left=left, right=right, equal_tolerance=equal_tolerance,
    )
    for name, values in external.items():
        out[name] = values

    if include_internal:
        internal = _swing_layer(
            highs, lows, closes,
            left=internal_left, right=internal_right, equal_tolerance=equal_tolerance,
        )
        for name, values in internal.items():
            out[f"internal_{name}"] = values

    out["mss_up"] = np.zeros(n, dtype="int8")
    out["mss_down"] = np.zeros(n, dtype="int8")
    if displacement is not None:
        if len(displacement) != n:
            raise ValueError("displacement length must match structure input")
        required = {"displacement_up", "displacement_down"}
        missing = required.difference(displacement.columns)
        if missing:
            raise ValueError(f"Missing displacement columns: {sorted(missing)}")
        disp_up = displacement["displacement_up"].to_numpy()
        disp_down = displacement["displacement_down"].to_numpy()
        out["mss_up"] = (
            (out["choch_up"].to_numpy() == 1) & (disp_up == 1)
        ).astype("int8")
        out["mss_down"] = (
            (out["choch_down"].to_numpy() == 1) & (disp_down == 1)
        ).astype("int8")

    if include_protected:
        out["protected_high_price"] = np.nan
        out["protected_low_price"] = np.nan
        out["protected_high_active"] = np.zeros(n, dtype="int8")
        out["protected_low_active"] = np.zeros(n, dtype="int8")
        out["protected_high_created"] = np.zeros(n, dtype="int8")
        out["protected_low_created"] = np.zeros(n, dtype="int8")
        out["protected_high_broken"] = np.zeros(n, dtype="int8")
        out["protected_low_broken"] = np.zeros(n, dtype="int8")

        confirmed_high: float | None = None
        confirmed_low: float | None = None
        protected_high: float | None = None
        protected_low: float | None = None
        protected_high_active = False
        protected_low_active = False

        for row in range(n):
            if external["swing_high"][row] == 1:
                confirmed_high = float(external["swing_high_price"][row])
            if external["swing_low"][row] == 1:
                confirmed_low = float(external["swing_low_price"][row])

            if external["bos_up"][row] == 1 and confirmed_low is not None:
                protected_low = confirmed_low
                protected_low_active = True
                out.at[row, "protected_low_created"] = 1

            if external["bos_down"][row] == 1 and confirmed_high is not None:
                protected_high = confirmed_high
                protected_high_active = True
                out.at[row, "protected_high_created"] = 1

            if protected_high_active and protected_high is not None:
                if row > 0 and closes[row] > protected_high:
                    protected_high_active = False
                    out.at[row, "protected_high_broken"] = 1

            if protected_low_active and protected_low is not None:
                if row > 0 and closes[row] < protected_low:
                    protected_low_active = False
                    out.at[row, "protected_low_broken"] = 1

            if protected_high is not None:
                out.at[row, "protected_high_price"] = protected_high
            if protected_low is not None:
                out.at[row, "protected_low_price"] = protected_low
            out.at[row, "protected_high_active"] = int(protected_high_active)
            out.at[row, "protected_low_active"] = int(protected_low_active)

    if include_timestamps:
        # Preserve both sides of the causal contract: pivot time is descriptive,
        # confirmation time is the first time downstream logic may use the swing.
        timestamps = x["timestamp"].to_numpy()
        for side in ("high", "low"):
            pivot_index = out[f"swing_{side}_pivot_index"].to_numpy()
            confirmation_index = out[f"swing_{side}_confirmation_index"].to_numpy()
            pivot_ts = np.full(n, np.nan)
            confirmation_ts = np.full(n, np.nan)
            known = pivot_index >= 0
            pivot_ts[known] = timestamps[pivot_index[known]]
            known_confirmation = confirmation_index >= 0
            confirmation_ts[known_confirmation] = timestamps[confirmation_index[known_confirmation]]
            out[f"swing_{side}_pivot_timestamp"] = pivot_ts
            out[f"swing_{side}_confirmation_timestamp"] = confirmation_ts

    return out
