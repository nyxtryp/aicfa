from contextlib import asynccontextmanager
import asyncio
import logging
import json
import os
import time
from collections import defaultdict, deque

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse

from app.auth import AuthError, AuthStore
from app.backup import create_verified_backup
from app.market_data import ALL_SYMBOLS, TIMEFRAMES, TRADFI_SYMBOLS, MarketDataManager
from app.smc.engine import analyze_smc
from app.market_hours import COMMODITY_SYMBOLS, KRX_EQUITY_SYMBOLS, US_EQUITY_SYMBOLS, tradfi_market_is_open, tradfi_scan_block_reason
from app.smc.presentation import to_chart_payload
from app.smc.pac_scanner import scan_symbol  # active strategy: PAC-inspired; legacy scanner retained for rollback
from app.smc.setups import SetupEvidence, evaluate_candidate
from app.smc.setup_store import SetupStore

logger = logging.getLogger("aicfa.backup")
BACKUP_INTERVAL_SECONDS = 24 * 60 * 60
BACKUP_RETRY_SECONDS = 60 * 60
SCANNER_LIVE_ENABLED = os.getenv("AICFA_SCANNER_LIVE_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
COMMISSION_RATE_PER_SIDE = float(os.getenv("AICFA_COMMISSION_RATE_PER_SIDE", "0.0005"))
if not 0 <= COMMISSION_RATE_PER_SIDE <= 0.01:
    raise ValueError("AICFA_COMMISSION_RATE_PER_SIDE must be between 0 and 0.01")
backup_status = {"status": "waiting", "last_success_ms": None, "filename": None, "size_bytes": None, "last_error": None}

market_data = MarketDataManager()
setup_store: SetupStore | None = None


def _get_setup_store() -> SetupStore:
    global setup_store
    if setup_store is None:
        # Defer opening persistent storage until the app has started and the
        # candle store has created its configured data directory.
        setup_store = SetupStore(market_data.store.path)
    return setup_store

_event_subscribers: set[asyncio.Queue[str]] = set()
_event_history = deque(maxlen=200)
_analysis_cache: dict[tuple[str, str], dict] = {}
_setup_candidates: dict[str, dict] = {}
_scanner_last_event_ms: int | None = None
_scanner_event_count = 0
_scanner_error_count = 0
_scanner_last_error: str | None = None
_scanner_last_candidate_count = 0
_scanner_last_ready_series = 0
_scanner_last_rejections: dict[str, int] = {}
_scanner_rejection_totals: dict[str, int] = defaultdict(int)


def _publish_event(payload: dict) -> None:
    encoded = json.dumps(payload, separators=(",", ":"))
    _event_history.append(encoded)
    for queue in tuple(_event_subscribers):
        if queue.full():
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        try:
            queue.put_nowait(encoded)
        except asyncio.QueueFull:
            pass



def _advance_active_setups(candle, *, publish: bool = True) -> None:
    """Advance persisted setups using finalized 1m candles; ambiguous same-bar outcomes are conservative."""
    if candle.timeframe != "1m":
        return
    store = _get_setup_store()
    now_ms = candle.close_time_ms
    for setup in store.list_monitored():
        if candle.symbol != setup.get("symbol") or now_ms <= max(int(setup.get("confirmation_time_ms", 0)), int(setup.get("last_event_time_ms", 0))):
            continue
        payload = dict(setup)
        direction = payload["direction"]
        entry = float(payload["confirmation_price"])
        original_stop = float(payload["stop_price"])
        candidate_mode = payload.get("status") == "CANDIDATE"
        targets = [float(x) for x in payload.get("targets", [])][:1]  # TP1 closes the entire paper setup.
        if not targets:
            # A persisted setup must have TP1, but guard corrupted legacy rows.
            continue
        target_weights = {1: (1.0,), 2: (0.5, 0.5), 3: (0.5, 0.3, 0.2)}[len(targets)]
        opened = int(payload["confirmation_time_ms"])
        lifetime_hours = 3 if payload["profile"] == "scalp" else 12
        expired = now_ms >= opened + lifetime_hours * 3_600_000
        low, high, close = float(candle.low), float(candle.high), float(candle.close)
        zone = payload.get("zone", [])
        invalidated = len(zone) == 2 and ((direction == "long" and close < min(zone)) or
                                           (direction == "short" and close > max(zone)))
        if invalidated and payload.get("status") == "ACCEPTED":
            payload["status"] = "INVALIDATED"
            _finish_setup(payload, store, now_ms, "INVALIDATED", publish=publish)
            continue
        status = payload["status"]
        stop = entry if status in ("TP1", "TP2") else original_stop
        stop_hit = low <= stop if direction == "long" else high >= stop
        gross_r = float(payload.get("gross_r", 0.0))
        commission_r = float(payload.get("commission_r", 0.0))
        risk = abs(entry - original_stop)
        if risk <= 0:
            payload["status"] = "REJECTED"
            payload["decision_reasons"] = list(payload.get("decision_reasons", [])) + ["invalid_risk_during_lifecycle"]
            store.transition(payload["key"], payload, event_type="LIFECYCLE_REJECTED", event_time_ms=now_ms)
            continue
        if stop_hit:
            if status == "ACCEPTED":
                gross_r -= 1.0
                commission_r += COMMISSION_RATE_PER_SIDE * (entry + stop) / risk
            else:
                completed_targets = {"TP1": 1, "TP2": 2}.get(status, 0)
                remaining = max(0.0, 1.0 - sum(target_weights[:completed_targets]))
                commission_r += remaining * COMMISSION_RATE_PER_SIDE * (entry + stop) / risk
            payload.update({"status": "SL", "gross_r": gross_r, "commission_r": commission_r})
            _finish_setup(payload, store, now_ms, "SL", publish=publish)
            continue
        stages = {"CANDIDATE": 0, "ACCEPTED": 0, "TP1": 1, "TP2": 2}
        stage = stages.get(status, 3)
        first_target_hit = (high >= targets[0]) if direction == "long" else (low <= targets[0])
        breakeven_hit = (low <= entry) if direction == "long" else (high >= entry)
        if status == "ACCEPTED" and first_target_hit and breakeven_hit:
            target = targets[0]
            gross_r += 0.5 * ((target - entry) if direction == "long" else (entry - target)) / risk
            commission_r += 0.5 * COMMISSION_RATE_PER_SIDE * (entry + target) / risk
            commission_r += 0.5 * COMMISSION_RATE_PER_SIDE * (entry + entry) / risk
            payload.update({"status": "SL", "gross_r": gross_r, "commission_r": commission_r})
            _finish_setup(payload, store, now_ms, "SL", publish=publish)
            continue
        reached = []
        for idx in range(stage, len(targets)):
            target = targets[idx]
            hit = high >= target if direction == "long" else low <= target
            if not hit:
                break
            weight = target_weights[idx]
            gross_r += weight * ((target - entry) if direction == "long" else (entry - target)) / risk
            commission_r += weight * COMMISSION_RATE_PER_SIDE * (entry + target) / risk
            reached.append(idx + 1)
        if not reached:
            if expired:
                completed_targets = {"CANDIDATE": 0, "ACCEPTED": 0, "TP1": 1, "TP2": 2}.get(status, len(targets))
                remaining = max(0.0, 1.0 - sum(target_weights[:completed_targets]))
                gross_r += remaining * ((close - entry) if direction == "long" else (entry - close)) / risk
                commission_r += remaining * COMMISSION_RATE_PER_SIDE * (entry + close) / risk
                payload.update({"status": "EXPIRED", "gross_r": gross_r, "commission_r": commission_r})
                _finish_setup(payload, store, now_ms, "EXPIRED", publish=publish)
            continue
        last = reached[-1]
        payload.update({"gross_r": gross_r, "commission_r": commission_r, "last_event_time_ms": now_ms})
        if candidate_mode or last == len(targets):
            payload["status"] = "CLOSED"
            _finish_setup(payload, store, now_ms, f"TP{last}", publish=publish)
        else:
            payload["status"] = f"TP{last}"
            if store.transition(payload["key"], payload, event_type=f"TP{last}", event_time_ms=now_ms) and publish:
                _publish_event({"type": "setup_lifecycle", "setup": payload})
            if expired:
                remaining = max(0.0, 1.0 - sum(target_weights[:last]))
                gross_r += remaining * ((close - entry) if direction == "long" else (entry - close)) / risk
                commission_r += remaining * COMMISSION_RATE_PER_SIDE * (entry + close) / risk
                payload.update({"status": "EXPIRED", "gross_r": gross_r, "commission_r": commission_r})
                _finish_setup(payload, store, now_ms, "EXPIRED", publish=publish)


def _finish_setup(payload: dict, store: SetupStore, event_time_ms: int, final_status: str, *, publish: bool = True) -> None:
    payload["final_status"] = final_status
    payload["closed_at_ms"] = event_time_ms
    gross_r = float(payload.get("gross_r", 0.0))
    commission_r = float(payload.get("commission_r", 0.0))
    payload["net_r"] = gross_r - commission_r
    journal = {
        "key": payload["key"], "symbol": payload["symbol"], "profile": payload["profile"],
        "direction": payload["direction"], "timeframe": payload.get("timeframe", "1m"), "final_status": final_status,
        "confirmation_price": payload.get("confirmation_price"), "entry_limit": payload.get("entry_limit"),
        "stop_price": payload.get("stop_price"), "targets": payload.get("targets", []), "zone": payload.get("zone", []),
        "opened_at_ms": int(payload["confirmation_time_ms"]), "closed_at_ms": event_time_ms,
        "gross_r": gross_r, "commission_r": commission_r, "net_r": payload["net_r"],
    }
    if store.transition(payload["key"], payload, event_type=final_status,
                        event_time_ms=event_time_ms, final_journal=journal) and publish:
        _publish_event({"type": "setup_lifecycle", "setup": payload, "journal": journal})



async def _invalidate_on_opposite_choch(candle) -> None:
    """Invalidate an unscaled active setup on an opposite CHoCH at its confirmation timeframe."""
    if candle.timeframe not in {"5m", "15m"}:
        return
    for setup in _get_setup_store().list_monitored():
        if setup.get("symbol") != candle.symbol or setup.get("status") not in {"CANDIDATE", "ACCEPTED"} or setup.get("timeframe") != candle.timeframe:
            continue
        if candle.close_time_ms <= int(setup.get("confirmation_time_ms", 0)):
            continue
        series = tuple(
            item for item in market_data.candles.get((candle.symbol, candle.timeframe), ())
            if item.close_time_ms <= candle.close_time_ms
        )
        if len(series) < 40:
            continue
        analysis = await asyncio.to_thread(
            analyze_smc,
            [float(item.open) for item in series],
            [float(item.high) for item in series],
            [float(item.low) for item in series],
            [float(item.close) for item in series],
            [float(item.volume) for item in series],
            [item.open_time_ms for item in series],
        )
        if not analysis.structure_breaks:
            continue
        latest_break = analysis.structure_breaks[-1]
        opposite = "bearish" if setup["direction"] == "long" else "bullish"
        if latest_break.kind != "CHoCH" or latest_break.direction != opposite:
            continue
        payload = dict(setup)
        payload["status"] = "INVALIDATED"
        _finish_setup(payload, _get_setup_store(), candle.close_time_ms, "INVALIDATED")


async def _on_closed_candle(candle) -> None:
    global _scanner_last_event_ms, _scanner_event_count, _scanner_error_count, _scanner_last_error, _scanner_last_candidate_count, _scanner_last_ready_series, _scanner_last_rejections
    _advance_active_setups(candle)
    await _invalidate_on_opposite_choch(candle)
    if candle.timeframe in {"5m", "15m"}:
        _scanner_last_event_ms = candle.close_time_ms
        _scanner_event_count += 1
        snapshot = {tf: tuple(x for x in market_data.candles.get((candle.symbol, tf), ()) if x.close_time_ms <= candle.close_time_ms) for tf in TIMEFRAMES}
        _scanner_last_ready_series = sum(len(snapshot.get(tf, ())) >= 40 for tf in TIMEFRAMES)
        _scanner_last_candidate_count = 0
        _scanner_last_error = None
        scan_diagnostics: dict[str, int] = {}
        try:
            # Closed or unverified TradFi sessions must not generate incoming setups.
            block_reason = (
                tradfi_scan_block_reason(candle.symbol)
                if candle.symbol in TRADFI_SYMBOLS else None
            )
            if block_reason is not None:
                scan_diagnostics[f"{block_reason}_scan_skipped"] = 1
                candidates = []
            else:
                candidates = await asyncio.to_thread(
                    scan_symbol, candle.symbol, snapshot,
                    trigger_timeframe=candle.timeframe, diagnostics=scan_diagnostics,
                )
            _scanner_last_candidate_count = len(candidates)
            _scanner_last_rejections = dict(scan_diagnostics)
            for reason, count in scan_diagnostics.items():
                _scanner_rejection_totals[reason] += count
            for candidate in candidates:
                # Recheck before persistence in case the session closes mid-scan.
                candidate_block_reason = (
                    tradfi_scan_block_reason(candidate.symbol)
                    if candidate.symbol in TRADFI_SYMBOLS else None
                )
                if candidate_block_reason is not None:
                    reason = f"{candidate_block_reason}_scan_skipped"
                    _scanner_last_rejections[reason] = _scanner_last_rejections.get(reason, 0) + 1
                    _scanner_rejection_totals[reason] += 1
                    continue
                payload = candidate.as_dict()
                tick_info = market_data.exchange_filters.get(candidate.symbol)
                latest = snapshot.get(candidate.timeframe, ())
                now_ms = int(time.time() * 1000)
                tf_ms = {"1m": 60_000, "5m": 300_000, "15m": 900_000, "1h": 3_600_000, "4h": 14_400_000}[candidate.timeframe]
                fresh = bool(latest and now_ms - latest[-1].close_time_ms <= tf_ms + 120_000)
                market_open = True
                market_hours_known = True
                if candidate.symbol in TRADFI_SYMBOLS:
                    market_open = tradfi_market_is_open(candidate.symbol)
                    market_hours_known = market_open is not None
                payload["zone_key"] = f"{candidate.symbol}:{candidate.profile}:{candidate.direction}:{candidate.zone[0]:.12g}:{candidate.zone[1]:.12g}"
                payload["entry_limit"] = None
                payload["risk_reward"] = None
                payload["decision_reasons"] = []
                if not candidate.targets:
                    payload["status"] = "REJECTED"
                    payload["decision_reasons"] = ["tp1_target_missing"]
                elif not tick_info:
                    payload["status"] = "REJECTED"
                    payload["decision_reasons"] = ["tick_size_unavailable"]
                elif not latest:
                    payload["status"] = "REJECTED"
                    payload["decision_reasons"] = ["confirmation_data_missing"]
                elif not market_hours_known:
                    payload["status"] = "REJECTED"
                    payload["decision_reasons"] = ["market_hours_unverified"]
                elif not market_open:
                    payload["status"] = "REJECTED"
                    payload["decision_reasons"] = ["tradfi_market_closed"]
                else:
                    if ":PAC:" in candidate.key:
                        # PAC candidates have already passed the PAC scanner's own
                        # structural/zone/ATR/RR rules. Do not run the legacy SMC
                        # hard-gates here (sweep, PD/OTE, mandatory 1m, old score).
                        risk = abs(candidate.confirmation_price - candidate.stop_price)
                        reward = abs(candidate.targets[0] - candidate.confirmation_price) if candidate.targets else 0.0
                        rr = reward / risk if risk > 0 else 0.0
                        target_on_correct_side = (
                            candidate.targets and
                            (candidate.targets[0] > candidate.confirmation_price if candidate.direction == "long"
                             else candidate.targets[0] < candidate.confirmation_price)
                        )
                        if (not fresh or risk <= 0 or rr < 1.49 or not target_on_correct_side
                                or float(tick_info.get("tick_size", 0)) <= 0):
                            payload["status"] = "REJECTED"
                            payload["decision_reasons"] = ["pac_invalid_risk_target_or_rr"]
                        else:
                            payload["entry_limit"] = candidate.confirmation_price
                            payload["risk_reward"] = rr
                            payload["score"] = candidate.score
                            # PAC candidates are eligible scanner setups too: track them in Accepted.
                            # This is paper tracking only and never submits an exchange order.
                            payload["status"] = "ACCEPTED"
                            payload["decision_reasons"] = list(candidate.reasons) + ["pac_paper_tracking"]
                    else:
                        evidence = SetupEvidence(**candidate.evidence)
                        decision = evaluate_candidate(
                            evidence,
                            direction=candidate.direction,
                            higher_timeframe_bias=candidate.direction,
                            premium_discount_zone="discount" if candidate.direction == "long" else "premium",
                            zone_intersects_ote=True,
                            confirmation_aligned=True,
                            one_minute_confirmed=True,
                            profile=candidate.profile,
                            entry_price=candidate.confirmation_price,
                            current_price=float(latest[-1].close),
                            stop_price=candidate.stop_price,
                            tp1_price=candidate.targets[0],
                            tick_size=float(tick_info["tick_size"]),
                            min_stop_distance=max(0.5 * candidate.atr, candidate.confirmation_price * 4 * COMMISSION_RATE_PER_SIDE),
                            data_fresh=fresh,
                            tradfi_market_open=market_open,
                        )
                        payload["entry_limit"] = decision.entry_limit
                        payload["risk_reward"] = decision.risk_reward
                        payload["score"] = decision.score.total
                        payload["decision_reasons"] = list(decision.reasons)
                        # "Accepted" means the scanner is tracking this setup in the paper journal;
                        # it never submits an exchange order or enables real trading.
                        payload["status"] = "ACCEPTED" if decision.status == "ELIGIBLE" else decision.status
                saved, payload = _get_setup_store().save_decision(
                    payload, cooldown_minutes=30 if candidate.profile == "scalp" else 120, max_active=100
                )
                if saved:
                    _setup_candidates[candidate.key] = payload
                    _publish_event({"type": "setup_candidate", "setup": payload})
        except Exception as exc:
            _scanner_error_count += 1
            _scanner_last_error = type(exc).__name__
            logger.exception("Automatic SMC scan failed for %s %s", candle.symbol, candle.timeframe)
    series = tuple(x for x in market_data.candles.get((candle.symbol, candle.timeframe), ()) if x.close_time_ms <= candle.close_time_ms)
    event = {"type": "closed_candle", "symbol": candle.symbol,
             "timeframe": candle.timeframe, "close_time_ms": candle.close_time_ms,
             "series_size": len(series)}
    if len(series) >= 3:
        analysis = await asyncio.to_thread(
            analyze_smc,
            [float(x.open) for x in series],
            [float(x.high) for x in series],
            [float(x.low) for x in series],
            [float(x.close) for x in series],
            [float(x.volume) for x in series],
            [x.open_time_ms for x in series],
        )
        annotations = to_chart_payload(analysis, [x.open_time_ms for x in series])
        _analysis_cache[(candle.symbol, candle.timeframe)] = {
            "status": "ok",
            "symbol": candle.symbol,
            "timeframe": candle.timeframe,
            "candles_count": len(series),
            "candles": [{
                "timestamp_ms": x.open_time_ms,
                "open": float(x.open), "high": float(x.high), "low": float(x.low),
                "close": float(x.close), "volume": float(x.volume),
            } for x in series],
            "annotations": annotations,
        }
        event["analysis"] = {key: len(annotations.get(key, [])) for key in
                             ("swings", "structure_breaks", "order_blocks", "fvg",
                              "liquidity_levels", "sweeps")}
    _publish_event(event)


market_data.on_closed_candle = _on_closed_candle



def _recover_active_history() -> None:
    """Replay persisted active setups through retained 1m candles after downtime."""
    active = _get_setup_store().list_monitored()
    if not active:
        return
    symbols = {str(setup["symbol"]) for setup in active}
    candles = []
    for symbol in symbols:
        candles.extend(market_data.candles.get((symbol, "1m"), ()))
    for candle in sorted(candles, key=lambda item: item.close_time_ms):
        _advance_active_setups(candle, publish=False)


async def _scanner_startup_warmup() -> None:
    """Run the SMC scanner once on each currently fresh finalized 5m/15m candle.

    The REST history load populates candle windows but intentionally does not emit
    candle events. Without this warm-up, the UI can report zero scanner checks
    after every restart until the next 5m/15m close. Only fresh candles are used;
    stale history is never replayed into candidate decisions.
    """
    history_task = market_data._history_task
    if history_task is not None:
        await asyncio.gather(history_task, return_exceptions=True)
    now_ms = int(time.time() * 1000)
    warmup_events = 0
    for symbol in ALL_SYMBOLS:
        for timeframe, duration_ms in (("5m", 300_000), ("15m", 900_000)):
            series = market_data.candles.get((symbol, timeframe), ())
            if not series:
                continue
            latest = series[-1]
            if now_ms - latest.close_time_ms > duration_ms + 120_000:
                continue
            try:
                await _on_closed_candle(latest)
                warmup_events += 1
            except Exception:
                logger.exception("SMC startup warm-up failed for %s %s", symbol, timeframe)
    logger.info("SMC startup warm-up processed %s fresh finalized candle events", warmup_events)


async def _daily_backup_loop() -> None:
    """Back up after startup history finishes, then repeat daily."""
    history_task = market_data._history_task
    if history_task is not None:
        await asyncio.gather(history_task, return_exceptions=True)
    await asyncio.to_thread(_recover_active_history)
    while True:
        try:
            path = await asyncio.to_thread(
                create_verified_backup,
                market_data.store.path,
            )
            backup_status.update({"status": "ok", "last_success_ms": int(time.time() * 1000), "filename": path.name, "size_bytes": path.stat().st_size, "last_error": None})
            logger.info("Verified SQLite backup created: %s", path)
            delay = BACKUP_INTERVAL_SECONDS
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            backup_status.update({"status": "error", "last_error": type(exc).__name__})
            logger.exception("SQLite backup failed; retrying in %s seconds", BACKUP_RETRY_SECONDS)
            delay = BACKUP_RETRY_SECONDS
        await asyncio.sleep(delay)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await market_data.start()
    backup_task = asyncio.create_task(_daily_backup_loop(), name="aicfa-daily-backup")
    scanner_warmup_task = asyncio.create_task(_scanner_startup_warmup(), name="aicfa-scanner-startup-warmup")
    try:
        yield
    finally:
        for task in (backup_task, scanner_warmup_task):
            task.cancel()
        await asyncio.gather(backup_task, scanner_warmup_task, return_exceptions=True)
        await market_data.stop()


app = FastAPI(
    title="AICFA",
    description="SMC market scanner",
    version="0.2.0",
    lifespan=lifespan,
)


AUTH_DATA_DIR = os.environ.get("AICFA_DATA_DIR", "./data")
auth_store = AuthStore(AUTH_DATA_DIR)
AUTH_COOKIE = "aicfa_session"
_attempts: dict[str, deque[float]] = defaultdict(deque)
LOGIN_WINDOW_SECONDS = 900
LOGIN_MAX_ATTEMPTS = 8
PUBLIC_PATHS = {"/health", "/login", "/api/auth/status", "/api/auth/setup", "/api/auth/login", "/api/auth/logout"}

@app.middleware("http")
async def require_single_user_auth(request: Request, call_next):
    if request.url.path in PUBLIC_PATHS:
        return await call_next(request)
    if not auth_store.configured or not auth_store.verify_session(request.cookies.get(AUTH_COOKIE)):
        if request.url.path.startswith("/api/"):
            return JSONResponse({"detail": "authentication required"}, status_code=401)
        return RedirectResponse("/login", status_code=303)
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        origin = request.headers.get("origin")
        if origin:
            from urllib.parse import urlsplit
            if urlsplit(origin).netloc != request.headers.get("host"):
                return JSONResponse({"detail": "origin check failed"}, status_code=403)
    return await call_next(request)

LOGIN_PAGE = """<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AICFA — вход</title>
<style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#080d18;color:#e8eef8;font:16px system-ui}.box{width:min(90vw,400px);padding:28px;background:#101a2a;border:1px solid #293851;border-radius:16px}input,button{box-sizing:border-box;width:100%;padding:12px;margin:6px 0 14px;background:#0b1321;color:#e8eef8;border:1px solid #2a3a53;border-radius:8px}button{background:#17352f}p{color:#a8b8ce}</style><style id="modern-login-theme">
:root{color-scheme:dark;font-family:Inter,ui-sans-serif,system-ui,sans-serif;color:#e9f0fa;background:#080d16;font-synthesis:none;text-rendering:optimizeLegibility}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;display:grid;place-items:center;padding:22px;background:radial-gradient(ellipse at 20% 0%,rgba(39,83,112,.3),transparent 45%),radial-gradient(ellipse at 100% 100%,rgba(28,86,73,.16),transparent 35%),#080d16;color:#e9f0fa;font:15px/1.5 Inter,ui-sans-serif,system-ui,sans-serif}
.box{width:min(100%,420px);padding:clamp(24px,5vw,34px);background:linear-gradient(155deg,rgba(18,30,46,.98),rgba(11,19,31,.98));border:1px solid #2a3c52;border-radius:20px;box-shadow:0 24px 80px rgba(0,0,0,.35)}
h1{margin:0;font-size:1.7rem;letter-spacing:-.05em}.box h1:after{content:".";color:#69e0bd}
p{color:#94a7bf;font-size:.88rem}
label{display:block;margin-top:12px;color:#b8c7d9;font-size:.8rem;font-weight:650}
input,button{box-sizing:border-box;width:100%;padding:12px 13px;margin:6px 0 12px;background:#0b1421;color:#e9f0fa;border:1px solid #30435b;border-radius:9px;font:inherit}
input:focus{outline:2px solid #69e0bd;outline-offset:1px;border-color:#69e0bd}
button{margin-top:10px;background:linear-gradient(180deg,#1b5145,#12382f);border-color:#2c6c5a;font-weight:700;cursor:pointer}
button:hover{background:#205b4d}
#msg{min-height:1.4em;margin-bottom:0;color:#edc477}
</style>

</head><body><main class="box"><h1>AICFA</h1><p id="intro">Проверка…</p><form id="login"><label>Пароль</label><input id="password" type="password" autocomplete="current-password" required><button>Войти</button></form><form id="setup" hidden><label>Токен настройки</label><input id="token" type="password" required><label>Новый пароль (от 12 символов)</label><input id="newpass" type="password" minlength="12" required><button>Установить пароль</button></form><p id="msg" role="status"></p></main><script>
const $=id=>document.getElementById(id),msg=$('msg'),login=$('login'),setup=$('setup');
async function post(url,data){return fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)})}
fetch('/api/auth/status').then(r=>r.json()).then(d=>{if(d.configured){$('intro').textContent='Войдите в закрытую панель.';setup.hidden=true}else{$('intro').textContent=d.setup_available?'Первичная настройка пароля владельца.':'Настройка закрыта: требуется переменная AICFA_SETUP_TOKEN.';login.hidden=true;setup.hidden=!d.setup_available}}).catch(()=>msg.textContent='Ошибка проверки статуса');
login.onsubmit=async e=>{e.preventDefault();const r=await post('/api/auth/login',{password:$('password').value});if(r.ok)location.href='/';else msg.textContent=r.status===429?'Слишком много попыток.':'Неверный пароль.'};
setup.onsubmit=async e=>{e.preventDefault();const r=await post('/api/auth/setup',{token:$('token').value,password:$('newpass').value});if(r.ok){msg.textContent='Пароль установлен. Теперь войдите.';setup.hidden=true;login.hidden=false;$('intro').textContent='Пароль установлен.'}else msg.textContent=r.status===429?'Слишком много попыток.':'Не удалось настроить пароль.'};
</script></body></html>"""

@app.get("/login", response_class=HTMLResponse)
async def login_page() -> HTMLResponse:
    return HTMLResponse(LOGIN_PAGE, headers={"Cache-Control": "no-store"})

@app.get("/api/auth/status")
async def auth_status() -> dict[str, bool]:
    return {"configured": auth_store.configured, "setup_available": bool(os.environ.get("AICFA_SETUP_TOKEN"))}

def _rate_allowed(request: Request) -> bool:
    key = request.client.host if request.client else "unknown"
    now = time.monotonic()
    q = _attempts[key]
    while q and now - q[0] > LOGIN_WINDOW_SECONDS:
        q.popleft()
    if len(q) >= LOGIN_MAX_ATTEMPTS:
        return False
    q.append(now)
    return True

def _cookie(response: JSONResponse, request: Request, token: str) -> None:
    secure = os.environ.get("AICFA_COOKIE_SECURE", "true").lower() not in {"0", "false", "no"}
    response.set_cookie(AUTH_COOKIE, token, max_age=12 * 60 * 60, httponly=True, secure=secure, samesite="strict", path="/")

@app.post("/api/auth/setup")
async def auth_setup(request: Request) -> JSONResponse:
    if not _rate_allowed(request):
        return JSONResponse({"detail":"too many attempts"}, status_code=429)
    expected = os.environ.get("AICFA_SETUP_TOKEN", "")
    if not expected:
        return JSONResponse({"detail":"setup disabled"}, status_code=503)
    try:
        data = await request.json()
        if not isinstance(data, dict):
            raise ValueError("JSON object required")
        password, token = data.get("password", ""), data.get("token", "")
        if not isinstance(password, str) or not isinstance(token, str):
            raise ValueError("password and token must be strings")
        auth_store.set_initial_password(password, token, expected)
    except (AuthError, ValueError, TypeError):
        return JSONResponse({"detail":"setup failed"}, status_code=400)
    return JSONResponse({"status":"configured"})

@app.post("/api/auth/login")
async def auth_login(request: Request) -> JSONResponse:
    if not _rate_allowed(request):
        return JSONResponse({"detail":"too many attempts"}, status_code=429)
    try:
        data = await request.json()
        if not isinstance(data, dict):
            return JSONResponse({"detail":"invalid request"}, status_code=400)
        password = data.get("password", "")
    except (ValueError, TypeError):
        return JSONResponse({"detail":"invalid request"}, status_code=400)
    if not isinstance(password, str) or not auth_store.verify_password(password):
        return JSONResponse({"detail":"invalid credentials"}, status_code=401)
    response = JSONResponse({"status":"ok"})
    _cookie(response, request, auth_store.create_session())
    return response

@app.post("/api/auth/logout")
async def auth_logout() -> JSONResponse:
    response = JSONResponse({"status":"ok"})
    response.delete_cookie(AUTH_COOKIE, path="/", httponly=True, samesite="strict")
    return response

@app.post("/api/settings/password")
async def auth_change_password(request: Request) -> JSONResponse:
    if not auth_store.verify_session(request.cookies.get(AUTH_COOKIE)):
        return JSONResponse({"detail":"authentication required"}, status_code=401)
    try:
        data = await request.json()
        if not isinstance(data, dict):
            raise ValueError("JSON object required")
        current_password, new_password = data.get("current_password", ""), data.get("new_password", "")
        if not isinstance(current_password, str) or not isinstance(new_password, str):
            raise ValueError("passwords must be strings")
        auth_store.change_password(current_password, new_password)
    except (AuthError, ValueError, TypeError):
        return JSONResponse({"detail":"password change failed"}, status_code=400)
    response = JSONResponse({"status":"ok"})
    _cookie(response, request, auth_store.create_session())
    return response

PAGE = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#080d18"><title>AICFA — SMC Scanner</title>
<style>
:root {
  color-scheme: dark;
  font-family: Inter, ui-sans-serif, system-ui, sans-serif;
  background: #090e17;
  color: #e6edf7;
  font-synthesis: none;
  text-rendering: optimizeLegibility;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  min-height: 100vh;
  background: radial-gradient(ellipse at 12% 0%, #142137 0, transparent 38%), #090e17;
}
header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 12px clamp(14px, 2.4vw, 32px);
  border-bottom: 1px solid #202b3c;
  background: rgba(9, 14, 23, .88);
}
.brand { font-size: 1.15rem; font-weight: 800; letter-spacing: .06em; }
.brand span { color: #65dfbb; }
.sub { margin-top: 2px; color: #8292a8; font-size: .68rem; letter-spacing: .04em; }
.pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 100%;
  padding: 5px 8px;
  border: 1px solid #2a374b;
  border-radius: 7px;
  color: #aab8cc;
  font-size: .72rem;
  line-height: 1.35;
}
.led { display: inline-block; width: 6px; height: 6px; flex: 0 0 auto; border-radius: 50%; background: #e7b75f; }
main { max-width: 1720px; margin: 0 auto; padding: 16px clamp(14px, 2.4vw, 32px) 28px; }
.top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}
h1 { margin: 0 0 3px; font-size: clamp(1.35rem, 2.5vw, 1.8rem); line-height: 1.15; letter-spacing: -.035em; }
.muted { color: #8999af; font-size: .76rem; }
.controls { display: flex; align-items: center; justify-content: flex-end; gap: 6px; flex-wrap: wrap; }
select, button {
  min-height: 30px;
  padding: 6px 9px;
  border: 1px solid #2b394d;
  border-radius: 7px;
  background: #111a28;
  color: #e6edf7;
  font: inherit;
  font-size: .76rem;
}
button { cursor: pointer; background: #15352f; border-color: #285c50; }
button:hover { background: #1b443b; }
.grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 5px;
  margin-bottom: 7px;
}
.metric {
  min-width: 0;
  padding: 4px 7px;
  border: 1px solid #253247;
  border-radius: 6px;
  background: #0f1724;
}
.metric .label { color: #8e9eb4; font-size: .62rem; line-height: 1.1; }
.metric .value { margin-top: 1px; font-size: .8rem; line-height: 1.1; font-weight: 700; overflow-wrap: anywhere; font-variant-numeric: tabular-nums; }
.metric .hint { margin-top: 1px; color: #71829a; font-size: .57rem; line-height: 1.1; }
.dashboard {
  display: grid;
  grid-template-columns: minmax(250px, .88fr) minmax(0, 1.75fr) minmax(245px, .86fr);
  gap: 10px;
  align-items: stretch;
}
.dashboard-column {
  display: grid;
  grid-template-rows: repeat(2, minmax(0, 1fr));
  gap: 10px;
  min-width: 0;
  height: calc(100vh - 265px);
  min-height: 320px;
}
.panel {
  min-width: 0;
  margin: 0;
  padding: 12px;
  border: 1px solid #253247;
  border-radius: 10px;
  background: #0e1622;
}
.dashboard .panel { min-width: 0; margin: 0 !important; }
.incoming-panel { display: flex; flex-direction: column; min-height: 0; overflow: hidden; }
.panel-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  min-width: 0;
  margin-bottom: 9px;
  font-size: .78rem;
  line-height: 1.3;
  font-weight: 700;
}
.panel-title > span { min-width: 0; overflow-wrap: anywhere; }
.panel-title .pill { flex: 0 0 auto; padding: 3px 6px; font-size: .65rem; }
.setup-list {
  min-width: 0;
  max-width: 100%;
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
  padding-right: 3px;
}
.setup-list .setup-card { width: 100%; min-width: 0; }
.setup-card {
  margin: 0 0 7px;
  padding: 9px;
  border: 1px solid #253349;
  border-radius: 8px;
  background: #0a121e;
  cursor: pointer;
  transition: border-color .15s, background .15s;
}
.setup-card:hover { border-color: #477c79; background: #101d2b; }
.setup-card.selected { border-color: #65dfbb; box-shadow: inset 2px 0 #65dfbb; }
.setup-card-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 7px; margin-bottom: 7px; }
.setup-card-title { font-size: .82rem; font-weight: 750; overflow-wrap: anywhere; }
.setup-card-sub { margin-top: 2px; color: #8c9bb0; font-size: .66rem; }
.direction-pill { padding: 3px 6px; border-radius: 5px; font-size: .62rem; font-weight: 800; letter-spacing: .03em; white-space: nowrap; }
.direction-long { color: #70e0bd; background: #12372f; }
.direction-short { color: #ff9aa4; background: #39202a; }
.setup-status { padding: 3px 5px; border: 1px solid #2b394d; border-radius: 5px; color: #aab8cc; font-size: .61rem; white-space: nowrap; }
.setup-metrics { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 5px; }
.setup-metric { min-width: 0; padding: 6px; border-radius: 6px; background: #111b29; }
.setup-metric span { display: block; margin-bottom: 2px; color: #8494aa; font-size: .61rem; line-height: 1.25; }
.setup-metric strong { display: block; font-size: .73rem; line-height: 1.25; overflow-wrap: anywhere; font-variant-numeric: tabular-nums; }
.setup-metric.rr strong { color: #e8bf72; }
.setup-time { margin-top: 6px; color: #7789a1; font-size: .61rem; line-height: 1.4; overflow-wrap: anywhere; }
.setup-details { margin-top: 7px; padding-top: 6px; border-top: 1px solid #202c3d; cursor: default; }
.setup-details summary { color: #a0b0c4; font-size: .66rem; cursor: pointer; list-style-position: inside; }
.reason-list { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px; }
.reason-tag { padding: 3px 5px; border: 1px solid #29384d; border-radius: 5px; background: #142033; color: #aab8cc; font-size: .61rem; line-height: 1.3; }
.setup-list::-webkit-scrollbar { width: 5px; }
.setup-list::-webkit-scrollbar-thumb { border-radius: 8px; background: #293b54; }
.setup-list::-webkit-scrollbar-track { background: transparent; }
.right-stack { display: grid; align-content: start; gap: 10px; min-width: 0; }
.chart-column { min-width: 0; }
.chart-column #setupChart { grid-template-columns: minmax(0, 1fr); }
.chart-column #setupChart aside { margin-top: 0; }
.chart-wrap { position: relative; height: 390px; }
.chart-wrap canvas { display: block; width: 100%; height: 100%; }
.chart-note { margin-top: 8px; color: #8495ad; font-size: .72rem; line-height: 1.45; }
.rows { display: grid; gap: 0; }
.rowitem { display: flex; justify-content: space-between; gap: 10px; padding: 7px 0; border-bottom: 1px solid #202c3d; font-size: .76rem; }
.rowitem:last-child { border: 0; }
.rowitem span:first-child { color: #8e9eb4; }
.rowitem strong { text-align: right; overflow-wrap: anywhere; }
.event { min-width: 0; max-width: 100%; margin-bottom: 6px; padding: 8px 9px; border: 1px solid #222f42; border-radius: 7px; background: #0a121e; font-size: .72rem; line-height: 1.45; overflow-wrap: anywhere; word-break: break-word; }
.event > div { min-width: 0; max-width: 100%; white-space: normal; overflow-wrap: anywhere; word-break: break-word; }
.event b { color: #70e0bd; overflow-wrap: anywhere; word-break: break-word; }
.empty { padding: 12px 0; color: #8292a8; font-size: .76rem; line-height: 1.5; }
footer { margin-top: 12px; color: #61738e; font-size: .68rem; line-height: 1.5; }
@media (max-width: 1180px) {
  .dashboard { grid-template-columns: minmax(220px, .85fr) minmax(0, 1.5fr); }
  .dashboard-column { height: calc(100vh - 250px); min-height: 300px; }
  .right-stack { grid-column: 1 / -1; grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 760px) {
  header { align-items: flex-start; }
  .controls { width: 100%; justify-content: flex-start; }
  main { padding-top: 12px; }
  .top { align-items: flex-start; flex-direction: column; }
  .grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 4px; margin-bottom: 6px; }
  .metric { padding: 4px 6px; }
  .dashboard { grid-template-columns: minmax(0, 1fr); gap: 9px; }
  .dashboard-column { height: auto; min-height: 0; grid-template-rows: repeat(2, minmax(220px, auto)); gap: 9px; }
  .right-stack { grid-column: auto; grid-template-columns: minmax(0, 1fr); gap: 9px; }
  .panel { padding: 10px; }
  .chart-wrap { height: 320px; }
  .setup-list { max-height: 54vh; }
}
@media (max-width: 420px) {
  .sub { font-size: .61rem; }
  .grid { gap: 4px; }
  .metric { padding: 3px 5px; }
  .metric .label { font-size: .58rem; }
  .metric .value { font-size: .76rem; }
  .metric .hint { font-size: .54rem; }
  .panel { padding: 9px; }
  .setup-card { padding: 8px; }
  .chart-wrap { height: 270px; }
}

.journal-summary{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px;margin:10px 0}.journal-stat{min-width:0;border:1px solid var(--line,#26313b);border-radius:9px;padding:9px;background:rgba(255,255,255,.025)}.journal-stat span{display:block;font-size:.68rem;color:var(--muted,#8b98a7);margin-bottom:5px}.journal-stat strong{font-size:1.05rem;overflow-wrap:anywhere;font-variant-numeric:tabular-nums}.journal-filters{display:flex;gap:5px;align-items:center;flex-wrap:wrap;margin:8px 0}.journal-filter{background:transparent;color:var(--muted,#8b98a7);border:1px solid var(--line,#26313b);border-radius:6px;padding:5px 8px;font-size:.72rem;cursor:pointer}.journal-filter.active{color:var(--accent,#b7f36b);border-color:var(--accent,#b7f36b)}.journal-audit{font-size:.68rem;color:#e7b66a;margin-left:auto}.journal-trade{padding:9px 2px;border-bottom:1px solid var(--line,#26313b);cursor:pointer}.journal-trade:last-child{border-bottom:0}.journal-trade-head,.journal-trade-foot{display:flex;justify-content:space-between;align-items:center;gap:8px}.journal-trade-head{font-size:.78rem;font-weight:650}.journal-trade-foot{font-size:.68rem;color:var(--muted,#8b98a7);margin-top:5px;flex-wrap:wrap}.journal-net{font-variant-numeric:tabular-nums;font-weight:750}.journal-net.positive{color:#83dfb0}.journal-net.negative{color:#ff8c91}.journal-warning{font-size:.7rem;color:#e7b66a;margin-top:5px}
</style><style id="modern-mvp-theme">
:root{color-scheme:dark;--bg:#080d16;--surface:#0e1725;--surface-raised:#121e2e;--line:#24344a;--line-soft:#1b293b;--text:#e9f0fa;--muted:#8fa1b9;--accent:#69e0bd;--accent-soft:#102e2a;--danger:#ff8796;--warning:#edc477;--radius:12px;--shadow:0 12px 32px rgba(0,0,0,.14)}
html{scroll-behavior:smooth;scrollbar-color:#344963 #0a111c}
body{background:radial-gradient(ellipse at 10% -10%,rgba(39,83,112,.24),transparent 42%),radial-gradient(ellipse at 90% 0%,rgba(28,86,73,.12),transparent 32%),var(--bg);color:var(--text);font-feature-settings:"ss01" on,"cv11" on}
header{position:sticky;top:0;z-index:20;min-height:58px;padding:9px clamp(14px,2.4vw,32px);background:rgba(8,13,22,.88);backdrop-filter:blur(18px);border-bottom:1px solid rgba(83,109,143,.22)}
.brand{font-size:1.08rem;letter-spacing:.09em}.brand span{color:var(--accent)}
.sub{font-size:.64rem;letter-spacing:.12em;color:#8396b0}
main{max-width:1840px;padding-top:15px}
.top{align-items:flex-end;margin-bottom:12px}.top>div:first-child{min-width:0}
h1{font-size:clamp(1.45rem,2.2vw,2rem);letter-spacing:-.045em;font-weight:760}
.muted{font-size:.78rem;color:var(--muted)}
.controls{gap:7px}
.pill{border-color:var(--line);background:rgba(16,27,42,.72);border-radius:999px;padding:5px 9px;font-size:.69rem}
.led{width:7px;height:7px;box-shadow:0 0 0 3px rgba(237,196,119,.12)}
button,select{min-height:32px;padding:7px 11px;border-color:#30435b;border-radius:8px;background:#111d2c;transition:background .15s,border-color .15s,transform .15s}
button{background:linear-gradient(180deg,#17483e,#12382f);border-color:#286553;font-weight:650}
button:hover{background:#1b5145;border-color:#39846d}
button:active{transform:translateY(1px)}
button:focus-visible,select:focus-visible,summary:focus-visible,.setup-card:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.grid{gap:5px;margin-bottom:9px}
.metric{padding:4px 7px;border-color:var(--line-soft);border-radius:7px;background:linear-gradient(145deg,rgba(17,29,45,.96),rgba(12,21,33,.96));box-shadow:none}
.metric .label{font-size:.62rem;line-height:1.1;letter-spacing:.015em;color:#9aabc0}
.metric .value{margin-top:1px;font-size:.8rem;line-height:1.1;font-weight:750;letter-spacing:-.015em}
.metric .hint{margin-top:1px;font-size:.57rem;line-height:1.1;color:#71849d}
.dashboard{grid-template-columns:minmax(235px,.86fr) minmax(0,1.72fr) minmax(225px,.82fr);gap:11px}
.dashboard-column{gap:11px;height:calc(100vh - 248px);min-height:350px}
.panel{padding:13px;border-color:var(--line-soft);border-radius:var(--radius);background:linear-gradient(160deg,rgba(15,24,38,.97),rgba(11,19,31,.97));box-shadow:var(--shadow)}
.panel-title{font-size:.79rem;margin-bottom:10px;letter-spacing:.005em}
.panel-title .pill{font-size:.64rem;padding:3px 8px}
.setup-list{scrollbar-width:thin;scrollbar-color:#344963 transparent}
.setup-card{padding:10px;margin-bottom:7px;border-color:#24354a;border-radius:10px;background:linear-gradient(145deg,#0d1725,#0b1420);box-shadow:0 2px 8px rgba(0,0,0,.08)}
.setup-card:hover{border-color:#4d8e83;background:linear-gradient(145deg,#122436,#0d1b29)}
.setup-card.selected{border-color:var(--accent);box-shadow:inset 2px 0 var(--accent),0 0 0 1px rgba(105,224,189,.07)}
.setup-card-head{margin-bottom:8px}.setup-card-title{font-size:.85rem;letter-spacing:-.01em}.setup-card-sub{font-size:.67rem;color:#92a4bb}
.direction-long{color:#83ebc9;background:#12372f;border:1px solid #225b4d}.direction-short{color:#ffabb4;background:#3a202a;border:1px solid #64313d}
.setup-status{background:#121e2d;border-color:#2c3d53;border-radius:6px}
.setup-metrics{gap:5px}.setup-metric{padding:7px;border:1px solid rgba(42,59,80,.48);border-radius:8px;background:rgba(18,30,46,.76)}
.setup-metric span{color:#8ea1b8;font-size:.62rem}.setup-metric strong{font-size:.76rem}
.setup-metric.rr strong{color:var(--warning)}.setup-time{font-size:.62rem;color:#8194ad}
.setup-details{border-color:var(--line-soft)}.setup-details summary{padding:2px 0;color:#a6b7cb}
.reason-tag{border-color:#2a3b52;border-radius:6px;background:#142236;color:#b3c2d5}
.chart-wrap{height:clamp(300px,43vh,540px)}
.chart-note{color:#94a7bf;font-size:.73rem}
.rows .rowitem{border-color:var(--line-soft);padding:8px 0}.rowitem span:first-child{color:#93a5bc}
.event{border-color:var(--line-soft);border-radius:9px;background:#0b1522}
.empty{color:#8fa1b8}
#chartPlaceholder{border-style:dashed;border-color:#2a3d53;background:linear-gradient(145deg,rgba(16,29,45,.7),rgba(11,19,31,.75))}
#setupChart .panel{overflow:hidden}
footer{padding-top:3px;color:#71849d}
@media(max-width:1180px){.dashboard{grid-template-columns:minmax(220px,.85fr) minmax(0,1.5fr);gap:10px}.dashboard-column{height:calc(100vh - 245px)}.right-stack{gap:10px}}
@media(max-width:760px){
 header{position:relative;align-items:center;flex-wrap:wrap;gap:8px}
 header>.controls{width:100%;justify-content:flex-start}
 main{padding:12px 12px 22px}
 .top{gap:10px}.top>.pill{align-items:flex-start;flex-direction:column;border-radius:10px;max-width:100%;white-space:normal}
 .grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:4px;margin-bottom:8px}
 .metric{padding:4px 6px}.metric .label{font-size:.6rem}.metric .value{font-size:.79rem}.metric .hint{font-size:.55rem}
 .dashboard{gap:9px}.dashboard-column{gap:9px;grid-template-rows:repeat(2,minmax(230px,auto))}
 .right-stack{gap:9px}.panel{padding:11px}.chart-wrap{height:clamp(250px,48vh,400px)}
 .setup-list{max-height:56vh}
}
@media(max-width:420px){
 .brand{font-size:1rem}.sub{font-size:.58rem}
 .controls button{min-height:30px;padding:6px 9px;font-size:.71rem}
 .metric{padding:3px 5px}.metric .label{font-size:.57rem}.metric .value{font-size:.74rem}.metric .hint{font-size:.52rem}
 .panel{padding:9px}.panel-title{font-size:.74rem}.setup-card{padding:8px}.setup-metric{padding:6px}
 .chart-wrap{height:270px}
}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}*,*::before,*::after{transition:none!important;animation:none!important}}
<style id="aicfa-reconstruction">body{background:#070a10;color:#edf3ff}header{background:rgba(7,10,16,.94);backdrop-filter:blur(20px);border-bottom:1px solid #202b3c}.top{padding:14px 16px;border:1px solid #253146;border-radius:13px;background:linear-gradient(110deg,#121d2d,#0b111b)}.metric{padding:7px 10px;border-radius:10px;background:#0d1522}.panel{border:1px solid #202c3e;border-radius:13px;background:linear-gradient(155deg,#0e1724,#090f18)}.setup-card{border-radius:10px;background:linear-gradient(135deg,#111c2b,#0a111b)}button{background:#c7f36b;color:#11180b;border-color:#c7f36b}.brand span{color:#c7f36b}</style><style id="aicfa-layout-rebuild">
:root{--lime:#c7f36b;--teal:#61e3ce;--red:#ff7d91;--amber:#f5c36a}
.metric:before{content:"";position:absolute;left:0;top:0;bottom:0;width:2px;background:#34435b}.metric:first-child:before{background:var(--teal)}.metric .label{font-size:.6rem;letter-spacing:.07em;text-transform:uppercase}.metric .value{font-size:.93rem;font-weight:800}.dashboard{grid-template-columns:minmax(235px,.76fr) minmax(0,1.75fr) minmax(225px,.76fr);gap:12px}.dashboard-column{gap:9px;transition:grid-template-rows .2s}.panel{box-shadow:0 8px 25px #0002}.panel-title{font-size:.71rem;font-weight:800;letter-spacing:.07em}.accordion-trigger{cursor:pointer;user-select:none;min-height:40px;margin:-4px -4px 8px;padding:8px 9px;border-radius:8px;display:flex;align-items:center;justify-content:space-between;gap:8px}.accordion-trigger:hover{background:#172233;color:var(--lime)}.accordion-label{display:flex;align-items:center;gap:8px;min-width:0}.accordion-index{font-size:.6rem;color:var(--lime);background:#202b1a;border:1px solid #3c4b2b;padding:4px 5px;border-radius:5px}.accordion-chevron{display:grid;place-items:center;width:23px;height:23px;border:1px solid #344158;border-radius:6px}.incoming-panel.is-collapsed{align-self:start;min-height:0}.incoming-panel.is-collapsed .setup-list{display:none}.dashboard-column.intraday-collapsed{grid-template-rows:auto minmax(0,1fr)}.dashboard-column.scalp-collapsed{grid-template-rows:minmax(0,1fr) auto}.dashboard-column.both-collapsed{grid-template-rows:auto auto;align-content:start}.setup-card{border-radius:10px;background:linear-gradient(135deg,#111c2b,#0a111b)}.setup-card.selected{border-color:var(--lime);box-shadow:inset 3px 0 var(--lime)}.direction-long{color:var(--teal)}.direction-short{color:var(--red)}.setup-metric.rr strong{color:var(--amber)}.event b{color:var(--lime)}#chartPlaceholder{border:1px dashed #34435a;border-radius:13px;background:#0b111b}button:focus-visible,select:focus-visible,.accordion-trigger:focus-visible{outline:2px solid var(--teal);outline-offset:3px}
@media(max-width:1180px){.dashboard{grid-template-columns:minmax(220px,.8fr) minmax(0,1.6fr);gap:10px}}@media(max-width:760px){.dashboard{grid-template-columns:minmax(0,1fr);gap:9px}.dashboard-column{height:auto;min-height:0;grid-template-rows:auto auto;gap:8px}.dashboard-column.intraday-collapsed,.dashboard-column.scalp-collapsed,.dashboard-column.both-collapsed{grid-template-rows:auto auto}.incoming-panel{max-height:56vh}.incoming-panel.is-collapsed{max-height:none}.setup-list{max-height:48vh}.right-stack{grid-column:auto;grid-template-columns:minmax(0,1fr)}}@media(prefers-reduced-motion:reduce){*,*::before,*::after{transition:none!important}}
</style></head>
<body>
<header><div><div class="brand">AICFA<span>.</span></div><div class="sub">PERSONAL MARKET STRUCTURE TERMINAL</div></div><div class="controls"><div class="pill"><i class="led" id="led"></i><span id="connection">Подключение…</span></div><button id="changePassword" type="button">Сменить пароль</button><button id="logout" type="button">Выйти</button></div></header>
<main>
<div class="top"><div><h1>SMC Scanner</h1><div class="muted">Закрытые свечи · BOS/CHoCH · Order Blocks · FVG · Liquidity</div></div>
<div class="pill">Автосканер · все инструменты · scalp / intraday <span id="marketHoursStatus">Режим: shadow · часы рынка: проверка</span><span id="scannerStages" style="display:block;max-width:100%;font-size:11px;white-space:normal">Отсев по этапам: ожидание</span></div><div hidden><select id="symbol" aria-label="Инструмент"></select><select id="tf" aria-label="Таймфрейм"><option>1m</option><option>5m</option><option>15m</option><option>1h</option><option>4h</option></select></div></div>
<section class="grid">
<div class="metric"><div class="label">Поток Binance</div><div class="value" id="stream">—</div><div class="hint">статус соединения</div></div>
<div class="metric"><div class="label">Свечные серии</div><div class="value" id="series">—</div><div class="hint">ожидается 250</div></div>
<div class="metric"><div class="label">Закрытые свечи</div><div class="value" id="candleCount">—</div><div class="hint">хранимое окно</div></div>
<div class="metric"><div class="label">История</div><div class="value" id="history">—</div><div class="hint">начальная загрузка</div></div>
</section>
<section class="dashboard">
<div class="dashboard-column">
<section class="panel incoming-panel" id="intradayPanel"><div class="panel-title"><span>Сетапы · INTRADAY</span><span class="pill" id="intradayCount">0 актуальных</span></div><div class="setup-list" id="intradaySetups"><div class="empty">Ожидание intraday-сетапов…</div></div></section>
 <section class="panel incoming-panel" id="scalpPanel"><div class="panel-title"><span>Сетапы · SCALP</span><span class="pill" id="scalpCount">0 актуальных</span></div><div class="setup-list" id="scalpSetups"><div class="empty">Ожидание scalp-сетапов…</div></div></section>
</div>
<div class="chart-column">
<div class="panel empty" id="chartPlaceholder" style="padding:28px;text-align:center">Выберите входящий, принятый или реализованный сетап — здесь откроется его график.</div>
<div class="layout" id="setupChart" style="display:none">
<section class="panel"><div class="panel-title"><span id="chartTitle">Выберите сетап</span><span class="pill" id="lastPrice">Ожидание данных</span></div><div class="chart-wrap"><canvas id="chart" aria-label="График свечей"></canvas></div><div class="chart-note" id="chartNote">Загрузка закрытых свечей и расчёт разметки SMC…</div></section>
<aside class="panel"><div class="panel-title"><span>Сетап и SMC-разметка</span><span class="pill" id="annotationCount">—</span></div><div class="rows" id="stats"><div class="empty">Выберите сетап, чтобы увидеть его параметры и SMC-разметку.</div></div><div class="panel-title" style="margin-top:22px"><span>Последние события</span></div><div id="events"><div class="empty">Событий пока нет</div></div></aside>
</div>
</div>
<div class="right-stack">
<section class="panel"><div class="panel-title">Принятые сетапы</div><div id="activeSetups"><div class="empty">Пока нет принятых сетапов.</div></div></section>
<section class="panel journal-panel"><div class="panel-title"><span>Результаты стратегии</span><span class="pill" id="journalTradeCount">0 сделок</span></div><div class="journal-summary" id="journalSummary"><div class="journal-stat"><span>Чистый результат</span><strong>—</strong></div><div class="journal-stat"><span>Win rate</span><strong>—</strong></div><div class="journal-stat"><span>Profit Factor</span><strong>—</strong></div><div class="journal-stat"><span>Макс. просадка</span><strong>—</strong></div></div><div class="journal-filters"><button type="button" class="journal-filter active" data-journal-filter="all">Все</button><button type="button" class="journal-filter" data-journal-filter="scalp">SCALP</button><button type="button" class="journal-filter" data-journal-filter="intraday">INTRADAY</button><span id="journalAudit" class="journal-audit"></span></div><div id="realizedJournal"><div class="empty">Журнал пока пуст.</div></div></section>
</div>
</section>
<footer>Анализ выполняется только по закрытым свечам. Разметка не является торговой рекомендацией. Автоматический поиск сетапов по закрытым свечам всех инструментов. Исполнение сделок отключено.</footer>
</main>
<script>
const symbols=__AICFA_SYMBOLS__;const timeframes=__AICFA_TIMEFRAMES__;
const $=id=>document.getElementById(id);let selectedSetup=null;symbols.forEach(s=>{const o=document.createElement('option');o.value=s;o.textContent=s;$('symbol').append(o)});$('symbol').value=symbols.includes('BTCUSDT')?'BTCUSDT':symbols[0];timeframes.forEach(tf=>{const o=document.createElement('option');o.value=tf;o.textContent=tf;$('tf').append(o)});
function fmt(n){return n==null?'—':Number(n).toLocaleString('en-US',{maximumFractionDigits:8})}
function draw(data){const canvas=$('chart'),ctx=canvas.getContext('2d'),rect=canvas.getBoundingClientRect(),dpr=window.devicePixelRatio||1;canvas.width=Math.max(1,rect.width*dpr);canvas.height=Math.max(1,rect.height*dpr);ctx.scale(dpr,dpr);const w=rect.width,h=rect.height;ctx.clearRect(0,0,w,h);ctx.fillStyle='#0a1220';ctx.fillRect(0,0,w,h);const cs=data.candles||[];if(!cs.length){ctx.fillStyle='#8192aa';ctx.fillText('Ожидание свечей…',20,30);return}const view=cs.slice(-100),baseLo=Math.min(...view.map(c=>c.low)),baseHi=Math.max(...view.map(c=>c.high)),activeSetup=selectedSetup&&selectedSetup.symbol===$('symbol').value&&selectedSetup.timeframe===$('tf').value?selectedSetup:null,setupPrices=activeSetup?[...(activeSetup.zone||[]),activeSetup.confirmation_price,activeSetup.entry_limit,activeSetup.stop_price,...(activeSetup.targets||[])].filter(v=>v!=null&&Number.isFinite(Number(v))).map(Number):[],lo=Math.min(baseLo,...setupPrices),hi=Math.max(baseHi,...setupPrices),span=hi-lo||1,pad={l:10,r:64,t:16,b:24},cw=(w-pad.l-pad.r)/view.length;const y=p=>pad.t+(hi-p)/span*(h-pad.t-pad.b);ctx.strokeStyle='#1d2a3d';ctx.lineWidth=1;for(let i=0;i<5;i++){const yy=pad.t+i*(h-pad.t-pad.b)/4;ctx.beginPath();ctx.moveTo(pad.l,yy);ctx.lineTo(w-pad.r,yy);ctx.stroke();ctx.fillStyle='#7e90a9';ctx.font='10px system-ui';ctx.fillText(fmt(hi-i*span/4),w-pad.r+5,yy+3)}view.forEach((c,i)=>{const x=pad.l+i*cw+cw/2,up=c.close>=c.open;ctx.strokeStyle=up?'#59d6ad':'#f07883';ctx.fillStyle=ctx.strokeStyle;ctx.beginPath();ctx.moveTo(x,y(c.high));ctx.lineTo(x,y(c.low));ctx.stroke();const top=y(Math.max(c.open,c.close)),bot=y(Math.min(c.open,c.close));ctx.fillRect(x-Math.max(1,cw*.29),top,Math.max(2,cw*.58),Math.max(1,bot-top))});const ann=data.annotations||{},offset=cs.length-view.length;const zone=(items,color)=>{for(const z of items||[]){const start=Number(z.candle_index??z.first_candle_index??z.confirmation_index)-offset;if(start>=view.length||start< -view.length)continue;const x0=pad.l+Math.max(0,start)*cw, x1=w-pad.r,top=y(Number(z.upper)),bottom=y(Number(z.lower));if(Number.isFinite(top)&&Number.isFinite(bottom)){ctx.fillStyle=color;ctx.fillRect(x0,Math.min(top,bottom),Math.max(1,x1-x0),Math.max(1,Math.abs(bottom-top)))}}};zone((ann.order_blocks||[]).filter(z=>!z.mitigated),'rgba(99,130,255,.12)');zone((ann.fvg||[]).filter(z=>!z.fully_filled),'rgba(89,214,173,.12)');for(const e of ann.structure_breaks||[]){const i=Number(e.candle_index)-offset;if(i<0||i>=view.length)continue;const yy=y(Number(e.level));ctx.strokeStyle=e.kind==='CHoCH'?'#f4bd62':'#9aabff';ctx.setLineDash([3,3]);ctx.beginPath();ctx.moveTo(pad.l+i*cw,yy);ctx.lineTo(w-pad.r,yy);ctx.stroke();ctx.setLineDash([]);ctx.fillStyle=ctx.strokeStyle;ctx.font='10px system-ui';ctx.fillText(e.kind+' '+e.direction,pad.l+i*cw+3,Math.max(11,yy-4))}for(const e of ann.sweeps||[]){const i=Number(e.candle_index)-offset;if(i<0||i>=view.length)continue;const yy=y(Number(e.level));ctx.fillStyle='#f4bd62';ctx.beginPath();ctx.arc(pad.l+i*cw+cw/2,yy,3,0,Math.PI*2);ctx.fill()}const last=view[view.length-1];ctx.strokeStyle='#e6bc6d';ctx.setLineDash([4,4]);ctx.beginPath();ctx.moveTo(pad.l,y(last.close));ctx.lineTo(w-pad.r,y(last.close));ctx.stroke();ctx.setLineDash([]);
if(activeSetup){const z=(activeSetup.zone||[]).map(Number);if(z.length===2&&z.every(Number.isFinite)){const zy1=y(Math.max(...z)),zy2=y(Math.min(...z));ctx.fillStyle=activeSetup.direction==='long'?'rgba(89,214,173,.13)':'rgba(240,120,131,.13)';ctx.fillRect(pad.l,zy1,w-pad.l-pad.r,Math.max(1,zy2-zy1));ctx.strokeStyle=activeSetup.direction==='long'?'#59d6ad':'#f07883';ctx.setLineDash([5,3]);ctx.strokeRect(pad.l,zy1,w-pad.l-pad.r,Math.max(1,zy2-zy1));ctx.setLineDash([]);ctx.fillStyle=ctx.strokeStyle;ctx.font='10px system-ui';ctx.fillText('SMC '+activeSetup.direction.toUpperCase()+' ZONE',pad.l+4,Math.max(11,zy1-4))}const setupTime=Number(activeSetup.confirmation_time_ms),confirmIndex=view.findIndex((c,i)=>Number(c.timestamp_ms)<=setupTime&&(i===view.length-1||Number(view[i+1].timestamp_ms)>setupTime));if(confirmIndex>=0){const xx=pad.l+confirmIndex*cw+cw/2;ctx.strokeStyle='#e6bc6d';ctx.setLineDash([2,4]);ctx.beginPath();ctx.moveTo(xx,pad.t);ctx.lineTo(xx,h-pad.b);ctx.stroke();ctx.setLineDash([]);const ey=y(Number(activeSetup.confirmation_price));ctx.fillStyle='#e6bc6d';ctx.beginPath();if(activeSetup.direction==='long'){ctx.moveTo(xx,ey-7);ctx.lineTo(xx-5,ey+2);ctx.lineTo(xx+5,ey+2)}else{ctx.moveTo(xx,ey+7);ctx.lineTo(xx-5,ey-2);ctx.lineTo(xx+5,ey-2)}ctx.closePath();ctx.fill()}const levels=[['Вход',activeSetup.confirmation_price,'#e6bc6d'],['Лимит',activeSetup.entry_limit,'#a9b8ff'],['SL',activeSetup.stop_price,'#f07883'],['TP1',(activeSetup.targets||[])[0],'#59d6ad'],['TP2',(activeSetup.targets||[])[1],'#59d6ad'],['TP3',(activeSetup.targets||[])[2],'#59d6ad']];for(const [label,price,color] of levels){const p=Number(price);if(!Number.isFinite(p)||price==null)continue;const yy=y(p);ctx.strokeStyle=color;ctx.setLineDash(label==='SL'?[4,3]:[2,3]);ctx.beginPath();ctx.moveTo(pad.l,yy);ctx.lineTo(w-pad.r,yy);ctx.stroke();ctx.setLineDash([]);ctx.fillStyle=color;ctx.font='10px system-ui';ctx.fillText(label+' '+fmt(p),pad.l+4,Math.max(11,yy-4))}}}
function openSetup(s){selectedSetup=s;$("symbol").value=s.symbol;$("tf").value=s.timeframe||"1m";$("chartPlaceholder").style.display="none";$("setupChart").style.display="grid";load()}
function row(label,value){const d=document.createElement('div');d.className='rowitem';const a=document.createElement('span');a.textContent=label;const b=document.createElement('strong');b.textContent=value;d.append(a,b);$('stats').append(d)}
async function loadStatus(){try{const st=await fetch('/api/data-status').then(r=>r.json());const connected=st.groups?.tradfi?.status==='connected'&&st.groups?.crypto?.status==='connected';$('connection').textContent=connected?'Поток активен':'Проверка потока';$('led').style.background=connected?'#59d6ad':'#f4bd62';$('stream').textContent=connected?'CONNECTED':'CONNECTING';$('series').textContent=fmt(st.latest_series);$('candleCount').textContent=fmt(st.stored_candles);$('history').textContent=st.history?.status||'—';return st}catch(e){$('connection').textContent='Ошибка статуса';console.error('Could not load market status',e);return null}}
async function load(){if(!selectedSetup)return;const symbol=$('symbol').value,tf=$('tf').value;$('chartTitle').textContent=symbol+' · '+tf;try{const an=await fetch('/api/smc-analysis/'+encodeURIComponent(symbol)+'/'+encodeURIComponent(tf)).then(r=>r.json());if(an.status!=='ok'){$('chartNote').textContent='Ряд прогревается: '+(an.candles||0)+' свечей';draw({candles:[]});return}draw(an);const cs=an.candles,last=cs[cs.length-1];$('lastPrice').textContent=fmt(last.close);$('chartNote').textContent='Свечей: '+cs.length+' · последнее закрытие: '+new Date(last.timestamp_ms).toLocaleString();const a=an.annotations;$('annotationCount').textContent=String(a.swings.length+a.structure_breaks.length+a.order_blocks.length+a.fvg.length+a.liquidity_levels.length+a.sweeps.length);$('stats').replaceChildren();row('Последняя цена',fmt(last.close));row('Premium / Discount',a.premium_discount||'Нет подтверждённого диапазона');row('ATR(14)',fmt(a.atr));row('Средний объём',fmt(a.average_volume));row('Swing points',String(a.swings.length));row('BOS / CHoCH',String(a.structure_breaks.length));row('Order Blocks',String(a.order_blocks.length));row('FVG',String(a.fvg.length));row('Liquidity levels',String(a.liquidity_levels.length));row('Sweeps',String(a.sweeps.length));const ev=[...a.structure_breaks.map(x=>({t:x.timestamp_ms,label:x.kind+' · '+x.direction+' · '+fmt(x.level)})),...a.sweeps.map(x=>({t:x.timestamp_ms,label:'Sweep '+x.direction+' · '+fmt(x.level)}))].sort((x,y)=>y.t-x.t).slice(0,6);$('events').replaceChildren();if(!ev.length){$('events').innerHTML='<div class="empty">На текущем окне событий нет</div>'}else ev.forEach(e=>{const d=document.createElement('div');d.className='event';const b=document.createElement('b');b.textContent=new Date(e.t).toLocaleTimeString();d.append(b,document.createTextNode('  '+e.label));$('events').append(d)})}catch(e){$('connection').textContent='Ошибка API';$('chartNote').textContent='Не удалось получить анализ. Проверьте статус сервиса.';console.error(e)}}
$('symbol').addEventListener('change',load);$('tf').addEventListener('change',load);async function loadSetups(){try{const r=await fetch('/api/setups');if(!r.ok)return;const data=await r.json();if($('marketHoursStatus')){const sd=data.scanner_diagnostics||{};const scanTime=data.last_scan_time_ms?new Date(data.last_scan_time_ms).toLocaleTimeString():'ожидание свечи';$('marketHoursStatus').textContent='Режим: '+(data.scanner_mode||'shadow')+' · часы рынка: '+(data.market_hours?data.market_hours.mapped+'/'+data.market_hours.total:'проверка')+' · скан-проверок: '+(sd.events||0)+' · последняя: '+scanTime+' · ошибки: '+(sd.errors||0)+(sd.last_error?' ('+sd.last_error+')':'')+' · ТФ последнего символа: '+(sd.last_ready_series||0)+'/5';const totals=sd.total_stage_counts||{};const top=Object.entries(totals).sort((a,b)=>b[1]-a[1]);if($('scannerStages'))$('scannerStages').textContent='Отсев по этапам: '+(top.length?top.map(([k,v])=>k+'='+v).join(' · '):'данных пока нет');}const reasonLabels={pac_htf_structure_bias:'Направление старшего ТФ',pac_ob_zone:'Order Block (OB)',pac_fvg_zone:'Fair Value Gap (FVG)',pac_zone_retest_or_nearby:'Повторный тест / близость к зоне',pac_atr_stop:'Стоп по ATR',pac_target_and_rr:'Цель и соотношение риск/прибыль',pac_trigger_structure_aligned:'Структура подтверждения совпадает',pac_internal_structure_aligned:'Внутренняя структура совпадает',pac_liquidity_sweep_confluence:'Снятие ликвидности',pac_premium_discount_confluence:'Premium / Discount совпадает',pac_shadow_candidate:'Кандидат в shadow-режиме',cooldown_active:'Повторный сигнал в период паузы',pac_invalid_risk_target_or_rr:'Некорректный риск или цель',tp1_target_missing:'Не найдена цель TP1',tick_size_unavailable:'Нет шага цены',confirmation_data_missing:'Нет данных подтверждения',market_hours_unverified:'Не подтверждены часы рынка',tradfi_market_closed:'Рынок закрыт'};const readableReason=k=>reasonLabels[k]||String(k).replaceAll('_',' ');const renderList=(hostId,countId,items,emptyText)=>{const host=$(hostId);if(!host)return;host.replaceChildren();const count=$(countId);if(!items.length){host.innerHTML='<div class="empty">'+emptyText+'</div>';return}for(const setup of items){try{const d=document.createElement('article');d.className='setup-card'+(selectedSetup&&selectedSetup.key===setup.key?' selected':'');d.tabIndex=0;d.setAttribute('role','button');d.setAttribute('aria-label','Открыть '+setup.symbol+' '+setup.direction);const head=document.createElement('div');head.className='setup-card-head';const title=document.createElement('div');const symbol=document.createElement('div');symbol.className='setup-card-title';symbol.textContent=setup.symbol;const sub=document.createElement('div');sub.className='setup-card-sub';sub.textContent=String(setup.profile||'').toUpperCase()+' · '+(setup.timeframe||'—');title.append(symbol,sub);const badges=document.createElement('div');badges.style.cssText='display:flex;align-items:center;gap:5px;flex-wrap:wrap;justify-content:flex-end';const direction=document.createElement('span');direction.className='direction-pill '+(setup.direction==='long'?'direction-long':'direction-short');direction.textContent=String(setup.direction||'').toUpperCase();const status=document.createElement('span');status.className='setup-status';status.textContent=setup.status==='CANDIDATE'?'КАНДИДАТ':setup.status==='REJECTED'?'ОТКЛОНЁН':String(setup.status||'');badges.append(direction,status);head.append(title,badges);d.append(head);const metrics=document.createElement('div');metrics.className='setup-metrics';const metric=(label,value,extra='')=>{const m=document.createElement('div');m.className='setup-metric '+extra;const l=document.createElement('span');l.textContent=label;const v=document.createElement('strong');v.textContent=value;m.append(l,v);metrics.append(m)};metric('Вход',fmt(setup.entry_limit??setup.confirmation_price));metric('Стоп · SL',fmt(setup.stop_price));metric('Цель · TP1',fmt((setup.targets||[])[0]));metric('Risk / Reward',setup.risk_reward==null?'—':fmt(setup.risk_reward)+'R','rr');d.append(metrics);const time=document.createElement('div');time.className='setup-time';const expires=setup.expires_at_ms?new Date(setup.expires_at_ms).toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'}):null;time.textContent=(setup.confirmation_time_ms?new Date(setup.confirmation_time_ms).toLocaleString():'Время неизвестно')+(expires?' · срок до '+expires:'')+' · скор '+(setup.score??'—')+'/10';d.append(time);const details=document.createElement('details');details.className='setup-details';details.addEventListener('click',e=>e.stopPropagation());const summary=document.createElement('summary');summary.textContent='Подробности стратегии';details.append(summary);const reasons=[...(setup.reasons||[]),...(setup.decision_reasons||[])];if(reasons.length){const tags=document.createElement('div');tags.className='reason-list';for(const reason of [...new Set(reasons)]){const tag=document.createElement('span');tag.className='reason-tag';tag.textContent=readableReason(reason);tags.append(tag)}details.append(tags)}else{const p=document.createElement('div');p.className='setup-time';p.textContent='Дополнительных пояснений нет';details.append(p)}d.append(details);const choose=()=>openSetup(setup);d.addEventListener('click',choose);d.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();choose()}});host.append(d)}catch(cardError){console.error('Could not render setup card',setup&&setup.key,cardError)}}if(count)count.textContent=String(host.querySelectorAll('.setup-card').length)+' актуальных'};const incoming=(data.candidates||[]).filter(x=>['scalp','intraday'].includes(String(x.profile||'').toLowerCase())&&typeof x.key==='string'&&x.key.length>0).sort((a,b)=>(Number(b.score)||0)-(Number(a.score)||0)||(Number(b.confirmation_time_ms)||0)-(Number(a.confirmation_time_ms)||0));const intraday=incoming.filter(x=>String(x.profile||'').toLowerCase()==='intraday');const scalp=incoming.filter(x=>String(x.profile||'').toLowerCase()==='scalp');renderList('intradaySetups','intradayCount',intraday,'Входящих intraday-сетапов пока нет.');renderList('scalpSetups','scalpCount',scalp,'Входящих scalp-сетапов пока нет.');}catch(e){console.error('Could not load setup candidates',e)}}
async function loadActive(){try{const r=await fetch('/api/active-setups');if(!r.ok)return;const data=await r.json();const host=$('activeSetups');host.replaceChildren();if(!data.setups.length){host.innerHTML='<div class="empty">Пока нет принятых сетапов.</div>';return}for(const s of data.setups){const d=document.createElement('div');d.className='event';d.textContent=s.symbol+' · '+s.profile+' · '+s.direction+' · '+s.status+' · вход '+fmt(s.confirmation_price)+' · стоп '+fmt(s.stop_price)+' · TP '+s.targets.map(fmt).join(' / ');d.style.cursor='pointer';d.addEventListener('click',()=>openSetup(s));host.append(d)}}catch(e){console.error(e)}}
let journalTrades=[],journalFilter='all';function renderJournal(){const all=journalTrades.filter(t=>journalFilter==='all'||String(t.profile||'').toLowerCase()===journalFilter);const sane=all.filter(t=>Number.isFinite(Number(t.net_r))&&Number.isFinite(Number(t.gross_r))&&Number.isFinite(Number(t.commission_r))&&Number(t.commission_r)>=0&&Number(t.commission_r)<=5);const anomalies=all.length-sane.length;const wins=sane.filter(t=>Number(t.net_r)>0).length;const net=sane.reduce((s,t)=>s+Number(t.net_r),0),gp=sane.filter(t=>Number(t.net_r)>0).reduce((s,t)=>s+Number(t.net_r),0),gl=Math.abs(sane.filter(t=>Number(t.net_r)<0).reduce((s,t)=>s+Number(t.net_r),0));let peak=0,curve=0,dd=0;for(const t of [...sane].sort((a,b)=>Number(a.closed_at_ms)-Number(b.closed_at_ms))){curve+=Number(t.net_r);peak=Math.max(peak,curve);dd=Math.max(dd,peak-curve)}const pf=gl?gp/gl:(gp>0?'∞':'—');const vals=[['Чистый результат',net.toFixed(2)+'R',net>=0],['Win rate',sane.length?(100*wins/sane.length).toFixed(1)+'%':'—',null],['Profit Factor',typeof pf==='number'?pf.toFixed(2):pf,null],['Макс. просадка',dd.toFixed(2)+'R',false]];$('journalSummary').replaceChildren();for(const [label,value,pos] of vals){const box=document.createElement('div');box.className='journal-stat';const l=document.createElement('span');l.textContent=label;const v=document.createElement('strong');v.textContent=value;if(pos!==null)v.style.color=pos?'#83dfb0':'#ff8c91';box.append(l,v);$('journalSummary').append(box)}$('journalTradeCount').textContent=sane.length+' проверенных';$('journalAudit').textContent=anomalies?anomalies+' аномалий исключено из метрик':'аномалий не найдено';const host=$('realizedJournal');host.replaceChildren();if(!all.length){host.innerHTML='<div class="empty">Нет сделок для выбранного фильтра.</div>';return}for(const t of all){const d=document.createElement('div');d.className='journal-trade';d.tabIndex=0;d.setAttribute('role','button');const n=Number(t.net_r),fee=Number(t.commission_r),bad=!Number.isFinite(n)||!Number.isFinite(fee)||fee<0||fee>5;const h=document.createElement('div');h.className='journal-trade-head';const name=document.createElement('span');name.textContent=t.symbol+' · '+String(t.profile||'').toUpperCase()+' · '+String(t.direction||'').toUpperCase();const result=document.createElement('span');result.className='journal-net '+(n>=0?'positive':'negative');result.textContent=Number.isFinite(n)?(n>0?'+':'')+n.toFixed(2)+'R':'—';h.append(name,result);const f=document.createElement('div');f.className='journal-trade-foot';const status=document.createElement('span');status.textContent=String(t.final_status||'').replaceAll('_',' ');const details=document.createElement('span');details.textContent='Gross '+(Number(t.gross_r)||0).toFixed(2)+'R · комиссия '+(Number.isFinite(fee)?fee.toFixed(3):'—')+'R';f.append(status,details);d.append(h,f);if(bad){const w=document.createElement('div');w.className='journal-warning';w.textContent='Аномальная комиссия/результат — исключено из сводной статистики до проверки';d.append(w)}const open=()=>openSetup(t);d.addEventListener('click',open);d.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();open()}});host.append(d)}}async function loadJournal(){try{const r=await fetch('/api/journal');if(!r.ok)return;const data=await r.json();journalTrades=Array.isArray(data.trades)?data.trades:[];renderJournal()}catch(e){console.error(e)}}document.querySelectorAll('[data-journal-filter]').forEach(b=>b.addEventListener('click',()=>{journalFilter=b.dataset.journalFilter;document.querySelectorAll('[data-journal-filter]').forEach(x=>x.classList.toggle('active',x===b));renderJournal()}));
window.addEventListener('resize',()=>{if(selectedSetup)load()});loadStatus();loadSetups();loadActive();loadJournal();let firstClosedCandleStatusLoaded=false;const eventSource=new EventSource('/api/events');eventSource.onmessage=e=>{try{const event=JSON.parse(e.data);if(event.type==='setup_candidate'){loadStatus();loadSetups();loadActive()}if(event.type==='setup_lifecycle'){loadStatus();loadSetups();loadActive();loadJournal()}if(event.type==='closed_candle'){if(!firstClosedCandleStatusLoaded){firstClosedCandleStatusLoaded=true;loadStatus()}if(selectedSetup&&event.symbol===selectedSetup.symbol&&event.timeframe===selectedSetup.timeframe){load()}}}catch(err){console.error('Invalid scanner event',err)}};eventSource.onerror=()=>{$('connection').textContent='Восстановление потока событий'};$('logout').addEventListener('click',async()=>{await fetch('/api/auth/logout',{method:'POST'});location.href='/login'});$('changePassword').addEventListener('click',async()=>{const current_password=prompt('Текущий пароль');if(current_password===null)return;const new_password=prompt('Новый пароль (минимум 12 символов)');if(new_password===null)return;const r=await fetch('/api/settings/password',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({current_password,new_password})});alert(r.ok?'Пароль изменён. Войдите заново при следующем входе.':'Не удалось сменить пароль. Проверьте текущий пароль и длину нового.');});

(function(){const col=document.querySelector('.dashboard-column');if(!col)return;const ids=['intradayPanel','scalpPanel'];ids.forEach((id,i)=>{const p=document.getElementById(id),t=p.querySelector('.panel-title'),pill=t.querySelector('.pill'),label=document.createElement('span'),num=document.createElement('span'),name=document.createElement('span'),right=document.createElement('span'),icon=document.createElement('span');t.classList.add('accordion-trigger');t.setAttribute('role','button');t.setAttribute('tabindex','0');t.setAttribute('aria-expanded','true');t.setAttribute('aria-controls',id==='intradayPanel'?'intradaySetups':'scalpSetups');label.className='accordion-label';num.className='accordion-index';num.textContent=i?'02':'01';name.textContent=i?'SCALP · короткие':'INTRADAY · среднесрочные';label.append(num,name);right.className='accordion-label';icon.className='accordion-chevron';icon.textContent='−';right.append(pill,icon);t.replaceChildren(label,right);function toggle(){const open=t.getAttribute('aria-expanded')==='true';if(open){p.classList.add('is-collapsed');t.setAttribute('aria-expanded','false');icon.textContent='+'}else{ids.forEach(other=>{const op=document.getElementById(other),ot=op.querySelector('.panel-title'),oi=ot.querySelector('.accordion-chevron'),closed=other!==id;op.classList.toggle('is-collapsed',closed);ot.setAttribute('aria-expanded',String(!closed));oi.textContent=closed?'+':'−'})}col.classList.toggle('intraday-collapsed',document.getElementById(ids[0]).classList.contains('is-collapsed'));col.classList.toggle('scalp-collapsed',document.getElementById(ids[1]).classList.contains('is-collapsed'));col.classList.toggle('both-collapsed',ids.every(x=>document.getElementById(x).classList.contains('is-collapsed')));window.dispatchEvent(new Event('resize'))}t.addEventListener('click',toggle);t.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();toggle()}})});const initial=document.getElementById('scalpPanel'),it=initial.querySelector('.panel-title');initial.classList.add('is-collapsed');it.setAttribute('aria-expanded','false');it.querySelector('.accordion-chevron').textContent='+';col.classList.add('scalp-collapsed')})();</script></body></html>
"""
PAGE = PAGE.replace("__AICFA_SYMBOLS__", json.dumps(ALL_SYMBOLS)).replace("__AICFA_TIMEFRAMES__", json.dumps(TIMEFRAMES))


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    return HTMLResponse(PAGE)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "aicfa"}


@app.get("/api/data-status")
async def data_status() -> dict:
    """Live ingestion health; this does not imply SMC signals are available."""
    return market_data.status()


@app.get("/api/events")
async def event_stream(request: Request):
    """Push closed-candle events to the browser without periodic API polling."""
    async def stream():
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=100)
        _event_subscribers.add(queue)
        try:
            yield "retry: 3000\n"
            while not await request.is_disconnected():
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=20)
                    yield f"data: {item}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            _event_subscribers.discard(queue)
    return StreamingResponse(stream(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"})




@app.get("/api/smc-analysis/{symbol}/{timeframe}")
async def smc_analysis(symbol: str, timeframe: str) -> dict:
    """Return causal, chart-ready SMC annotations for the latest closed-candle window."""
    normalized_symbol = symbol.upper()
    if normalized_symbol not in ALL_SYMBOLS:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="unknown instrument")
    if timeframe not in TIMEFRAMES:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="unknown timeframe")
    series = tuple(market_data.candles.get((normalized_symbol, timeframe), ()))
    cached = _analysis_cache.get((normalized_symbol, timeframe))
    if cached and series and cached["candles"][-1]["timestamp_ms"] == series[-1].open_time_ms:
        return cached
    if len(series) < 3:
        return {
            "status": "warming_up",
            "symbol": normalized_symbol,
            "timeframe": timeframe,
            "candles": len(series),
            "required_minimum": 3,
            "annotations": None,
        }
    analysis = await asyncio.to_thread(
        analyze_smc,
        [float(c.open) for c in series],
        [float(c.high) for c in series],
        [float(c.low) for c in series],
        [float(c.close) for c in series],
        [float(c.volume) for c in series],
        [c.open_time_ms for c in series],
    )
    payload = to_chart_payload(analysis, [c.open_time_ms for c in series])
    return {
        "status": "ok",
        "symbol": normalized_symbol,
        "timeframe": timeframe,
        "candles_count": len(series),
        "candles": [{
            "timestamp_ms": c.open_time_ms,
            "open": float(c.open),
            "high": float(c.high),
            "low": float(c.low),
            "close": float(c.close),
            "volume": float(c.volume),
        } for c in series],
        "annotations": payload,
    }


def _latest_unique_candidates(candidates: list[dict]) -> list[dict]:
    """Keep newest symbol/profile candidate and expose its profile TTL deadline."""
    latest: dict[tuple[str, str], dict] = {}
    for candidate in candidates:
        key = (str(candidate.get("symbol", "")), str(candidate.get("profile", "")))
        previous = latest.get(key)
        if previous is None or int(candidate.get("confirmation_time_ms", 0)) > int(previous.get("confirmation_time_ms", 0)):
            latest[key] = candidate
    result = []
    for candidate in latest.values():
        item = dict(candidate)
        lifetime_hours = 3 if str(item.get("profile", "")).lower() == "scalp" else 12
        item["expires_at_ms"] = int(item.get("confirmation_time_ms", 0)) + lifetime_hours * 3_600_000
        result.append(item)
    return sorted(
        result,
        key=lambda item: (int(item.get("score", 0)), int(item.get("confirmation_time_ms", 0))),
        reverse=True,
    )


@app.get("/api/setups")
async def setup_candidates() -> dict:
    """Current incoming candidates; rejected decisions are not persisted or returned."""
    status = market_data.status()
    connected = status.get("groups", {}).get("tradfi", {}).get("status") == "connected" and status.get("groups", {}).get("crypto", {}).get("status") == "connected"
    return {"status": "running" if connected else "warming_up",
            "last_scan_time_ms": _scanner_last_event_ms,
            "scanner_diagnostics": {
                "events": _scanner_event_count,
                "errors": _scanner_error_count,
                "last_error": _scanner_last_error,
                "last_candidate_count": _scanner_last_candidate_count,
                "last_ready_series": _scanner_last_ready_series,
                "last_stage_counts": dict(_scanner_last_rejections),
                "total_stage_counts": dict(_scanner_rejection_totals),
            },
            "scanner_mode": "live" if SCANNER_LIVE_ENABLED else "shadow",
            "live_acceptance_enabled": SCANNER_LIVE_ENABLED,
            "exchange_metadata": status.get("exchange_metadata", {}),
            "active_count": _get_setup_store().active_count(),
            "market_hours": {
                "mapped": len((US_EQUITY_SYMBOLS | KRX_EQUITY_SYMBOLS | COMMODITY_SYMBOLS) & set(TRADFI_SYMBOLS)),
                "total": len(TRADFI_SYMBOLS),
                "unmapped": sorted(set(TRADFI_SYMBOLS) - US_EQUITY_SYMBOLS - KRX_EQUITY_SYMBOLS - COMMODITY_SYMBOLS),
            },
            "candidates": _latest_unique_candidates(_get_setup_store().list_candidates(include_rejected=False))}


@app.get("/api/active-setups")
async def active_setups() -> dict:
    return {"setups": _get_setup_store().list_active()}


@app.get("/api/journal")
async def realized_journal() -> dict:
    return {"trades": _get_setup_store().list_journal()}


@app.get("/api/backup-status")
async def backup_health() -> dict:
    """Expose the last verified backup result without leaking filesystem paths."""
    return dict(backup_status)
