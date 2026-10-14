"""Event-driven, deterministic multi-timeframe SMC candidate detection.

This module only consumes finalized candle windows supplied by the live data manager.
It deliberately refuses to invent tick sizes or accept a setup without exchange filters.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Mapping, Sequence

from app.market_data import ClosedCandle
from app.smc.engine import SMCAnalysis, analyze_smc
from app.smc.profiles import PROFILES, STOP_BUFFER_ATR_OVERRIDES, ProfileConfig


@dataclass(frozen=True, slots=True)
class SetupCandidate:
    key: str
    symbol: str
    profile: str
    direction: str
    status: str
    confirmation_time_ms: int
    confirmation_price: float
    stop_price: float
    targets: tuple[float, ...]
    score: int
    reasons: tuple[str, ...]
    zone: tuple[float, float]
    timeframe: str
    evidence: dict[str, bool | float] = field(default_factory=dict)
    atr: float = 0.0

    def as_dict(self) -> dict:
        result = asdict(self)
        result["targets"] = list(self.targets)
        result["reasons"] = list(self.reasons)
        result["zone"] = list(self.zone)
        return result


def _analysis(candles: Sequence[ClosedCandle], profile: ProfileConfig, timeframe: str) -> SMCAnalysis | None:
    if len(candles) < 40:
        return None
    return analyze_smc(
        [float(c.open) for c in candles],
        [float(c.high) for c in candles],
        [float(c.low) for c in candles],
        [float(c.close) for c in candles],
        [float(c.volume) for c in candles],
        [c.open_time_ms for c in candles],
        swing_left=profile.swing_left if timeframe in {profile.bias_timeframe, profile.zone_timeframe} else 2,
        swing_right=profile.swing_right if timeframe in {profile.bias_timeframe, profile.zone_timeframe} else 2,
    )


def scan_symbol(
    symbol: str,
    series_by_timeframe: Mapping[str, Sequence[ClosedCandle]],
    *,
    trigger_timeframe: str,
    diagnostics: dict[str, int] | None = None,
) -> list[SetupCandidate]:
    """Return only candidates whose confirmation is the newest candle on trigger TF.

    A candidate requires HTF structure bias, correct Premium/Discount, an active
    OB/FVG intersecting OTE, a directional liquidity sweep, and a later structure
    break on the profile confirmation timeframe. Candidate identity is stable
    for replay/dedup. Final ACCEPTED status is intentionally handled by the
    persistence/risk gate, not inferred here.
    """
    found: list[SetupCandidate] = []

    def count(reason: str) -> None:
        if diagnostics is not None:
            diagnostics[reason] = diagnostics.get(reason, 0) + 1

    for profile_name, profile in PROFILES.items():
        if trigger_timeframe != profile.confirmation_timeframe:
            continue
        count("profile_checks")
        trigger = tuple(series_by_timeframe.get(profile.confirmation_timeframe, ()))
        if not trigger:
            count("insufficient_history")
            continue
        # A scan is a snapshot at the newest closed trigger candle. Other
        # timeframes may advance independently; never let later candles leak
        # into bias, zone, or extra-confirmation analysis.
        confirmation_close_ms = trigger[-1].close_time_ms
        zone_series = tuple(c for c in series_by_timeframe.get(profile.zone_timeframe, ())
                            if c.close_time_ms <= confirmation_close_ms)
        bias_series = tuple(c for c in series_by_timeframe.get(profile.bias_timeframe, ())
                            if c.close_time_ms <= confirmation_close_ms)
        extra_series = tuple(c for c in series_by_timeframe.get(profile.extra_confirmation_timeframe, ())
                             if c.close_time_ms <= confirmation_close_ms) if profile.extra_confirmation_timeframe else ()
        if min(len(trigger), len(zone_series), len(bias_series)) < 40:
            count("insufficient_history")
            continue
        bias = _analysis(bias_series, profile, profile.bias_timeframe)
        zone = _analysis(zone_series, profile, profile.zone_timeframe)
        confirm = _analysis(trigger, profile, profile.confirmation_timeframe)
        extra = _analysis(extra_series, profile, profile.extra_confirmation_timeframe) if extra_series else None
        if bias is None or zone is None or confirm is None:
            count("analysis_unavailable")
            continue
        if not bias.structure_breaks:
            count("no_htf_structure_break")
            continue
        if zone.dealing_range is None:
            count("no_zone_dealing_range")
            continue
        if not confirm.sweeps:
            count("no_liquidity_sweep")
            continue
        if not confirm.structure_breaks:
            count("no_structure_break")
            continue

        latest_bias = bias.structure_breaks[-1]
        direction = "long" if latest_bias.direction == "bullish" else "short"
        required_zone = "discount" if direction == "long" else "premium"
        # TZ §6 defines Premium/Discount as part of the higher-timeframe bias,
        # not the zone-timeframe OTE calculation. Keep these independent: HTF
        # PD validates direction while the zone timeframe supplies the OTE leg.
        if bias.premium_discount != required_zone:
            count("premium_discount_mismatch")
            continue
        dr = zone.dealing_range
        ote_low, ote_high = sorted((float(dr.ote_lower), float(dr.ote_upper)))
        active_zones: list[tuple[float, float, str, int]] = []
        for block, state in zip(zone.order_blocks, zone.order_block_mitigation):
            if block.direction == latest_bias.direction and not state.mitigated and block.confirmation_index <= zone.as_of_index:
                active_zones.append((float(block.lower), float(block.upper), "OB", int(block.confirmation_index)))
        for gap, fill in zip(zone.fvg, zone.fvg_fill):
            if gap.direction == latest_bias.direction and not fill.fully_filled and gap.confirmation_index <= zone.as_of_index:
                active_zones.append((float(gap.lower), float(gap.upper), "FVG", int(gap.confirmation_index)))
        # TZ §6: price must enter the active zone before confirmation; it need
        # not still be inside the zone when the confirmation candle closes.
        # Only candles completed before confirmation are eligible, preventing
        # look-ahead and same-close-time ordering ambiguity.
        selected = next((z for z in reversed(active_zones)
                         if z[0] <= ote_high and z[1] >= ote_low
                         and any(
                             candle.close_time_ms < confirmation_close_ms
                             and index > z[3]
                             and float(candle.high) >= z[0]
                             and float(candle.low) <= z[1]
                             for index, candle in enumerate(zone_series)
                         )), None)
        if selected is None:
            count("no_active_zone_touched_in_ote_before_confirmation")
            continue
        count("active_zone_touched_in_ote")
        ob_zones = [(float(block.lower), float(block.upper)) for block, state in zip(zone.order_blocks, zone.order_block_mitigation)
                    if block.direction == latest_bias.direction and not state.mitigated]
        fvg_zones = [(float(gap.lower), float(gap.upper)) for gap, fill in zip(zone.fvg, zone.fvg_fill)
                     if gap.direction == latest_bias.direction and not fill.fully_filled]
        ob_fvg_overlap = any(a0 <= b1 and b0 <= a1 and max(a0, b0) <= ote_high and min(a1, b1) >= ote_low for a0, a1 in ob_zones for b0, b1 in fvg_zones)
        zone_bias_agreement = bool(zone.structure_breaks and zone.structure_breaks[-1].direction == latest_bias.direction)

        latest_trigger_break = confirm.structure_breaks[-1]
        if latest_trigger_break.candle_index != len(trigger) - 1:
            count("confirmation_break_not_latest")
            continue
        expected_break = "bullish" if direction == "long" else "bearish"
        if latest_trigger_break.direction != expected_break:
            count("confirmation_direction_mismatch")
            continue
        prior_sweeps = [s for s in confirm.sweeps if s.candle_index < latest_trigger_break.candle_index
                        and s.direction == expected_break]
        if not prior_sweeps:
            count("no_prior_directional_sweep")
            continue
        sweep = prior_sweeps[-1]
        sweep_candle = trigger[sweep.candle_index]
        stop_raw = float(sweep_candle.low if direction == "long" else sweep_candle.high)
        atr = confirm.atr[-1]
        if atr is None or atr <= 0:
            count("invalid_atr")
            continue
        stop_buffer_atr = max(profile.stop_buffer_atr, STOP_BUFFER_ATR_OVERRIDES.get(symbol, profile.stop_buffer_atr))
        stop = stop_raw - stop_buffer_atr * atr if direction == "long" else stop_raw + stop_buffer_atr * atr
        entry = float(trigger[-1].close)
        if (direction == "long" and stop >= entry) or (direction == "short" and stop <= entry):
            count("invalid_stop")
            continue

        liquidity_targets = sorted(
            {float(level.price) for level in confirm.liquidity_levels
             if (level.price > entry if direction == "long" else level.price < entry)},
            reverse=(direction == "short"),
        )
        if not liquidity_targets:
            count("no_target_liquidity")
            continue

        # TZ §6: TP1 is the nearest confirmed liquidity. TP2 is the next
        # available target; TP3 may be a confirmed major swing or range edge.
        # Do not require all three targets to be liquidity levels of the same
        # kind, and never move TP1 away from the nearest confirmed liquidity.
        targets = list(liquidity_targets[:3])
        last_target = targets[-1]
        swing_kind = "high" if direction == "long" else "low"
        swing_targets = sorted(
            {
                float(swing.price)
                for swing in getattr(confirm, "swings", ())
                if swing.kind == swing_kind
                and (swing.price > last_target if direction == "long" else swing.price < last_target)
            },
            reverse=(direction == "short"),
        )
        for target in swing_targets:
            if len(targets) >= 3:
                break
            if not any(abs(target - existing) <= max(abs(entry) * 1e-12, 1e-12) for existing in targets):
                targets.append(target)

        # The confirmation timeframe's dealing-range edge is the final fallback
        # for TP3, only when it lies beyond every target already selected.
        confirmation_range = confirm.dealing_range
        if len(targets) < 3 and confirmation_range is not None:
            edge = float(confirmation_range.high if direction == "long" else confirmation_range.low)
            beyond_last = edge > targets[-1] if direction == "long" else edge < targets[-1]
            if beyond_last and not any(abs(edge - existing) <= max(abs(entry) * 1e-12, 1e-12) for existing in targets):
                targets.append(edge)

        if len(targets) < 3:
            count("insufficient_confirmed_targets")
            continue
        tp1 = liquidity_targets[0]
        opposing_zones = [
            (float(block.lower), float(block.upper))
            for block, state in zip(confirm.order_blocks, confirm.order_block_mitigation)
            if block.direction != expected_break and not state.mitigated
        ] + [
            (float(gap.lower), float(gap.upper))
            for gap, fill in zip(confirm.fvg, confirm.fvg_fill)
            if gap.direction != expected_break and not fill.fully_filled
        ]
        clean_path = not any(
            (z_high > entry and z_low < tp1)
            if direction == "long"
            else (z_low < entry and z_high > tp1)
            for z_low, z_high in opposing_zones
        )
        risk = abs(entry - stop)
        reward = abs(tp1 - entry)
        if risk <= 0 or reward / risk < profile.min_rr:
            count("risk_reward_below_minimum")
            continue
        if profile.extra_confirmation_timeframe is not None:
            if extra is None or not extra.structure_breaks or extra.structure_breaks[-1].direction != expected_break or extra.structure_breaks[-1].candle_index != len(extra_series) - 1:
                count("missing_current_extra_confirmation")
                continue
            # A latest-index 1m break can still be stale when the 1m feed has
            # stopped advancing. Require the extra confirmation to be close in
            # time to the 5m confirmation, and never allow a future-dated bar.
            extra_age_ms = trigger[-1].close_time_ms - extra_series[-1].close_time_ms
            if extra_age_ms < 0 or extra_age_ms > 180_000:
                count("stale_extra_confirmation")
                continue

        average_volume = float(confirm.average_volume[-1] or 0)
        evidence = {
            "liquidity_sweep": True,
            "order_block_fvg_overlap": ob_fvg_overlap,
            "ote_overlap": True,
            "higher_timeframe_bias_aligned": True,
            "higher_timeframe_agreement": zone_bias_agreement,
            "confirmation_volume": float(trigger[-1].volume),
            "average_volume": average_volume,
            "clean_path_to_tp1": clean_path,
        }
        score = 2 + (2 if ob_fvg_overlap else 0) + 1 + 2 + (1 if zone_bias_agreement else 0) + (1 if clean_path else 0)
        if average_volume and float(trigger[-1].volume) > 1.5 * average_volume:
            score += 1
        if score < profile.score_threshold:
            count("score_below_threshold")
            continue
        # Include zone origin and candle timestamp to make replay idempotent.
        key = f"{symbol}:{profile_name}:{direction}:{selected[2]}:{zone_series[selected[3]].open_time_ms}:{trigger[-1].open_time_ms}"
        found.append(SetupCandidate(
            key=key, symbol=symbol, profile=profile_name, direction=direction,
            status="CANDIDATE", confirmation_time_ms=trigger[-1].close_time_ms,
            confirmation_price=entry, stop_price=stop,
            targets=tuple(targets[:3]), score=score,
            reasons=("htf_bias_aligned", "premium_discount_aligned", "active_zone_in_ote",
                     "liquidity_sweep", "confirmation_break", "rr_passed"),
            zone=(selected[0], selected[1]), timeframe=profile.confirmation_timeframe,
            evidence=evidence, atr=float(atr),
        ))
        count("candidate_generated")
    return found
