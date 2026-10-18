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
        trigger_aligned = bool(trigger_break and trigger_break.direction == expected and 0 <= trigger_break_age <= 3)
        # A PAC setup needs a recent BOS/CHoCH in the confirmation timeframe.
        if not trigger_aligned:
            count("no_recent_trigger_structure")
            continue
        trigger_break_close_ms = int(trigger[int(trigger_break.candle_index)].close_time_ms)

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

        selected = min(
            zones,
            key=lambda z: 0.0 if z[0] <= entry <= z[1] else min(abs(entry-z[0]), abs(entry-z[1])) / max(atr, 1e-12),
        )
        low, high, zone_kind, zone_index, zone_confirmation_index = selected
        zone_confirmation_ms = int(zone_series[zone_confirmation_index].close_time_ms)
        if zone_confirmation_ms > snapshot_ms:
            count("future_zone")
            continue

        # Require an actual retest AFTER both the zone was confirmed and the
        # directional trigger BOS/CHoCH closed. Old touches cannot qualify.
        causal_after_ms = max(zone_confirmation_ms, trigger_break_close_ms)
        recent = [
            c for c in trigger[-6:]
            if int(c.close_time_ms) > causal_after_ms
        ]
        retested = any(float(c.high) >= low and float(c.low) <= high for c in recent)
        if not retested:
            count("no_causal_post_trigger_retest")
            continue
        in_zone = low <= entry <= high
        distance_atr = 0.0 if in_zone else min(abs(entry-low), abs(entry-high)) / atr
        if distance_atr > 0.75:
            count("price_chased_away_from_zone")
            continue

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

        # TP1 must be the nearest confirmed liquidity level in the trade
        # direction. Never skip a nearer opposing level to manufacture >=1.49R,
        # and never synthesize a 2R target when structure provides no target.
        liquidity = sorted(
            {float(level.price) for level in confirm.liquidity_levels
             if (float(level.price) > entry if direction == "long" else float(level.price) < entry)},
            key=lambda p: abs(p-entry),
        )
        if not liquidity:
            count("no_directional_liquidity_target")
            continue
        targets = liquidity[:3]
        tp1 = targets[0]
        rr = abs(tp1-entry) / risk
        if rr < profile.min_rr:
            count("nearest_liquidity_below_minimum_rr")
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

        sweep_aligned = any(s.direction == expected and len(trigger)-1-int(s.candle_index) <= 12
                            for s in confirm.sweeps)
        zone_tf_aligned = bool(zone.structure_breaks and zone.structure_breaks[-1].direction == expected)
        extra_aligned = False
        if extra is not None and extra.structure_breaks:
            ev = extra.structure_breaks[-1]
            age = len(extra_series) - 1 - int(ev.candle_index)
            extra_aligned = ev.direction == expected and 0 <= age <= 4

        # Four base points represent mandatory gates already passed:
        # HTF bias, confirmed directional zone, causal post-trigger retest,
        # and fresh aligned trigger structure. Remaining points are explicit
        # confluences; enforce the profile threshold rather than merely display it.
        score = min(10, 4 + int(internal) + int(sweep_aligned) + int(zone_tf_aligned) + int(pd_aligned) + int(extra_aligned))
        if score < profile.score_threshold:
            count("score_below_profile_threshold")
            continue
        evidence = {
            "higher_timeframe_bias_aligned": True,
            "active_ob_fvg_zone": True,
            "zone_retested_or_current": bool(retested or in_zone),
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
