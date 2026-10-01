"""Deterministic, CPU-only chart visualization for AICFA setups.

The visualization layer consumes already-computed OHLCV/features and the
MTF SETUP ENGINE result. It does not calculate or alter trading decisions.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import numpy as np
import pandas as pd

from aicfa.setup_analysis import SetupAssessment, SetupCandidate, SetupDecision


@dataclass(frozen=True)
class ChartLevel:
    value: float
    timeframe: str
    source: str
    kind: str


@dataclass(frozen=True)
class ChartZone:
    low: float
    high: float
    timeframe: str
    source: str
    kind: str


@dataclass(frozen=True)
class ChartEvent:
    index: int
    price: float
    label: str
    kind: str


@dataclass(frozen=True)
class ChartModel:
    asset: str
    timeframe: str
    candles: pd.DataFrame
    current_price: float
    direction: str | None
    scenario: str | None
    confirmation: tuple[str, ...]
    source_timeframes: tuple[str, ...]
    levels: tuple[ChartLevel, ...]
    zones: tuple[ChartZone, ...]
    events: tuple[ChartEvent, ...]
    structure_labels: tuple[ChartEvent, ...]
    status: str


def _as_frame(frame: pd.DataFrame) -> pd.DataFrame:
    required = ("timestamp", "open", "high", "low", "close", "volume")
    missing = [c for c in required if c not in frame.columns]
    if missing:
        raise ValueError(f"missing chart columns: {missing}")
    out = frame.copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True)
    for column in required[1:]:
        out[column] = pd.to_numeric(out[column], errors="coerce")
    out = out.dropna().sort_values("timestamp").drop_duplicates("timestamp")
    if out.empty:
        raise ValueError("chart frame is empty")
    if (out["high"] < out[["open", "close"]].max(axis=1)).any():
        raise ValueError("invalid OHLC: high is below open/close")
    if (out["low"] > out[["open", "close"]].min(axis=1)).any():
        raise ValueError("invalid OHLC: low is above open/close")
    return out.reset_index(drop=True)


def _latest_value(row: pd.Series, *columns: str) -> float | None:
    for column in columns:
        if column not in row.index:
            continue
        value = pd.to_numeric(pd.Series([row[column]]), errors="coerce").iloc[0]
        if pd.notna(value):
            return float(value)
    return None


def _structure_labels(frame: pd.DataFrame) -> tuple[ChartEvent, ...]:
    events: list[ChartEvent] = []
    pairs = (
        ("hh", "HH"), ("hl", "HL"), ("lh", "LH"), ("ll", "LL"),
        ("internal_hh", "iHH"), ("internal_hl", "iHL"),
        ("internal_lh", "iLH"), ("internal_ll", "iLL"),
    )
    for i, row in frame.iterrows():
        for column, label in pairs:
            if column not in row.index or row[column] != 1:
                continue
            price = _latest_value(row, "high" if "H" in label.upper() else "low")
            if price is not None:
                events.append(ChartEvent(i, price, label, "structure"))
    return tuple(events)


def _feature_events(frame: pd.DataFrame) -> tuple[ChartEvent, ...]:
    pairs = (
        ("bos_up", "BOS↑"), ("bos_down", "BOS↓"),
        ("choch_up", "CHoCH↑"), ("choch_down", "CHoCH↓"),
        ("mss_up", "MSS↑"), ("mss_down", "MSS↓"),
        ("sweep_high", "SWEEP↑"), ("sweep_low", "SWEEP↓"),
        ("displacement_up", "DISP↑"), ("displacement_down", "DISP↓"),
    )
    events: list[ChartEvent] = []
    for i, row in frame.iterrows():
        for column, label in pairs:
            if column not in row.index or row[column] != 1:
                continue
            price = _latest_value(row, "high" if "↑" in label else "low", "close")
            if price is not None:
                events.append(ChartEvent(i, price, label, "event"))
    return tuple(events)


def _feature_zones(frame: pd.DataFrame) -> tuple[ChartZone, ...]:
    zones: list[ChartZone] = []
    zone_defs = (
        ("fvg_bullish", "fvg_bullish_low", "fvg_bullish_high", "FVG bullish"),
        ("fvg_bearish", "fvg_bearish_low", "fvg_bearish_high", "FVG bearish"),
        ("order_block_bullish", "order_block_bullish_low", "order_block_bullish_high", "OB bullish"),
        ("order_block_bearish", "order_block_bearish_low", "order_block_bearish_high", "OB bearish"),
    )
    for i, row in frame.iterrows():
        for flag, low_col, high_col, label in zone_defs:
            if flag not in row.index or row[flag] != 1:
                continue
            low = _latest_value(row, low_col)
            high = _latest_value(row, high_col)
            if low is not None and high is not None and low <= high:
                zones.append(ChartZone(low, high, "", label, "zone"))
    return tuple(zones)


def _candidate_levels(candidate: SetupCandidate) -> tuple[ChartLevel, ...]:
    levels: list[ChartLevel] = []
    for index, level in enumerate(candidate.entry_zone):
        levels.append(
            ChartLevel(
                level.value,
                level.timeframe,
                level.source,
                f"ENTRY {'LOW' if index == 0 else 'HIGH'}",
            )
        )
    if candidate.invalidation_level is not None:
        level = candidate.invalidation_level
        levels.append(ChartLevel(level.value, level.timeframe, level.source, "INVALIDATION"))
    for index, level in enumerate(candidate.target_levels[:2], start=1):
        levels.append(ChartLevel(level.value, level.timeframe, level.source, f"TP{index}"))
    return tuple(levels)


def build_chart_model(
    frames: Mapping[str, pd.DataFrame],
    setup: SetupAssessment,
    *,
    asset: str = "UNKNOWN",
    max_candles: int = 240,
) -> ChartModel:
    """Build render-ready chart state without recalculating setup geometry."""
    if not frames:
        raise ValueError("frames must not be empty")
    if max_candles < 20:
        raise ValueError("max_candles must be at least 20")

    candidate = tuple(setup.candidates)[0] if setup.candidates else None
    entry_tf = candidate.entry_zone[0].timeframe if candidate and candidate.entry_zone else None
    timeframe = entry_tf or ("15m" if "15m" in frames else next(iter(frames)))
    if timeframe not in frames:
        raise ValueError(f"entry timeframe {timeframe!r} is not present in frames")

    frame = _as_frame(frames[timeframe]).tail(max_candles).reset_index(drop=True)
    current_price = float(frame.iloc[-1]["close"])

    if candidate is not None:
        levels = _candidate_levels(candidate)
        direction = candidate.direction
        scenario = candidate.scenario
        confirmation = candidate.confirmation_timeframes
        source_timeframes = candidate.source_timeframes
        status = "SETUP"
    else:
        levels = ()
        direction = None
        scenario = None
        confirmation = ()
        source_timeframes = ()
        status = "WAIT" if setup.decision == SetupDecision.WAIT else "NO TRADE"

    zones = _feature_zones(frame)
    events = _feature_events(frame)
    structure = _structure_labels(frame)

    last = frame.iloc[-1]
    range_high = _latest_value(last, "premium_discount_range_high", "dealing_range_high")
    range_low = _latest_value(last, "premium_discount_range_low", "dealing_range_low")
    if range_low is not None and range_high is not None and range_low <= range_high:
        zones = zones + (
            ChartZone(range_low, range_high, timeframe, "Premium/Discount dealing range", "range"),
        )

    return ChartModel(
        asset=asset,
        timeframe=timeframe,
        candles=frame,
        current_price=current_price,
        direction=direction,
        scenario=scenario,
        confirmation=tuple(confirmation),
        source_timeframes=tuple(source_timeframes),
        levels=levels,
        zones=zones,
        events=events,
        structure_labels=structure,
        status=status,
    )


def render_chart(model: ChartModel, output_path: str | Path) -> Path:
    """Render one deterministic PNG using CPU-only matplotlib."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = model.candles

    fig = plt.figure(figsize=(18, 10), dpi=140)
    grid = fig.add_gridspec(5, 1, height_ratios=(4, 1, 0.05, 0.05, 0.05), hspace=0.02)
    ax = fig.add_subplot(grid[0])
    vol = fig.add_subplot(grid[1], sharex=ax)

    width = 0.68
    for i, row in frame.iterrows():
        open_, high, low, close = map(
            float, (row["open"], row["high"], row["low"], row["close"])
        )
        ax.vlines(i, low, high, linewidth=0.8)
        bottom = min(open_, close)
        height = max(abs(close - open_), 1e-12)
        ax.add_patch(
            Rectangle(
                (i - width / 2, bottom),
                width,
                height,
                fill=False,
                linewidth=0.8,
            )
        )
        vol.vlines(i, 0, float(row["volume"]), linewidth=1.0)

    ax.axhline(model.current_price, linestyle="--", linewidth=0.9)
    ax.text(len(frame) - 1, model.current_price, f"  {model.current_price:g}", va="center")

    for zone in model.zones:
        ax.axhspan(zone.low, zone.high, alpha=0.12 if zone.kind == "range" else 0.18)
        if zone.source:
            ax.text(0, zone.high, zone.source, fontsize=7, va="bottom")

    level_style = {
        "INVALIDATION": ("--", 1.4),
        "TP1": (":", 1.2),
        "TP2": (":", 1.2),
        "ENTRY LOW": ("-", 1.5),
        "ENTRY HIGH": ("-", 1.5),
    }
    for level in model.levels:
        linestyle, linewidth = level_style.get(level.kind, ("-", 1.0))
        ax.axhline(level.value, linestyle=linestyle, linewidth=linewidth)
        ax.text(
            len(frame) - 1,
            level.value,
            f"  {level.kind} {level.value:g} [{level.timeframe} {level.source}]",
            va="center",
            fontsize=8,
        )

    for event in model.events:
        ax.annotate(
            event.label,
            (event.index, event.price),
            xytext=(0, 8 if "↑" in event.label else -12),
            textcoords="offset points",
            ha="center",
            fontsize=7,
        )
    for event in model.structure_labels:
        ax.annotate(
            event.label,
            (event.index, event.price),
            xytext=(0, 7 if event.price <= model.current_price else -9),
            textcoords="offset points",
            ha="center",
            fontsize=7,
        )

    ax.set_title(
        f"AICFA — {model.asset} {model.timeframe} — {model.status}"
        + (f" — {model.direction.upper()} {model.scenario}" if model.direction else "")
    )
    ax.set_ylabel("Price")
    vol.set_ylabel("Volume")
    vol.set_xlabel("Candle")
    ax.grid(alpha=0.18)
    vol.grid(alpha=0.12)
    fig.text(
        0.01,
        0.01,
        "Source TFs: "
        + (", ".join(model.source_timeframes) if model.source_timeframes else "none")
        + " | Confirmation: "
        + (", ".join(model.confirmation) if model.confirmation else "none"),
        fontsize=8,
    )
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    return path
