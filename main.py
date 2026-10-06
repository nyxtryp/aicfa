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
from aicfa.market_universe import load_market_universe


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
    engine = AutonomousScanEngine(universe)

    print(
        f"AICFA autonomous worker started: markets={len(universe.markets)} "
        f"universe={universe_path}",
        flush=True,
    )
    print(
        "AICFA scanner: Intraday + Swing + Position; "
        "persistent journal enabled by environment.",
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

    engine.run_forever_batches(
        interval_seconds=0,
        batch_size=1,
        on_scan=on_scan,
        on_error=on_error,
        should_stop=stop_event.is_set,
    )

    print("AICFA autonomous worker stopped.", flush=True)


if __name__ == "__main__":
    main()
