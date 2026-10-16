"""Event-driven, deterministic multi-timeframe SMC candidate detection.

This module only consumes finalized candle windows supplied by the live data manager.
It deliberately refuses to invent tick sizes or accept a setup without exchange filters.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Mapping, Sequence

from app.market_data import ClosedCandle
from app.smc.liquidity import is_level_near_zone
from app.smc.engine import SMCAnalysis, analyze_smc
from app.smc.ranges import find_dealing_range, premium_discount
from app.smc.profiles import PROFILES, STOP_BUFFER_ATR_OVERRIDES, ProfileConfig
from app.smc.structure import find_confirmed_swings
from app.smc.breaks import detect_structure_breaks


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


def _recent_internal_structure_direction(candles: Sequence[ClosedCandle], *, max_age: int = 2) -> str | None:
    """Return a fresh 1-left/1-right internal BOS/CHoCH direction, without look-ahead.

    This is an independent, PAC-inspired internal-structure confluence, not
    LuxAlgo's proprietary implementation. Swing points are usable only after
    their right-hand confirmation candle closes.
    """
    if len(candles) < 5:
        return None
    highs = [float(c.high) for c in candles]
    lows = [float(c.low) for c in candles]
    closes = [float(c.close) for c in candles]
    internal_swings = find_confirmed_swings(highs, lows, left=1, right=1)
    events = detect_structure_breaks(closes, internal_swings)
    if not events:
        return None
    latest = events[-1]
    age = len(candles) - 1 - int(latest.candle_index)
    if age < 0 or age > max_age:
        return None
    return latest.direction


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
        if not confirm.sweeps:
            count("no_liquidity_sweep")
            continue
        if not confirm.structure_breaks:
            count("no_structure_break")
            continue

        latest_bias = bias.structure_breaks[-1]
        # Both HTF Premium/Discount and zone-TF OTE must use an impulse aligned
        # with the current HTF structure bias. The default latest leg can be a
        # countertrend pullback and invert the Premium/Discount classification.
        # Premium/Discount is evaluated at the current causal HTF snapshot,
        # not frozen at the candle where the latest BOS/CHoCH happened.
        # Select the newest confirmed impulse aligned with that structure bias;
        # find_dealing_range skips any newer countertrend pullback and excludes
        # swings whose right-hand confirmation candles have not closed yet.
        bias_dr = find_dealing_range(
            bias.swings,
            as_of_index=bias.as_of_index,
            direction=latest_bias.direction,
        )
        if bias_dr is None:
            count("no_directional_bias_dealing_range")
            continue
        bias_pd = premium_discount(float(bias_series[-1].close), bias_dr)
        dr = find_dealing_range(
            zone.swings,
            as_of_index=zone.as_of_index,
            direction=latest_bias.direction,
        )
        if dr is None:
            count("no_directional_zone_dealing_range")
            continue
        direction = "long" if latest_bias.direction == "bullish" else "short"
        required_zone = "discount" if direction == "long" else "premium"
        # Premium/Discount is SMC location confluence, not a standalone signal.
        # Structure determines bias; sweep + confirmed trigger break and an active
        # zone in OTE determine the setup. Do not hard-veto an otherwise valid setup
        # solely because price is in the other half of a broad HTF range.
        pd_aligned = bias_pd == required_zone
        if not pd_aligned:
            count("premium_discount_mismatch")
        ote_low, ote_high = sorted((float(dr.ote_lower), float(dr.ote_upper)))
        active_zones: list[tuple[float, float, str, int]] = []
        for block, state in zip(zone.order_blocks, zone.order_block_mitigation):
            if block.direction == latest_bias.direction and not state.mitigated and block.confirmation_index <= zone.as_of_index:
                active_zones.append((float(block.lower), float(block.upper), "OB", int(block.candle_index)))
        for gap, fill in zip(zone.fvg, zone.fvg_fill):
            if gap.direction == latest_bias.direction and not fill.fully_filled and gap.confirmation_index <= zone.as_of_index:
                active_zones.append((float(gap.lower), float(gap.upper), "FVG", int(gap.confirmation_index)))
        # For OBs, candle_index is the source candle where the zone formed; confirmation_index
        # is the later structure-break candle that makes the OB identifiable. FVG confirmation_index
        # is its third/forming candle. Sort and timestamp both by the actual zone-formation index.
        active_zones.sort(key=lambda item: (item[3], item[2]))
        # The latest structure break may be followed by a short, bounded
        # confirmation window. Requiring the BOS to be on the exact last candle
        # misses valid closed-candle setups when the feed and HTF bars close at
        # slightly different times. Entry is still evaluated at the current
        # trigger close, never retroactively at the BOS candle.
        latest_trigger_break = confirm.structure_breaks[-1]
        break_index = int(latest_trigger_break.candle_index)
        break_age = len(trigger) - 1 - break_index
        if break_age < 0 or break_age > 2:
            count("confirmation_break_not_recent")
            continue
        expected_break = "bullish" if direction == "long" else "bearish"
        if latest_trigger_break.direction != expected_break:
            count("confirmation_direction_mismatch")
            continue
        internal_direction = _recent_internal_structure_direction(trigger)
        internal_structure_confirmed = internal_direction is not None
        internal_structure_aligned = internal_direction == expected_break
        if internal_structure_confirmed and not internal_structure_aligned:
            count("internal_structure_conflict")
        elif internal_structure_aligned:
            count("internal_structure_aligned")
        break_close_ms = trigger[break_index].close_time_ms

        # SMC sequence: liquidity is swept, structure breaks with displacement,
        # then price returns to a fresh OB/FVG in OTE. Requiring the retest
        # BEFORE the break reverses that sequence and suppresses valid setups.
        # Choose the newest eligible zone that is actually retested after the
        # confirming break; entry is still evaluated at the newest closed candle.
        selected = None
        for candidate_zone in reversed(active_zones):
            if not (candidate_zone[0] <= ote_high and candidate_zone[1] >= ote_low):
                continue
            zone_index = candidate_zone[3]
            if not 0 <= zone_index < len(zone_series):
                continue
            zone_created_ms = zone_series[zone_index].close_time_ms
            touched = any(
                index > break_index
                and candle.close_time_ms > max(zone_created_ms, break_close_ms)
                and float(candle.high) >= candidate_zone[0]
                and float(candle.low) <= candidate_zone[1]
                for index, candle in enumerate(trigger)
            )
            if touched:
                selected = candidate_zone
                break
        if selected is None:
            count("no_active_zone_retested_after_confirmation")
            continue
        count("active_zone_retested_after_confirmation")

        # The directional liquidity sweep must precede the structure break and
        # be close to the selected zone. Do not require the sweep to occur after
        # the zone's formation: a sweep commonly creates the displacement that
        # identifies the OB/FVG used for the subsequent retest.
        zone_created_ms = zone_series[selected[3]].close_time_ms
        zone_atr = zone.atr[selected[3]] if selected[3] < len(zone.atr) else None
        if zone_atr is None or zone_atr <= 0:
            count("invalid_zone_atr")
            continue
        prior_sweeps = [
            sweep_event for sweep_event in confirm.sweeps
            if sweep_event.candle_index < break_index
            and sweep_event.direction == expected_break
            and is_level_near_zone(
                float(sweep_event.level), selected[0], selected[1], float(zone_atr),
                max_distance_atr=1.0,
            )
        ]
        if not prior_sweeps:
            count("no_prior_directional_sweep_near_zone")
            continue
        sweep = prior_sweeps[-1]
        ob_zones = [(float(block.lower), float(block.upper)) for block, state in zip(zone.order_blocks, zone.order_block_mitigation)
                    if block.direction == latest_bias.direction and not state.mitigated]
        fvg_zones = [(float(gap.lower), float(gap.upper)) for gap, fill in zip(zone.fvg, zone.fvg_fill)
                     if gap.direction == latest_bias.direction and not fill.fully_filled]
        ob_fvg_overlap = any(a0 <= b1 and b0 <= a1 and max(a0, b0) <= ote_high and min(a1, b1) >= ote_low for a0, a1 in ob_zones for b0, b1 in fvg_zones)
        zone_bias_agreement = bool(zone.structure_breaks and zone.structure_breaks[-1].direction == latest_bias.direction)

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

        # TP1 is required for the RR check; TP2/TP3 are optional structural
        # extensions. Never reject an otherwise valid setup just because the
        # market structure does not provide farther confirmed targets.
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
            if extra is None or not extra.structure_breaks:
                count("missing_current_extra_confirmation")
                continue
            extra_break = extra.structure_breaks[-1]
            extra_break_age = len(extra_series) - 1 - int(extra_break.candle_index)
            if extra_break.direction != expected_break or extra_break_age < 0 or extra_break_age > 2:
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
            "premium_discount_aligned": pd_aligned,
            "higher_timeframe_agreement": zone_bias_agreement,
            "confirmation_volume": float(trigger[-1].volume),
            "average_volume": average_volume,
            "clean_path_to_tp1": clean_path,
            "internal_structure_confirmed": internal_structure_confirmed,
            "internal_structure_aligned": internal_structure_aligned,
        }
        score = 2 + (2 if ob_fvg_overlap else 0) + 1 + 2 + (1 if zone_bias_agreement else 0) + (1 if clean_path else 0) + (1 if pd_aligned else 0)
        # PAC-style internal structure is a confluence, not a new hard gate:
        # reward a fresh aligned micro-break and penalize a fresh opposing one.
        if internal_structure_aligned:
            score += 1
        elif internal_structure_confirmed:
            score -= 1
        if average_volume and float(trigger[-1].volume) > 1.5 * average_volume:
            score += 1
        # The UI and strategy threshold are defined on a ten-point scale.
        # Multiple simultaneous confluences cannot inflate the displayed score.
        score = min(10, score)
        if score < profile.score_threshold:
            count("score_below_threshold")
            continue
        # Include zone origin and candle timestamp to make replay idempotent.
        key = f"{symbol}:{profile_name}:{direction}:{selected[2]}:{zone_series[selected[3]].open_time_ms}:{trigger[break_index].open_time_ms}"
        found.append(SetupCandidate(
            key=key, symbol=symbol, profile=profile_name, direction=direction,
            status="CANDIDATE", confirmation_time_ms=trigger[-1].close_time_ms,
            confirmation_price=entry, stop_price=stop,
            targets=tuple(targets[:3]), score=score,
            reasons=("htf_bias_aligned",
                     *(("premium_discount_aligned",) if pd_aligned else ("premium_discount_not_aligned_confluence_only",)),
                     "active_zone_in_ote", "liquidity_sweep", "confirmation_break",
                     *(("internal_structure_aligned",) if internal_structure_aligned else
                       (("internal_structure_conflict",) if internal_structure_confirmed else ())),
                     "rr_passed"),
            zone=(selected[0], selected[1]), timeframe=profile.confirmation_timeframe,
            evidence=evidence, atr=float(atr),
        ))
        count("candidate_generated")
    return found
