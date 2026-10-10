"""Production AICFA autonomous scanner worker.

The worker owns process lifecycle only. All market analysis remains inside the
existing AutonomousScanEngine and its deterministic orchestration stack.
"""

from __future__ import annotations

import os
from pathlib import Path
import signal
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

# Keep the source-layout package importable when FrostDeploy starts main.py
# directly from the repository root without an installed editable package.
ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aicfa.autonomous_scan import AutonomousScanEngine
from aicfa.armed_zones import extract_active_smc_zones, merge_refreshed_zones, should_skip_zone_scan, zones_for_trigger_timeframe
from aicfa.data_requirements import TradingMode
from aicfa.live_market import BinancePriceMonitor, LiveMarketCoordinator, LIVE_CANDLE_MODE_TRIGGERS
from aicfa.market_universe import load_market_universe
from aicfa.market_control import serve_control
from aicfa.market_data import MarketKey, completed_ohlcv
from aicfa.market_orchestrator import _cached_build_features
from aicfa.public_market_data import build_public_market_data_provider


DEFAULT_UNIVERSE_PATH = ROOT / "config" / "market_universe.json"


def _universe_path() -> Path:
    configured = os.environ.get("AICFA_MARKET_UNIVERSE")
    return Path(configured).expanduser() if configured else DEFAULT_UNIVERSE_PATH


def main() -> None:
    stop_event = threading.Event()

    def _stop(signum: int, _frame: object) -> None:
        print(f"AICFA worker stopping on signal {signum}.", flush=True)
        stop_event.set()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    universe_path = _universe_path()
    universe = load_market_universe(universe_path)

    # REST seeds the local rolling windows once. From that point the scanner is
    # event-driven: only a closed candle for a configured market/timeframe
    # schedules analysis. The cache remains the provider seen by the canonical
    # setup engine, so scans never refetch the whole history from the exchange.
    upstream = build_public_market_data_provider(timeout_seconds=10.0)
    data_dir = Path(os.environ.get("AICFA_DATA_DIR", str(ROOT / "data")))
    engine_holder: dict[str, AutonomousScanEngine] = {}
    coordinator_holder: dict[str, LiveMarketCoordinator] = {}
    armed_zone_gate_enabled = os.environ.get(
        "AICFA_ARMED_ZONE_GATE_ENABLED", "false"
    ).strip().lower() in {"1", "true", "yes", "on"}
    print(
        "AICFA armed-zone scan gate: "
        + ("enabled" if armed_zone_gate_enabled else "disabled (safe default pending replay validation)"),
        flush=True,
    )
    armed_zone_lock = threading.RLock()
    armed_zone_cache: dict[tuple[str, str], tuple[object, ...]] = {}
    armed_zone_ready: set[tuple[str, str]] = set()
    zone_scan_counts: dict[tuple[str, str], int] = {}
    zone_refresh_counts: dict[tuple[str, str], int] = {}

    def _refresh_armed_zones(market, key) -> None:
        analyses = {}
        for result in getattr(market, "results", ()) or ():
            result_analyses = getattr(result, "analyses", {}) or {}
            if isinstance(result_analyses, dict):
                analyses.update(result_analyses)
        # Do not activate the gate if the scan did not expose completed feature
        # frames; fail open rather than risk dropping a valid confirmation.
        if not analyses:
            # Stale zone geometry must never suppress a valid candle event.
            with armed_zone_lock:
                armed_zone_cache.pop((key.market_type, key.symbol), None)
                armed_zone_ready.discard((key.market_type, key.symbol))
            return
        zones = extract_active_smc_zones(analyses)
        cache_key = (key.market_type, key.symbol)
        refreshed_timeframes = set(analyses)
        with armed_zone_lock:
            # Each trigger profile analyzes a different timeframe subset.
            # Replace zones only for frames present in this scan and retain the
            # latest confirmed zones from other frames.
            armed_zone_cache[cache_key] = merge_refreshed_zones(
                armed_zone_cache.get(cache_key, ()),
                zones,
                refreshed_timeframes,
            )
            armed_zone_ready.add(cache_key)

    def _refresh_closed_timeframe_zone(key) -> None:
        """Refresh the just-closed TF's POIs even when its setup scan is gated.

        Without this step, a 5m candle that fails the 15m+ zone gate could
        never publish a newly formed 5m FVG/OB for the following 1m events.
        The feature cache is shared with the canonical scan, so a candle that
        subsequently passes the gate does not pay for a second feature build.
        """
        if key.timeframe not in {"5m", "15m", "1h", "4h", "1d", "1w"}:
            return
        cache_key = (key.market_type, key.symbol)
        with armed_zone_lock:
            zone_refresh_counts[cache_key] = zone_refresh_counts.get(cache_key, 0) + 1
        try:
            coordinator = coordinator_holder.get("coordinator")
            if coordinator is None:
                return
            frame = coordinator.cache.frame(key)
            if frame is None or frame.empty:
                return
            completed = completed_ohlcv(
                frame,
                timeframe=key.timeframe,
                now_ms=int(time.time() * 1000),
            )
            if completed.empty:
                return
            analysis = _cached_build_features(
                key.symbol, key.market_type, key.timeframe, completed
            )
            refreshed = extract_active_smc_zones(
                {key.timeframe: analysis},
                source_timeframes=(key.timeframe,),
            )
            with armed_zone_lock:
                armed_zone_cache[cache_key] = merge_refreshed_zones(
                    armed_zone_cache.get(cache_key, ()),
                    refreshed,
                    (key.timeframe,),
                )
                armed_zone_ready.add(cache_key)
        except Exception as exc:
            # A failed lightweight refresh must never let stale zones suppress
            # a valid confirmation. Fail open until a successful full scan.
            with armed_zone_lock:
                armed_zone_ready.discard(cache_key)
            print(
                f"AICFA zone refresh failed: {key.symbol} {key.timeframe}: "
                f"{type(exc).__name__}: {exc}; scan gate disabled",
                flush=True,
            )
        finally:
            with armed_zone_lock:
                remaining = zone_refresh_counts.get(cache_key, 1) - 1
                if remaining <= 0:
                    zone_refresh_counts.pop(cache_key, None)
                else:
                    zone_refresh_counts[cache_key] = remaining

    def _on_candle(event) -> None:
        engine = engine_holder["engine"]
        key = event.key
        # Structural context must refresh on daily/weekly closes too, even
        # though those candles do not independently trigger a trading profile.
        if armed_zone_gate_enabled:
            _refresh_closed_timeframe_zone(key)
        modes = LIVE_CANDLE_MODE_TRIGGERS.get(key.timeframe, ())
        if not modes:
            return
        cache_key = (key.market_type, key.symbol)
        # Concurrent events for the same symbol fail open while the cache is
        # being refreshed, so a stale snapshot cannot hide a valid signal.
        with armed_zone_lock:
            ready = cache_key in armed_zone_ready
            zones = armed_zone_cache.get(cache_key, ())
            scan_in_progress = (
                zone_scan_counts.get(cache_key, 0) > 0
                or zone_refresh_counts.get(cache_key, 0) > 0
            )
            gate_zones = zones_for_trigger_timeframe(zones, key.timeframe)
            should_skip = armed_zone_gate_enabled and should_skip_zone_scan(
                timeframe=key.timeframe,
                ready=ready,
                scan_in_progress=scan_in_progress,
                candle_low=event.low if event.low is not None else float("nan"),
                candle_high=event.high if event.high is not None else float("nan"),
                zones=gate_zones,
            )
            if should_skip:
                return
            # If another timeframe for this symbol is updating SMC zones, fail
            # open and analyze this candle. This avoids dropping a valid close
            # because it raced the zone-cache refresh.
            zone_scan_counts[cache_key] = zone_scan_counts.get(cache_key, 0) + 1

        try:
            market_index = next(
                (
                    index for index, market in enumerate(universe.markets)
                    if market.market_type == key.market_type
                    and engine._live_symbol_map.get((key.market_type, key.symbol)) == index
                ),
                None,
            )
            if market_index is None:
                # The WebSocket threads can deliver immediately after start()
                # launches them, before the startup thread has copied the resolved
                # symbol map onto the engine. Resolve from the coordinator's map
                # instead of acknowledging a candle without analyzing it.
                coordinator = coordinator_holder.get("coordinator")
                if coordinator is not None:
                    for resolved_index, resolved_key in coordinator._resolved_market_keys:
                        engine._live_symbol_map[(resolved_key.market_type, resolved_key.symbol)] = resolved_index
                    market_index = engine._live_symbol_map.get((key.market_type, key.symbol))
                if market_index is None:
                    raise RuntimeError(f"closed candle has no configured market mapping: {key.symbol}")
            state = engine.scan_market(
                market_index,
                rotation_id=getattr(engine, "current_rotation_id", 0),
                queue_position=getattr(engine, "current_rotation_queue_position", 0),
                modes=modes,
                enforce_timeout=False,
                journal=True,
            )
            market = state.result.markets[0]
            diagnostics = market.diagnostics
            status = str(diagnostics.status if diagnostics else "completed").lower()
            engine.last_automatic_scan_at_ms = int(state.scanned_at_ms)
            engine.last_automatic_scan_asset = market.asset
            engine.last_automatic_scan_status = status
            engine.last_automatic_scan_error = diagnostics.error if diagnostics else ""
            print(
                f"AICFA live candle: {market.asset} {key.timeframe} "
                f"status={status} setups={len(market.setups)} "
                f"modes=[{_mode_diagnostics(market)}]",
                flush=True,
            )
            # The coordinator advances the durable checkpoint only when this
            # callback succeeds; a failed analysis must be replayed.
            if status in {"error", "timeout"}:
                raise RuntimeError(
                    diagnostics.error or f"live scan returned {status}"
                )
            if armed_zone_gate_enabled:
                _refresh_armed_zones(market, key)
        finally:
            with armed_zone_lock:
                remaining = zone_scan_counts.get(cache_key, 1) - 1
                if remaining <= 0:
                    zone_scan_counts.pop(cache_key, None)
                else:
                    zone_scan_counts[cache_key] = remaining

    coordinator = LiveMarketCoordinator(
        universe,
        provider=upstream,
        data_dir=data_dir,
        on_candle=_on_candle,
        max_workers=max(1, min(4, (os.cpu_count() or 2))),
    )
    coordinator_holder["coordinator"] = coordinator
    engine = AutonomousScanEngine(universe, provider=coordinator.cache)
    # Keep automatic-rotation health separate from last_state, which manual
    # scans can overwrite while the background queue is running.
    engine.automatic_worker_running = False
    engine.last_automatic_scan_at_ms = 0
    engine.last_automatic_scan_asset = ""
    engine.last_automatic_scan_status = "not_started"
    engine.last_automatic_scan_error = ""
    # Event-driven scans must inherit the current rotation metadata so their
    # journal entries cannot reset the terminal's progress to 0/0.
    engine.current_rotation_id = 1
    engine.current_rotation_queue_position = 1
    engine_holder["engine"] = engine

    # Start the control plane before any live-market initialization. Manual
    # Market Watch must remain usable even if one venue takes time to resolve.
    control_port = int(os.environ.get("AICFA_CONTROL_PORT", "8091"))

    def _serve_control() -> None:
        try:
            serve_control(engine, host="127.0.0.1", port=control_port)
        except Exception as exc:
            print(
                f"AICFA market control stopped: {type(exc).__name__}: {exc}",
                flush=True,
            )

    control_thread = threading.Thread(
        target=_serve_control,
        name="aicfa-market-control",
        daemon=True,
    )
    control_thread.start()

    def on_scan(state) -> None:
        market = state.result.markets[0]
        diagnostics = market.diagnostics
        status = diagnostics.status if diagnostics is not None else "completed"
        engine.last_automatic_scan_at_ms = int(state.scanned_at_ms)
        engine.last_automatic_scan_asset = market.asset
        engine.last_automatic_scan_status = str(status).lower()
        engine.last_automatic_scan_error = diagnostics.error if diagnostics is not None else ""
        duration_ms = diagnostics.total_duration_ms if diagnostics is not None else 0.0
        error = diagnostics.error if diagnostics is not None else ""
        analyses = tuple(getattr(market, "results", ()) or ())
        candidate_count = sum(
            len(getattr(getattr(item, "setup_assessment", None), "candidates", ()) or ())
            for item in analyses
        )
        decisions = ",".join(
            f"{getattr(getattr(item, 'mode', None), 'value', getattr(item, 'mode', 'unknown'))}:"
            f"{str(getattr(item, 'decision', 'unknown')).lower()}:"
            f"{len(getattr(getattr(item, 'setup_assessment', None), 'candidates', ()) or ())}"
            for item in analyses
        ) or "none"
        suffix = f" error={error[:240]}" if error else ""
        print(
            f"AICFA scan #{state.scan_number}: {market.asset} "
            f"status={status} duration={duration_ms:.0f}ms "
            f"candidates={candidate_count} active_setups={len(market.setups)} "
            f"modes=[{decisions}]{suffix}",
            flush=True,
        )

    def on_error(asset: str, exc: Exception) -> None:
        engine.last_automatic_scan_asset = asset
        engine.last_automatic_scan_status = "error"
        engine.last_automatic_scan_error = f"{type(exc).__name__}: {exc}"
        print(
            f"AICFA scan error: {asset}: {type(exc).__name__}: {exc}",
            flush=True,
        )

    def _mode_diagnostics(market) -> str:
        """Expose why each trading horizon did or did not produce a setup."""
        parts = []
        for result in getattr(market, "results", ()) or ():
            mode = getattr(getattr(result, "mode", None), "value", getattr(result, "mode", "unknown"))
            assessment = getattr(result, "setup_assessment", None)
            candidates = tuple(getattr(assessment, "candidates", ()) or ())
            reasons = tuple(getattr(assessment, "reasons", ()) or ())
            missing = tuple(getattr(assessment, "missing_context", ()) or ())
            decision = str(getattr(result, "decision", "unknown")).lower()
            detail = f"{mode}:{decision}:candidates={len(candidates)}"
            if reasons:
                detail += f":reason={str(reasons[0])[:120]}"
            if missing:
                detail += f":missing={str(missing[0])[:100]}"
            parts.append(detail)
        return " | ".join(parts) or "no-horizon-results"

    def _run_startup_scan() -> None:
        """Analyze every configured market once on boot; don't wait for a candle."""
        markets = tuple(universe.markets)
        print(
            f"AICFA startup scan: beginning one pass over {len(markets)} markets "
            "with all four modes; live candle events remain enabled.",
            flush=True,
        )
        completed = 0
        errors = 0
        # Keep the initial REST workload bounded so the 1m/5m event workers
        # remain responsive. Per-market locks serialize a boot scan against a
        # simultaneous live candle for the same symbol.
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="aicfa-startup-scan") as pool:
            futures = {
                pool.submit(
                    engine.scan_market,
                    index,
                    rotation_id=0,
                    queue_position=0,
                    enforce_timeout=False,
                    journal=True,
                ): (index, market)
                for index, market in enumerate(markets)
            }
            for future in as_completed(futures):
                index, configured_market = futures[future]
                try:
                    state = future.result()
                    market = state.result.markets[0]
                    diagnostics = market.diagnostics
                    status = str(diagnostics.status if diagnostics else "completed").lower()
                    duration_ms = diagnostics.total_duration_ms if diagnostics else 0.0
                    setup_count = len(market.setups)
                    candidate_count = sum(
                        len(getattr(getattr(item, "setup_assessment", None), "candidates", ()) or ())
                        for item in (getattr(market, "results", ()) or ())
                    )
                    if status in {"error", "timeout"}:
                        errors += 1
                    else:
                        completed += 1
                    engine.last_automatic_scan_at_ms = int(state.scanned_at_ms)
                    engine.last_automatic_scan_asset = market.asset
                    engine.last_automatic_scan_status = status
                    engine.last_automatic_scan_error = diagnostics.error if diagnostics else ""
                    print(
                        f"AICFA startup scan: {market.asset} ({index + 1}/{len(markets)}) "
                        f"status={status} duration={duration_ms:.0f}ms "
                        f"candidates={candidate_count} active_setups={setup_count} "
                        f"modes=[{_mode_diagnostics(market)}]"
                        + (f" error={diagnostics.error[:200]}" if diagnostics and diagnostics.error else ""),
                        flush=True,
                    )
                except Exception as exc:
                    errors += 1
                    print(
                        f"AICFA startup scan error: {configured_market.asset}: "
                        f"{type(exc).__name__}: {exc}",
                        flush=True,
                    )
        print(
            f"AICFA startup scan finished: markets={len(markets)} "
            f"completed={completed} errors={errors}. "
            "Use the per-mode reason/missing fields above to diagnose withheld setups.",
            flush=True,
        )

    # Startup REST analysis is a one-time baseline, not a timed rotation.
    # Thereafter new analysis is triggered by confirmed closed candles.
    price_monitor_holder: dict[str, BinancePriceMonitor] = {}

    def _start_live_services() -> None:
        try:
            coordinator.start()
            resolved_pairs = coordinator._resolved_market_keys
            engine._live_symbol_map = {
                (key.market_type, key.symbol): index
                for index, key in resolved_pairs
            }

            price_keys = tuple(
                MarketKey("binance", key.symbol, key.market_type, "5m")
                for _, key in resolved_pairs
            )

            def _on_price(key, price, event_ms) -> None:
                engine_holder["engine"].monitor_price(
                    symbol=key.symbol,
                    market_type=key.market_type,
                    price=price,
                    now_ms=event_ms,
                )

            if price_keys and not stop_event.is_set():
                monitor = BinancePriceMonitor(price_keys, on_price=_on_price)
                price_monitor_holder["monitor"] = monitor
                monitor.start()

            if not stop_event.is_set():
                threading.Thread(
                    target=_run_startup_scan,
                    name="aicfa-startup-scan",
                    daemon=True,
                ).start()
        except Exception as exc:
            print(
                f"AICFA live services startup error: {type(exc).__name__}: {exc}",
                flush=True,
            )

    threading.Thread(
        target=_start_live_services,
        name="aicfa-live-startup",
        daemon=True,
    ).start()

    print(
        f"AICFA live worker started: markets={len(universe.markets)} "
        f"universe={universe_path}",
        flush=True,
    )
    print(
        "AICFA scanner: Scalping + Intraday + Swing + Position; "
        "closed-candle event triggers + persistent recovery checkpoints.",
        flush=True,
    )

    # The scanner is event-driven: each completed candle is dispatched by
    # LiveMarketCoordinator to _on_candle, which selects the relevant trading
    # mode(s). Durable REST recovery replays missing closed candles; do not run
    # a competing 30-second market queue.
    engine.automatic_worker_running = True
    engine.last_automatic_scan_status = "waiting_for_closed_candles"
    print(
        "AICFA scanner mode: event-driven; scans run on completed candles; "
        "REST checkpoint recovery handles missed events. No timed market rotation.",
        flush=True,
    )
    try:
        while not stop_event.wait(1.0):
            # Keep the process alive for WebSocket callbacks and recovery workers.
            # This wait is only process supervision, not a scan interval.
            pass
    finally:
        engine.automatic_worker_running = False
        stop_event.set()
        monitor = price_monitor_holder.get("monitor")
        if monitor is not None:
            monitor.stop()
        coordinator.stop()

    print("AICFA autonomous worker stopped.", flush=True)


if __name__ == "__main__":
    main()
