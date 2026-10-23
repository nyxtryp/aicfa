"""PAC-inspired scanner replacing the legacy hard-gated SMC candidate pipeline.

Independent implementation using public market-structure concepts; not LuxAlgo source.
Closed-candle snapshots only. Confluences contribute to score rather than each becoming
a mandatory veto, so the scanner can surface qualified candidates in trending markets.
"""
from __future__ import annotations

from typing import Mapping, Sequence

from app.market_data import ClosedCandle
from app.smc.scanner import SetupCandidate, _analysis
from app.smc.profiles import PROFILES, STOP_BUFFER_ATR_OVERRIDES
from app.smc.ranges import find_dealing_range, premium_discount


def scan_symbol(
    symbol: str,
    series_by_timeframe: Mapping[str, Sequence[ClosedCandle]],
    *,
    trigger_timeframe: str,
    diagnostics: dict[str, int] | None = None,
) -> list[SetupCandidate]:
    """Detect PAC-style structure/zone/retest candidates on closed candles."""
    found: list[SetupCandidate] = []

    def count(reason: str) -> None:
        if diagnostics is not None:
            diagnostics[reason] = diagnostics.get(reason, 0) + 1

    for profile_name, profile in PROFILES.items():
        if trigger_timeframe != profile.confirmation_timeframe:
            continue
        count("profile_checks")
        trigger = tuple(series_by_timeframe.get(profile.confirmation_timeframe, ()))
        if len(trigger) < 40:
            count("insufficient_trigger_history")
            continue
        snapshot_ms = trigger[-1].close_time_ms
        zone_series = tuple(c for c in series_by_timeframe.get(profile.zone_timeframe, ())
                            if c.close_time_ms <= snapshot_ms)
        bias_series = tuple(c for c in series_by_timeframe.get(profile.bias_timeframe, ())
                            if c.close_time_ms <= snapshot_ms)
        extra_series = tuple(c for c in series_by_timeframe.get(profile.extra_confirmation_timeframe, ())
                             if c.close_time_ms <= snapshot_ms) if profile.extra_confirmation_timeframe else ()
        if min(len(zone_series), len(bias_series)) < 40:
            count("insufficient_mtf_history")
            continue

        bias = _analysis(bias_series, profile, profile.bias_timeframe)
        zone = _analysis(zone_series, profile, profile.zone_timeframe)
        confirm = _analysis(trigger, profile, profile.confirmation_timeframe)
        extra = _analysis(extra_series, profile, profile.extra_confirmation_timeframe) if extra_series else None
        if bias is None or zone is None or confirm is None or not bias.structure_breaks:
            count("no_htf_bias")
            continue

        htf_break = bias.structure_breaks[-1]
        expected = htf_break.direction
        direction = "long" if expected == "bullish" else "short"
        entry = float(trigger[-1].close)
        atr = confirm.atr[-1]
        if atr is None or atr <= 0:
            count("invalid_atr")
            continue

        trigger_break = confirm.structure_breaks[-1] if confirm.structure_breaks else None
        trigger_break_age = len(trigger) - 1 - int(trigger_break.candle_index) if trigger_break else 999
        # Keep the legacy scoring window, but allow the causal SCALP sequence
        # to start from a slightly older 5m break when a fresh retest/reaction
        # follows it. A same-direction pre-break sweep is optional score confluence.
        trigger_aligned = bool(trigger_break and trigger_break.direction == expected and 0 <= trigger_break_age <= 3)
        scalp_trigger_aligned = bool(trigger_break and trigger_break.direction == expected and 0 <= trigger_break_age <= 12)
        causal_trigger_aligned = scalp_trigger_aligned if profile_name == "scalp" else trigger_aligned
        trigger_break_close_ms = (
            int(trigger[int(trigger_break.candle_index)].close_time_ms)
            if causal_trigger_aligned and trigger_break is not None
            and 0 <= int(trigger_break.candle_index) < len(trigger) else None
        )

        # SCALP requires aligned 5m BOS/CHoCH -> post-trigger retest -> 1m reaction.
        # A same-direction sweep before the trigger is optional score confluence.
        if profile_name == "scalp" and not scalp_trigger_aligned:
            count("no_recent_trigger_structure")
            continue
        sweep_before_trigger = bool(
            causal_trigger_aligned and any(
                s.direction == expected
                and 0 <= int(s.candle_index) < int(trigger_break.candle_index)
                and 0 <= len(trigger) - 1 - int(s.candle_index) <= 12
                for s in confirm.sweeps
            )
        )
        # Sweep is optional confluence, not a hard rejection gate.
        # When present, it only scores if same-direction and before the trigger.

        # Keep source and confirmation indices separate: an OB is not actionable
        # until its confirmation candle has closed.
        zones: list[tuple[float, float, str, int, int]] = []
        for block, state in zip(zone.order_blocks, zone.order_block_mitigation):
            source_index = int(block.candle_index)
            confirmation_index = int(block.confirmation_index)
            if (block.direction == expected and not state.mitigated
                    and 0 <= source_index < len(zone_series)
                    and 0 <= confirmation_index < len(zone_series)
                    and confirmation_index <= zone.as_of_index):
                zones.append((float(block.lower), float(block.upper), "OB", source_index, confirmation_index))
        for gap, fill in zip(zone.fvg, zone.fvg_fill):
            source_index = int(gap.confirmation_index)
            confirmation_index = int(gap.confirmation_index)
            if (gap.direction == expected and not fill.fully_filled
                    and 0 <= source_index < len(zone_series)
                    and confirmation_index <= zone.as_of_index):
                zones.append((float(gap.lower), float(gap.upper), "FVG", source_index, confirmation_index))
        if not zones:
            count("no_directional_ob_fvg")
            continue

        if profile_name == "scalp":
            # SCALP requires a retest after both zone confirmation and the
            # aligned 5m BOS/CHoCH. Evaluate every zone before choosing one so
            # an untouched nearer zone cannot hide a valid retested zone.
            retested_zones: list[tuple[tuple[float, float, str, int, int], int]] = []
            for candidate_zone in zones:
                candidate_low, candidate_high, _, _, candidate_confirmation_index = candidate_zone
                candidate_confirmation_ms = int(zone_series[candidate_confirmation_index].close_time_ms)
                if candidate_confirmation_ms > snapshot_ms:
                    continue
                causal_after_ms = max(
                    candidate_confirmation_ms,
                    trigger_break_close_ms or candidate_confirmation_ms,
                )
                recent = [
                    c for c in trigger[-12:]
                    if int(c.close_time_ms) > causal_after_ms
                ]
                touch_times = [
                    int(c.close_time_ms) for c in recent
                    if float(c.high) >= candidate_low and float(c.low) <= candidate_high
                ]
                if touch_times:
                    retested_zones.append((candidate_zone, min(touch_times)))

            if not retested_zones:
                count("no_causal_post_trigger_retest")
                continue

            selected, retest_close_ms = min(
                retested_zones,
                key=lambda item: 0.0 if item[0][0] <= entry <= item[0][1] else min(
                    abs(entry-item[0][0]), abs(entry-item[0][1])
                ) / max(atr, 1e-12),
            )
            low, high, zone_kind, zone_index, zone_confirmation_index = selected
            zone_confirmation_ms = int(zone_series[zone_confirmation_index].close_time_ms)
            if zone_confirmation_ms > snapshot_ms:
                count("future_zone")
                continue

            # Strict anti-chase applies to SCALP only.
            in_zone = low <= entry <= high
            distance_atr = 0.0 if in_zone else min(abs(entry-low), abs(entry-high)) / atr
            if distance_atr > 0.75:
                count("price_chased_away_from_zone")
                continue
        else:
            # Preserve the existing INTRADAY zone-selection and retest policy
            # in the SCALP-only change. INTRADAY-specific causal refinement is
            # handled separately by its dependent PR.
            selected = min(
                zones,
                key=lambda z: 0.0 if z[0] <= entry <= z[1] else min(
                    abs(entry-z[0]), abs(entry-z[1])
                ) / max(atr, 1e-12),
            )
            low, high, zone_kind, zone_index, zone_confirmation_index = selected
            zone_created_ms = int(zone_series[zone_index].close_time_ms)
            if zone_created_ms > snapshot_ms:
                count("future_zone")
                continue
            recent = trigger[-6:]
            in_zone = low <= entry <= high
            retested = any(float(c.high) >= low and float(c.low) <= high for c in recent)
            distance_atr = 0.0 if in_zone else min(abs(entry-low), abs(entry-high)) / atr
            if not (in_zone or retested) or distance_atr > 2.0:
                count("zone_not_recently_retested")
                continue
            retest_close_ms = max(
                (int(c.close_time_ms) for c in recent
                 if float(c.high) >= low and float(c.low) <= high),
                default=int(trigger[-1].close_time_ms),
            )

        # Use structural stop beyond the selected zone with ATR buffer.
        buffer = max(profile.stop_buffer_atr, STOP_BUFFER_ATR_OVERRIDES.get(symbol, profile.stop_buffer_atr))
        stop = low - buffer * atr if direction == "long" else high + buffer * atr
        if (direction == "long" and stop >= entry) or (direction == "short" and stop <= entry):
            # If price has already crossed the zone, use the latest local swing
            # as a structural fallback; never emit a zero/negative-risk setup.
            recent_lows = [float(c.low) for c in trigger[-10:]]
            recent_highs = [float(c.high) for c in trigger[-10:]]
            stop = min(recent_lows) - buffer * atr if direction == "long" else max(recent_highs) + buffer * atr
        risk = abs(entry - stop)
        if risk <= 0:
            count("invalid_stop")
            continue

        if profile_name == "scalp":
            # TP1 is the nearest real directional liquidity level that can
            # satisfy the profile RR floor. Do not synthesize a 2R target; if
            # no real level qualifies, reject the setup.
            liquidity = sorted(
                {float(level.price) for level in confirm.liquidity_levels
                 if (float(level.price) > entry if direction == "long" else float(level.price) < entry)},
                key=lambda p: abs(p-entry),
            )
            if not liquidity:
                count("no_directional_liquidity_target")
                continue
            # The nearest real liquidity is TP1. Reject if it is too close;
            # never skip it to manufacture a compliant RR using a farther level.
            targets = liquidity[:3]
            tp1 = targets[0]
            rr = abs(tp1-entry) / risk
            if rr < profile.min_rr:
                count("nearest_liquidity_below_minimum_rr")
                continue
        else:
            # Preserve the existing INTRADAY target policy in the SCALP-only
            # change; evaluate its target policy separately in the INTRADAY PR.
            liquidity = sorted(
                {float(level.price) for level in confirm.liquidity_levels
                 if (float(level.price) > entry if direction == "long" else float(level.price) < entry)},
                reverse=(direction == "short"),
            )
            targets = [p for p in liquidity if abs(p-entry) >= profile.min_rr * risk][:3]
            if not targets:
                targets = [entry + 2.0*risk if direction == "long" else entry - 2.0*risk]
            tp1 = targets[0]
            rr = abs(tp1-entry) / risk
            if rr < profile.min_rr:
                count("risk_reward_below_minimum")
                continue

        pd = None
        dr = find_dealing_range(bias.swings, as_of_index=bias.as_of_index, direction=expected)
        if dr is not None:
            pd = premium_discount(float(bias_series[-1].close), dr)
        pd_aligned = pd == ("discount" if direction == "long" else "premium")

        internal = False
        if len(trigger) >= 5:
            # Existing internal-structure helper is intentionally optional;
            # avoid a hard veto when no fresh micro event exists.
            from app.smc.scanner import _recent_internal_structure_direction
            internal = _recent_internal_structure_direction(trigger) == expected

        sweep_aligned = (
            sweep_before_trigger if profile_name == "scalp" else
            any(s.direction == expected and len(trigger)-1-int(s.candle_index) <= 12
                for s in confirm.sweeps)
        )
        zone_tf_aligned = bool(zone.structure_breaks and zone.structure_breaks[-1].direction == expected)
        extra_aligned = False
        if extra is not None and extra.structure_breaks:
            ev = extra.structure_breaks[-1]
            ev_index = int(ev.candle_index)
            age = len(extra_series) - 1 - ev_index
            ev_close_ms = int(extra_series[ev_index].close_time_ms) if 0 <= ev_index < len(extra_series) else 0
            extra_max_age = 8 if profile_name == "scalp" else 4
            extra_aligned = ev.direction == expected and 0 <= age <= extra_max_age
            if profile_name == "scalp":
                # 1m confirmation must close after both the 5m retest and BOS.
                extra_aligned = bool(
                    extra_aligned and ev_close_ms > retest_close_ms
                    and trigger_break_close_ms is not None
                    and ev_close_ms > trigger_break_close_ms
                )
        if profile.extra_confirmation_timeframe and not extra_aligned:
            count("no_recent_extra_confirmation")
            continue

        # Three base points represent HTF bias, a confirmed directional zone,
        # and a causal retest. SCALP's trigger/sweep/1m sequence is additionally
        # enforced above; remaining confluences contribute to the profile score.
        score = min(10, 3 + int(trigger_aligned) + int(internal) + int(sweep_aligned) + int(zone_tf_aligned) + int(pd_aligned) + int(extra_aligned))
        if score < profile.score_threshold:
            count("score_below_profile_threshold")
            continue
        evidence = {
            "higher_timeframe_bias_aligned": True,
            "active_ob_fvg_zone": True,
            "zone_retested_or_current": True,
            "trigger_structure_aligned": trigger_aligned,
            "internal_structure_aligned": internal,
            "liquidity_sweep": sweep_aligned,
            "zone_timeframe_structure_aligned": zone_tf_aligned,
            "premium_discount_aligned": pd_aligned,
            "extra_confirmation_aligned": extra_aligned,
            "risk_reward": float(rr),
            "zone_distance_atr": float(distance_atr),
        }
        zone_open_ms = zone_series[zone_index].open_time_ms
        event_ms = trigger[trigger_break.candle_index].open_time_ms if trigger_aligned and trigger_break else trigger[-1].open_time_ms
        key = f"{symbol}:{profile_name}:{direction}:PAC:{zone_kind}:{zone_open_ms}:{event_ms}"
        reasons = ["pac_htf_structure_bias", f"pac_{zone_kind.lower()}_zone", "pac_zone_retest_or_nearby", "pac_atr_stop", "pac_target_and_rr"]
        if trigger_aligned:
            reasons.append("pac_trigger_structure_aligned")
        if internal:
            reasons.append("pac_internal_structure_aligned")
        if sweep_aligned:
            reasons.append("pac_liquidity_sweep_confluence")
        if pd_aligned:
            reasons.append("pac_premium_discount_confluence")
        found.append(SetupCandidate(
            key=key, symbol=symbol, profile=profile_name, direction=direction,
            status="CANDIDATE", confirmation_time_ms=snapshot_ms,
            confirmation_price=entry, stop_price=stop, targets=tuple(targets[:3]),
            score=score, reasons=tuple(reasons), zone=(low, high),
            timeframe=profile.confirmation_timeframe, evidence=evidence, atr=float(atr),
        ))
        count("pac_candidate_generated")
    return found