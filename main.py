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

# Keep the source-layout package importable when FrostDeploy starts main.py
# directly from the repository root without an installed editable package.
ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aicfa.autonomous_scan import AutonomousScanEngine
from aicfa.data_requirements import TradingMode
from aicfa.live_market import BinancePriceMonitor, LiveMarketCoordinator
from aicfa.market_universe import load_market_universe
from aicfa.market_control import serve_control
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
    engine_holder: dict[str, AutonomousScanEngine] = {}

    def _on_candle(event) -> None:
        engine = engine_holder["engine"]
        key = event.key
        mode_map = {
            "5m": (TradingMode.SCALPING, TradingMode.INTRADAY),
            "15m": (TradingMode.INTRADAY,),
            "1h": (TradingMode.SCALPING, TradingMode.SWING),
            "4h": (TradingMode.INTRADAY, TradingMode.POSITION),
            "1d": (TradingMode.SWING, TradingMode.POSITION),
            "1w": (TradingMode.POSITION,),
        }
        modes = mode_map.get(key.timeframe, ())
        if not modes:
            return
        market_index = next(
            (
                index for index, market in enumerate(universe.markets)
                if market.market_type == key.market_type
                and engine._live_symbol_map.get((key.market_type, key.symbol)) == index
            ),
            None,
        )
        if market_index is None:
            return
        state = engine.scan_market(
            market_index,
            modes=modes,
            enforce_timeout=False,
        )
        market = state.result.markets[0]
        diagnostics = market.diagnostics
        print(
            f"AICFA live candle: {market.asset} {key.timeframe} "
            f"status={diagnostics.status if diagnostics else 'completed'} "
            f"setups={len(market.setups)}",
            flush=True,
        )

    coordinator = LiveMarketCoordinator(
        universe,
        provider=upstream,
        data_dir=os.environ.get("AICFA_DATA_DIR", str(ROOT / "data")),
        on_candle=_on_candle,
        max_workers=max(1, min(4, (os.cpu_count() or 2))),
    )
    engine = AutonomousScanEngine(universe, provider=coordinator.cache)
    engine._live_symbol_map = {
        (
            market.market_type,
            coordinator.cache.resolve_symbol(market.asset, market_type=market.market_type),
        ): index
        for index, market in enumerate(universe.markets)
    }
    engine_holder["engine"] = engine

    price_keys = tuple(
        __import__("aicfa.market_data", fromlist=["MarketKey"]).MarketKey(
            "binance",
            coordinator.cache.resolve_symbol(market.asset, market_type=market.market_type),
            market.market_type,
            "5m",
        )
        for market in universe.markets
    )

    def _on_price(key, price, event_ms) -> None:
        engine_holder["engine"].monitor_price(
            symbol=key.symbol,
            market_type=key.market_type,
            price=price,
            now_ms=event_ms,
        )

    price_monitor = BinancePriceMonitor(price_keys, on_price=_on_price)
    control_port = int(os.environ.get("AICFA_CONTROL_PORT", "8091"))

    def _serve_control() -> None:
        try:
            serve_control(engine, host="127.0.0.1", port=control_port)
        except Exception as exc:
            # Market Watch is a control plane. Its failure must be explicit,
            # while the autonomous scanner itself remains alive.
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

    def on_scan(state) -> None:
        market = state.result.markets[0]
        diagnostics = market.diagnostics
        status = diagnostics.status if diagnostics is not None else "completed"
        print(
            f"AICFA scan #{state.scan_number}: {market.asset} "
            f"status={status} setups={len(market.setups)}",
            flush=True,
        )

    def on_error(asset: str, exc: Exception) -> None:
        print(
            f"AICFA scan error: {asset}: {type(exc).__name__}: {exc}",
            flush=True,
        )

    try:
        coordinator.start()
        price_monitor.start()
        stop_event.wait()
    finally:
        price_monitor.stop()
        coordinator.stop()

    print("AICFA autonomous worker stopped.", flush=True)


if __name__ == "__main__":
    main()
