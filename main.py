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
import time

# Keep the source-layout package importable when FrostDeploy starts main.py
# directly from the repository root without an installed editable package.
ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aicfa.autonomous_scan import AutonomousScanEngine
from aicfa.armed_zones import candle_intersects_armed_zone, extract_active_smc_zones, merge_refreshed_zones, zones_for_trigger_timeframe
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
        modes = LIVE_CANDLE_MODE_TRIGGERS.get(key.timeframe, ())
        if not modes:
            return
        cache_key = (key.market_type, key.symbol)
        # Update this candle's own timeframe POIs before considering a skip.
        # Concurrent events for the same symbol fail open while the cache is
        # being refreshed, so a stale snapshot cannot hide a valid signal.
        _refresh_closed_timeframe_zone(key)
        with armed_zone_lock:
            ready = cache_key in armed_zone_ready
            zones = armed_zone_cache.get(cache_key, ())
            scan_in_progress = (
                zone_scan_counts.get(cache_key, 0) > 0
                or zone_refresh_counts.get(cache_key, 0) > 0
            )
            gate_zones = zones_for_trigger_timeframe(zones, key.timeframe)
            should_skip = (
                key.timeframe in {"1m", "5m"}
                and ready
                and not scan_in_progress
                and not candle_intersects_armed_zone(
                    event.low if event.low is not None else float("nan"),
                    event.high if event.high is not None else float("nan"),
                    gate_zones,
                )
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
                f"status={status} setups={len(market.setups)}",
                flush=True,
            )
            # The coordinator advances the durable checkpoint only when this
            # callback succeeds; a failed analysis must be replayed.
            if status in {"error", "timeout"}:
                raise RuntimeError(
                    diagnostics.error or f"live scan returned {status}"
                )
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

    # SIGALRM only works in Python's main thread. Run the market rotation
    # here (rather than in a daemon worker) so a pathological market cannot
    # block the queue for minutes. Live candle/WebSocket startup stays separate.
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

    try:
        # Normal operation is candle-event driven. The legacy market rotation
        # is only an emergency fallback when no confirmed candle arrives for
        # three minutes (for example, a dead WebSocket connection).
        fallback_index = 0
        last_fallback_scan_monotonic = 0.0
        engine.last_automatic_scan_status = "event_driven"
        while not stop_event.is_set():
            if not coordinator.websocket_is_stale(max_age_seconds=180.0):
                engine.automatic_worker_running = True
                stop_event.wait(1.0)
                continue

            now = time.monotonic()
            if now - last_fallback_scan_monotonic < 30.0:
                engine.automatic_worker_running = True
                stop_event.wait(1.0)
                continue

            try:
                engine.automatic_worker_running = True
                engine.last_automatic_scan_status = "websocket_fallback"
                market_index = fallback_index % len(universe.markets)
                state = engine.scan_market(
                    market_index,
                    enforce_timeout=False,
                    journal=True,
                )
                on_scan(state)
                fallback_index = (market_index + 1) % len(universe.markets)
                last_fallback_scan_monotonic = now
            except Exception as exc:
                engine.last_automatic_scan_status = "restarting"
                engine.last_automatic_scan_error = f"{type(exc).__name__}: {exc}"
                print(
                    f"AICFA WebSocket fallback scan failed: {type(exc).__name__}: {exc}; "
                    "retrying.",
                    flush=True,
                )
                last_fallback_scan_monotonic = now
                if stop_event.wait(1.0):
                    break
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
