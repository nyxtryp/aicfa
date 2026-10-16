"""Causal historical replay for evaluating SMC profiles after costs.

This module never places orders. It uses the production scanner on each historical
closed-candle prefix, enters no earlier than the next candle open, and resolves
ambiguous stop/target bars conservatively (stop first).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from math import isfinite
from typing import Mapping, Sequence

from app.market_data import ClosedCandle
from app.smc.profiles import PROFILES, ProfileConfig
from app.smc.scanner import SetupCandidate, scan_symbol


@dataclass(frozen=True, slots=True)
class BacktestConfig:
    margin_usd: float = 5.0
    leverage: float = 10.0
    fee_rate_per_side: float = 0.0005
    slippage_bps_per_side: float = 2.0
    score_threshold: int | None = None
    min_rr: float | None = None
    stop_buffer_atr: float | None = None
    max_candles: int = 500

    def validate(self) -> None:
        numeric = (self.margin_usd, self.leverage, self.fee_rate_per_side,
                   self.slippage_bps_per_side)
        if any(not isfinite(float(v)) for v in numeric):
            raise ValueError("backtest numeric settings must be finite")
        if self.margin_usd <= 0 or self.leverage <= 0:
            raise ValueError("margin_usd and leverage must be > 0")
        if self.fee_rate_per_side < 0 or self.slippage_bps_per_side < 0:
            raise ValueError("fees and slippage cannot be negative")
        if self.score_threshold is not None and not 0 <= self.score_threshold <= 10:
            raise ValueError("score_threshold must be between 0 and 10")
        if self.min_rr is not None and self.min_rr <= 0:
            raise ValueError("min_rr must be > 0")
        if self.stop_buffer_atr is not None and self.stop_buffer_atr <= 0:
            raise ValueError("stop_buffer_atr must be > 0")
        if self.max_candles < 40:
            raise ValueError("max_candles must be at least 40")


@dataclass(frozen=True, slots=True)
class TradeResult:
    key: str
    symbol: str
    profile: str
    direction: str
    signal_time_ms: int
    entry_time_ms: int
    exit_time_ms: int
    entry_price: float
    stop_price: float
    targets: tuple[float, ...]
    exit_reason: str
    gross_pnl_usd: float
    fees_usd: float
    net_pnl_usd: float
    net_r: float
    margin_return_pct: float
    complete: bool

    def as_dict(self) -> dict:
        result = asdict(self)
        result["targets"] = list(self.targets)
        return result


def _adverse_price(price: float, direction: str, is_entry: bool, bps: float) -> float:
    slip = bps / 10_000.0
    # A long buys high/sells low; a short sells low/buys high.
    sign = 1.0 if direction == "long" else -1.0
    return price * (1.0 + sign * slip if is_entry else 1.0 - sign * slip)


def _net_rr(direction: str, entry: float, stop: float, target: float) -> float:
    risk = entry - stop if direction == "long" else stop - entry
    reward = target - entry if direction == "long" else entry - target
    return reward / risk if risk > 0 and reward > 0 else 0.0


def _simulate(
    candidate: SetupCandidate,
    trigger: Sequence[ClosedCandle],
    signal_index: int,
    profile: ProfileConfig,
    config: BacktestConfig,
    end_index: int,
) -> TradeResult | None:
    entry_index = signal_index + 1
    if entry_index > end_index or entry_index >= len(trigger) or not candidate.targets:
        return None
    direction = candidate.direction
    sign = 1.0 if direction == "long" else -1.0
    raw_entry = float(trigger[entry_index].open)
    entry = _adverse_price(raw_entry, direction, True, config.slippage_bps_per_side)
    stop = float(candidate.stop_price)
    targets = tuple(float(x) for x in candidate.targets[:3])
    min_rr = profile.min_rr
    if _net_rr(direction, entry, stop, targets[0]) < min_rr:
        return None

    notional = config.margin_usd * config.leverage
    units = notional / entry
    entry_fee = notional * config.fee_rate_per_side
    fees = entry_fee
    gross_pnl = 0.0
    remaining = 1.0
    weights = (1.0,) if len(targets) == 1 else ((0.5, 0.5) if len(targets) == 2 else (0.5, 0.3, 0.2))
    next_target = 0
    be_active = False
    risk_usd = notional * abs(entry - stop) / entry
    if risk_usd <= 0:
        return None

    exit_reason = "END_OF_DATA"
    exit_time = int(trigger[end_index].close_time_ms)
    complete = False
    last_index = min(end_index, len(trigger) - 1)
    lifetime_ms = profile.lifetime_hours * 3_600_000

    for i in range(entry_index, last_index + 1):
        candle = trigger[i]
        active_stop = entry if be_active else stop
        stop_hit = (float(candle.low) <= active_stop if direction == "long"
                    else float(candle.high) >= active_stop)
        target_hit = (float(candle.high) >= targets[next_target] if direction == "long"
                      else float(candle.low) <= targets[next_target])
        # With OHLC-only data, if stop and a target are both touched, assume stop first.
        if stop_hit:
            exit_price = _adverse_price(active_stop, direction, False, config.slippage_bps_per_side)
            gross_pnl += units * remaining * sign * (exit_price - entry)
            fees += notional * remaining * config.fee_rate_per_side
            remaining = 0.0
            exit_reason = "BE" if be_active else "SL"
            exit_time = int(candle.close_time_ms)
            complete = True
            break

        if target_hit:
            fraction = min(remaining, weights[next_target])
            target_price = _adverse_price(targets[next_target], direction, False, config.slippage_bps_per_side)
            gross_pnl += units * fraction * sign * (target_price - entry)
            fees += notional * fraction * config.fee_rate_per_side
            remaining -= fraction
            reached_first = next_target == 0
            next_target += 1
            if reached_first and remaining > 1e-9:
                # Breakeven is active only from the next candle to avoid assuming
                # the unknown intrabar path after TP1.
                be_active = True
            if remaining <= 1e-9:
                remaining = 0.0
                exit_reason = "TP" + str(next_target)
                exit_time = int(candle.close_time_ms)
                complete = True
                break
            # If multiple targets lie inside one OHLC bar, process them in price order;
            # the next loop iteration remains the same bar only when a further target
            # is clearly beyond the previous target in the direction of travel.
            while next_target < len(targets):
                further_hit = (float(candle.high) >= targets[next_target] if direction == "long"
                               else float(candle.low) <= targets[next_target])
                if not further_hit:
                    break
                fraction = min(remaining, weights[next_target])
                target_price = _adverse_price(targets[next_target], direction, False, config.slippage_bps_per_side)
                gross_pnl += units * fraction * sign * (target_price - entry)
                fees += notional * fraction * config.fee_rate_per_side
                remaining -= fraction
                next_target += 1
                if remaining <= 1e-9:
                    remaining = 0.0
                    exit_reason = "TP" + str(next_target)
                    exit_time = int(candle.close_time_ms)
                    complete = True
                    break
            if complete:
                break

        if int(candle.close_time_ms) - int(trigger[entry_index].open_time_ms) >= lifetime_ms:
            exit_price = _adverse_price(float(candle.close), direction, False, config.slippage_bps_per_side)
            gross_pnl += units * remaining * sign * (exit_price - entry)
            fees += notional * remaining * config.fee_rate_per_side
            remaining = 0.0
            exit_reason = "EXPIRED"
            exit_time = int(candle.close_time_ms)
            complete = True
            break

    if remaining > 1e-9 and last_index >= entry_index:
        close = _adverse_price(float(trigger[last_index].close), direction, False, config.slippage_bps_per_side)
        gross_pnl += units * remaining * sign * (close - entry)
        fees += notional * remaining * config.fee_rate_per_side

    net = gross_pnl - fees
    return TradeResult(
        key=candidate.key, symbol=candidate.symbol, profile=candidate.profile,
        direction=direction, signal_time_ms=int(candidate.confirmation_time_ms),
        entry_time_ms=int(trigger[entry_index].open_time_ms), exit_time_ms=exit_time,
        entry_price=entry, stop_price=stop, targets=targets, exit_reason=exit_reason,
        gross_pnl_usd=gross_pnl, fees_usd=fees, net_pnl_usd=net,
        net_r=net / risk_usd, margin_return_pct=100.0 * net / config.margin_usd,
        complete=complete,
    )


def summarize(trades: Sequence[TradeResult], *, margin_usd: float = 5.0, include_incomplete: bool = False) -> dict:
    sample = [t for t in trades if include_incomplete or t.complete]
    wins = [t for t in sample if t.net_pnl_usd > 0]
    losses = [t for t in sample if t.net_pnl_usd < 0]
    gross_profit = sum(t.net_pnl_usd for t in wins)
    gross_loss = -sum(t.net_pnl_usd for t in losses)
    equity = peak = max_drawdown = 0.0
    loss_streak = current_streak = 0
    for trade in sorted(sample, key=lambda t: t.exit_time_ms):
        equity += trade.net_pnl_usd
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
        if trade.net_pnl_usd < 0:
            current_streak += 1
            loss_streak = max(loss_streak, current_streak)
        else:
            current_streak = 0
    count = len(sample)
    return {
        "trades": count,
        "complete_trades": sum(t.complete for t in sample),
        "win_rate_pct": 100.0 * len(wins) / count if count else 0.0,
        "net_profit_usd": sum(t.net_pnl_usd for t in sample),
        "net_r": sum(t.net_r for t in sample),
        "expectancy_r": sum(t.net_r for t in sample) / count if count else 0.0,
        "profit_factor": gross_profit / gross_loss if gross_loss else (None if gross_profit else 0.0),
        "average_win_usd": sum(t.net_pnl_usd for t in wins) / len(wins) if wins else 0.0,
        "average_loss_usd": sum(t.net_pnl_usd for t in losses) / len(losses) if losses else 0.0,
        "max_drawdown_usd": max_drawdown,
        "max_consecutive_losses": loss_streak,
        "fees_usd": sum(t.fees_usd for t in sample),
        "margin_return_pct": 100.0 * sum(t.net_pnl_usd for t in sample) / margin_usd if sample and margin_usd > 0 else 0.0,
    }


def run_backtest(
    symbol: str,
    series_by_timeframe: Mapping[str, Sequence[ClosedCandle]],
    *,
    trigger_timeframe: str,
    profile_name: str,
    config: BacktestConfig = BacktestConfig(),
    start_index: int = 40,
    end_index: int | None = None,
) -> dict:
    """Replay one symbol/profile causally; return metrics and trade-level audit rows."""
    config.validate()
    if profile_name not in PROFILES:
        raise ValueError("profile_name must be 'scalp' or 'intraday'")
    if trigger_timeframe != PROFILES[profile_name].confirmation_timeframe:
        raise ValueError("trigger_timeframe does not match profile")
    trigger = tuple(series_by_timeframe.get(trigger_timeframe, ()))
    if len(trigger) < 41:
        return {"metrics": summarize((), margin_usd=config.margin_usd), "trades": [], "reason": "insufficient_history"}
    end = min(len(trigger) - 1, end_index if end_index is not None else len(trigger) - 1)
    if start_index < 40 or start_index > end:
        raise ValueError("start_index must be >= 40 and <= end_index")
    base_profile = PROFILES[profile_name]
    profile = replace(
        base_profile,
        score_threshold=(config.score_threshold if config.score_threshold is not None else base_profile.score_threshold),
        min_rr=(config.min_rr if config.min_rr is not None else base_profile.min_rr),
        stop_buffer_atr=(config.stop_buffer_atr if config.stop_buffer_atr is not None else base_profile.stop_buffer_atr),
    )
    trades: list[TradeResult] = []
    seen_keys: set[str] = set()
    i = start_index
    while i < end:
        timestamp = int(trigger[i].close_time_ms)
        snapshot: dict[str, tuple[ClosedCandle, ...]] = {}
        for timeframe, rows in series_by_timeframe.items():
            closed = tuple(c for c in rows if c.close_time_ms <= timestamp)
            snapshot[timeframe] = closed[-config.max_candles:]
        prefix_trigger = snapshot.get(trigger_timeframe, ())
        if len(prefix_trigger) < 40:
            i += 1
            continue
        diagnostics: dict[str, int] = {}
        candidates = scan_symbol(
            symbol, snapshot, trigger_timeframe=trigger_timeframe,
            diagnostics=diagnostics, profiles={profile_name: profile},
        )
        candidate = next((c for c in candidates if c.key not in seen_keys), None)
        if candidate is None:
            i += 1
            continue
        seen_keys.add(candidate.key)
        # scanner snapshot may be capped at 500, so map its final candle back to
        # the source index by timestamp before simulating future bars.
        signal_time = int(prefix_trigger[-1].open_time_ms)
        absolute_signal_index = next(
            (j for j, row in enumerate(trigger) if row.open_time_ms == signal_time),
            i,
        )
        result = _simulate(candidate, trigger, absolute_signal_index, profile, config, end)
        if result is not None:
            trades.append(result)
            # Avoid overlapping positions for the same symbol/profile.
            if result.complete:
                exit_index = next(
                    (j for j, row in enumerate(trigger) if row.close_time_ms == result.exit_time_ms),
                    absolute_signal_index,
                )
                i = max(i + 1, exit_index + 1)
                continue
        i += 1
    metrics = summarize(trades, margin_usd=config.margin_usd)
    metrics["incomplete_trades_excluded"] = sum(not t.complete for t in trades)
    return {
        "symbol": symbol, "profile": profile_name, "trigger_timeframe": trigger_timeframe,
        "settings": asdict(config), "metrics": metrics,
        "trades": [trade.as_dict() for trade in trades],
    }


def parameter_grid() -> tuple[BacktestConfig, ...]:
    """Small, predeclared grid; selection must be made on train/validation only."""
    return tuple(
        BacktestConfig(score_threshold=score, min_rr=rr, stop_buffer_atr=buffer)
        for score in (6, 7, 8)
        for rr in (1.5, 2.0, 2.5)
        for buffer in (0.3, 0.4, 0.5)
    )
