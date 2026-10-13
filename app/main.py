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
from app.market_hours import COMMODITY_SYMBOLS, KRX_EQUITY_SYMBOLS, US_EQUITY_SYMBOLS, tradfi_market_is_open
from app.smc.presentation import to_chart_payload
from app.smc.scanner import scan_symbol
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
    for setup in store.list_active():
        if candle.symbol != setup.get("symbol") or now_ms <= max(int(setup.get("confirmation_time_ms", 0)), int(setup.get("last_event_time_ms", 0))):
            continue
        payload = dict(setup)
        direction = payload["direction"]
        entry = float(payload["confirmation_price"])
        original_stop = float(payload["stop_price"])
        targets = [float(x) for x in payload.get("targets", [])]
        if len(targets) < 3:
            continue
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
                remaining = 0.5 if status == "TP1" else 0.2
                commission_r += remaining * COMMISSION_RATE_PER_SIDE * (entry + stop) / risk
            payload.update({"status": "SL", "gross_r": gross_r, "commission_r": commission_r})
            _finish_setup(payload, store, now_ms, "SL", publish=publish)
            continue
        stages = {"ACCEPTED": 0, "TP1": 1, "TP2": 2}
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
        for idx in range(stage, 3):
            target = targets[idx]
            hit = high >= target if direction == "long" else low <= target
            if not hit:
                break
            weight = (0.5, 0.3, 0.2)[idx]
            gross_r += weight * ((target - entry) if direction == "long" else (entry - target)) / risk
            commission_r += weight * COMMISSION_RATE_PER_SIDE * (entry + target) / risk
            reached.append(idx + 1)
        if not reached:
            if expired:
                remaining = 1.0 if status == "ACCEPTED" else 0.5 if status == "TP1" else 0.2
                gross_r += remaining * ((close - entry) if direction == "long" else (entry - close)) / risk
                commission_r += remaining * COMMISSION_RATE_PER_SIDE * (entry + close) / risk
                payload.update({"status": "EXPIRED", "gross_r": gross_r, "commission_r": commission_r})
                _finish_setup(payload, store, now_ms, "EXPIRED", publish=publish)
            continue
        last = reached[-1]
        payload.update({"gross_r": gross_r, "commission_r": commission_r, "last_event_time_ms": now_ms})
        if last == 3:
            payload["status"] = "CLOSED"
            _finish_setup(payload, store, now_ms, "TP3", publish=publish)
        else:
            payload["status"] = f"TP{last}"
            if store.transition(payload["key"], payload, event_type=f"TP{last}", event_time_ms=now_ms) and publish:
                _publish_event({"type": "setup_lifecycle", "setup": payload})
            if expired:
                remaining = 0.5 if last == 1 else 0.2
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
    for setup in _get_setup_store().list_active():
        if setup.get("symbol") != candle.symbol or setup.get("status") != "ACCEPTED" or setup.get("timeframe") != candle.timeframe:
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
    global _scanner_last_event_ms
    _advance_active_setups(candle)
    await _invalidate_on_opposite_choch(candle)
    if candle.timeframe in {"5m", "15m"}:
        _scanner_last_event_ms = candle.close_time_ms
        snapshot = {tf: tuple(x for x in market_data.candles.get((candle.symbol, tf), ()) if x.close_time_ms <= candle.close_time_ms) for tf in TIMEFRAMES}
        try:
            candidates = await asyncio.to_thread(scan_symbol, candle.symbol, snapshot, trigger_timeframe=candle.timeframe)
            for candidate in candidates:
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
                if len(candidate.targets) < 3:
                    payload["status"] = "REJECTED"
                    payload["decision_reasons"] = ["three_confirmed_targets_required"]
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
                    payload["status"] = ("ACCEPTED" if SCANNER_LIVE_ENABLED else "CANDIDATE") if decision.status == "ELIGIBLE" else decision.status
                    if decision.status == "ELIGIBLE" and not SCANNER_LIVE_ENABLED:
                        payload["decision_reasons"].append("live_acceptance_disabled_until_phase1_accepted")
                saved, payload = _get_setup_store().save_decision(
                    payload, cooldown_minutes=30 if candidate.profile == "scalp" else 120, max_active=8
                )
                if saved:
                    _setup_candidates[candidate.key] = payload
                    _publish_event({"type": "setup_candidate", "setup": payload})
        except Exception:
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
    active = _get_setup_store().list_active()
    if not active:
        return
    symbols = {str(setup["symbol"]) for setup in active}
    candles = []
    for symbol in symbols:
        candles.extend(market_data.candles.get((symbol, "1m"), ()))
    for candle in sorted(candles, key=lambda item: item.close_time_ms):
        _advance_active_setups(candle, publish=False)


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
    try:
        yield
    finally:
        backup_task.cancel()
        await asyncio.gather(backup_task, return_exceptions=True)
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
<style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#080d18;color:#e8eef8;font:16px system-ui}.box{width:min(90vw,400px);padding:28px;background:#101a2a;border:1px solid #293851;border-radius:16px}input,button{box-sizing:border-box;width:100%;padding:12px;margin:6px 0 14px;background:#0b1321;color:#e8eef8;border:1px solid #2a3a53;border-radius:8px}button{background:#17352f}p{color:#a8b8ce}</style></head><body><main class="box"><h1>AICFA</h1><p id="intro">Проверка…</p><form id="login"><label>Пароль</label><input id="password" type="password" autocomplete="current-password" required><button>Войти</button></form><form id="setup" hidden><label>Токен настройки</label><input id="token" type="password" required><label>Новый пароль (от 12 символов)</label><input id="newpass" type="password" minlength="12" required><button>Установить пароль</button></form><p id="msg" role="status"></p></main><script>
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
:root{color-scheme:dark;font-family:Inter,ui-sans-serif,system-ui,sans-serif;background:#080d18;color:#e8eef8}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(ellipse at 15% 0%,#14243b 0,transparent 42%),#080d18;min-height:100vh}
header{display:flex;justify-content:space-between;align-items:center;padding:20px clamp(16px,4vw,48px);border-bottom:1px solid #1f2a3d;gap:16px;flex-wrap:wrap}
.brand{font-size:1.35rem;font-weight:800;letter-spacing:.08em}.brand span{color:#63e6be}.sub{color:#8292aa;font-size:.8rem;margin-top:4px}
.pill{border:1px solid #293851;border-radius:999px;padding:8px 12px;color:#a9bad1;font-size:.8rem}.led{display:inline-block;width:7px;height:7px;border-radius:50%;background:#f4bd62;margin-right:8px}
main{max-width:1500px;margin:auto;padding:26px clamp(16px,4vw,48px) 48px}.top{display:flex;justify-content:space-between;align-items:end;gap:20px;flex-wrap:wrap;margin-bottom:22px}
h1{font-size:clamp(1.8rem,4vw,2.7rem);letter-spacing:-.04em;margin:0 0 8px}.muted{color:#8fa0b8}.controls{display:flex;gap:8px;flex-wrap:wrap}
select,button{background:#111c2d;border:1px solid #2a3a53;color:#e8eef8;padding:11px 13px;border-radius:10px;font:inherit}button{cursor:pointer;background:#17352f;border-color:#286456}button:hover{background:#1d493e}
.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-bottom:14px}.metric,.panel{background:linear-gradient(145deg,#111b2b,#0d1523);border:1px solid #202e43;border-radius:15px;padding:17px}
.metric .label{font-size:.78rem;color:#8fa0b8}.metric .value{font-size:1.45rem;font-weight:750;margin-top:8px;overflow-wrap:anywhere}.metric .hint{font-size:.76rem;color:#70839f;margin-top:4px}
.layout{display:grid;grid-template-columns:minmax(0,1fr);gap:14px}.dashboard{display:grid;grid-template-columns:minmax(240px,.78fr) minmax(0,2fr) minmax(260px,.82fr);gap:14px;align-items:start}.dashboard-column{display:grid;gap:14px;min-width:0}.dashboard .panel{min-width:0;margin:0!important}.incoming-panel{max-height:calc(100vh - 28px);overflow:auto;position:sticky;top:14px}.right-stack{display:grid;gap:14px;min-width:0}.chart-column{min-width:0}.chart-column #setupChart{grid-template-columns:minmax(0,1fr)}.chart-column #setupChart aside{margin-top:0}.panel-title{display:flex;justify-content:space-between;gap:10px;align-items:center;margin-bottom:15px;font-weight:700}.chart-wrap{height:390px;position:relative}.chart-wrap canvas{width:100%;height:100%;display:block}.chart-note{font-size:.78rem;color:#8495ad;margin-top:12px}
.rows{display:grid;gap:9px}.rowitem{display:flex;justify-content:space-between;gap:14px;padding:11px 0;border-bottom:1px solid #202c3f;font-size:.88rem}.rowitem:last-child{border:0}.rowitem span:first-child{color:#8fa0b8}.rowitem strong{text-align:right;overflow-wrap:anywhere}
.event{padding:10px 12px;border-radius:10px;background:#0b1320;border:1px solid #1f2c40;margin-bottom:8px;font-size:.82rem}.event b{color:#6ce0bb}.empty{color:#8292aa;padding:18px 0;font-size:.88rem}
footer{color:#61738e;font-size:.75rem;margin-top:20px;line-height:1.6}
@media(max-width:1100px){.dashboard{grid-template-columns:minmax(220px,.8fr) minmax(0,1.6fr)}.right-stack{grid-column:1 / -1;grid-template-columns:repeat(2,minmax(0,1fr))}.incoming-panel{position:static;max-height:none}}@media(max-width:700px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}.dashboard{grid-template-columns:minmax(0,1fr)}.right-stack{grid-column:auto;grid-template-columns:minmax(0,1fr)}.chart-wrap{height:320px}}
@media(max-width:420px){.grid{grid-template-columns:1fr 1fr}.metric{padding:12px}.metric .value{font-size:1.1rem}.chart-wrap{height:260px}}
</style></head>
<body>
<header><div><div class="brand">AICFA<span>.</span></div><div class="sub">PERSONAL MARKET STRUCTURE TERMINAL</div></div><div class="controls"><div class="pill"><i class="led" id="led"></i><span id="connection">Подключение…</span></div><button id="changePassword" type="button">Сменить пароль</button><button id="logout" type="button">Выйти</button></div></header>
<main>
<div class="top"><div><h1>SMC Scanner</h1><div class="muted">Закрытые свечи · BOS/CHoCH · Order Blocks · FVG · Liquidity</div></div>
<div class="pill">Автосканер · все инструменты · scalp / intraday <span id="marketHoursStatus">Режим: shadow · часы рынка: проверка</span></div><div hidden><select id="symbol" aria-label="Инструмент"></select><select id="tf" aria-label="Таймфрейм"><option>1m</option><option>5m</option><option>15m</option><option>1h</option><option>4h</option></select></div></div>
<section class="grid">
<div class="metric"><div class="label">Поток Binance</div><div class="value" id="stream">—</div><div class="hint">статус соединения</div></div>
<div class="metric"><div class="label">Свечные серии</div><div class="value" id="series">—</div><div class="hint">ожидается 250</div></div>
<div class="metric"><div class="label">Закрытые свечи</div><div class="value" id="candleCount">—</div><div class="hint">хранимое окно</div></div>
<div class="metric"><div class="label">История</div><div class="value" id="history">—</div><div class="hint">начальная загрузка</div></div>
</section>
<section class="dashboard">
<div class="dashboard-column">
<section class="panel incoming-panel" id="incomingPanel"><div class="panel-title"><span>Входящие сетапы</span><span class="pill" id="setupCount">0</span><label style="margin-left:12px"><input id="showRejected" type="checkbox"> Показывать отклонённые</label></div><div id="setups"><div class="empty">Автоматический поиск по закрытым свечам. Ожидание подходящих сетапов…</div></div></section>
</div>
<div class="chart-column">
<div class="panel empty" id="chartPlaceholder" style="padding:28px;text-align:center">Выберите сетап во входящих, принятых или реализованных — здесь откроется его график.</div>
<div class="layout" id="setupChart" style="display:none">
<section class="panel"><div class="panel-title"><span id="chartTitle">Выберите сетап</span><span class="pill" id="lastPrice">Ожидание данных</span></div><div class="chart-wrap"><canvas id="chart" aria-label="График свечей"></canvas></div><div class="chart-note" id="chartNote">Загрузка закрытых свечей и расчёт разметки SMC…</div></section>
<aside class="panel"><div class="panel-title"><span>Сетап и SMC-разметка</span><span class="pill" id="annotationCount">—</span></div><div class="rows" id="stats"><div class="empty">Выберите сетап, чтобы увидеть его параметры и SMC-разметку.</div></div><div class="panel-title" style="margin-top:22px"><span>Последние события</span></div><div id="events"><div class="empty">Событий пока нет</div></div></aside>
</div>
</div>
<div class="right-stack">
<section class="panel"><div class="panel-title">Принятые сетапы</div><div id="activeSetups"><div class="empty">Пока нет принятых сетапов.</div></div></section>
<section class="panel"><div class="panel-title">Реализованные</div><div id="realizedJournal"><div class="empty">Журнал пока пуст.</div></div></section>
</div>
</section>
<footer>Анализ выполняется только по закрытым свечам. Разметка не является торговой рекомендацией. Автоматический поиск сетапов по закрытым свечам всех инструментов. Исполнение сделок отключено.</footer>
</main>
<script>
const symbols=__AICFA_SYMBOLS__;const timeframes=__AICFA_TIMEFRAMES__;
const $=id=>document.getElementById(id);let selectedSetup=null;symbols.forEach(s=>{const o=document.createElement('option');o.value=s;o.textContent=s;$('symbol').append(o)});$('symbol').value=symbols.includes('BTCUSDT')?'BTCUSDT':symbols[0];timeframes.forEach(tf=>{const o=document.createElement('option');o.value=tf;o.textContent=tf;$('tf').append(o)});
function fmt(n){return n==null?'—':Number(n).toLocaleString('en-US',{maximumFractionDigits:8})}
function draw(data){const canvas=$('chart'),ctx=canvas.getContext('2d'),rect=canvas.getBoundingClientRect(),dpr=window.devicePixelRatio||1;canvas.width=Math.max(1,rect.width*dpr);canvas.height=Math.max(1,rect.height*dpr);ctx.scale(dpr,dpr);const w=rect.width,h=rect.height;ctx.clearRect(0,0,w,h);ctx.fillStyle='#0a1220';ctx.fillRect(0,0,w,h);const cs=data.candles||[];if(!cs.length){ctx.fillStyle='#8192aa';ctx.fillText('Ожидание свечей…',20,30);return}const view=cs.slice(-100),lo=Math.min(...view.map(c=>c.low)),hi=Math.max(...view.map(c=>c.high)),span=hi-lo||1,pad={l:10,r:64,t:16,b:24},cw=(w-pad.l-pad.r)/view.length;const y=p=>pad.t+(hi-p)/span*(h-pad.t-pad.b);ctx.strokeStyle='#1d2a3d';ctx.lineWidth=1;for(let i=0;i<5;i++){const yy=pad.t+i*(h-pad.t-pad.b)/4;ctx.beginPath();ctx.moveTo(pad.l,yy);ctx.lineTo(w-pad.r,yy);ctx.stroke();ctx.fillStyle='#7e90a9';ctx.font='10px system-ui';ctx.fillText(fmt(hi-i*span/4),w-pad.r+5,yy+3)}view.forEach((c,i)=>{const x=pad.l+i*cw+cw/2,up=c.close>=c.open;ctx.strokeStyle=up?'#59d6ad':'#f07883';ctx.fillStyle=ctx.strokeStyle;ctx.beginPath();ctx.moveTo(x,y(c.high));ctx.lineTo(x,y(c.low));ctx.stroke();const top=y(Math.max(c.open,c.close)),bot=y(Math.min(c.open,c.close));ctx.fillRect(x-Math.max(1,cw*.29),top,Math.max(2,cw*.58),Math.max(1,bot-top))});const ann=data.annotations||{},offset=cs.length-view.length;const zone=(items,color)=>{for(const z of items||[]){const start=Number(z.candle_index??z.first_candle_index??z.confirmation_index)-offset;if(start>=view.length||start< -view.length)continue;const x0=pad.l+Math.max(0,start)*cw, x1=w-pad.r,top=y(Number(z.upper)),bottom=y(Number(z.lower));if(Number.isFinite(top)&&Number.isFinite(bottom)){ctx.fillStyle=color;ctx.fillRect(x0,Math.min(top,bottom),Math.max(1,x1-x0),Math.max(1,Math.abs(bottom-top)))}}};zone((ann.order_blocks||[]).filter(z=>!z.mitigated),'rgba(99,130,255,.12)');zone((ann.fvg||[]).filter(z=>!z.fully_filled),'rgba(89,214,173,.12)');for(const e of ann.structure_breaks||[]){const i=Number(e.candle_index)-offset;if(i<0||i>=view.length)continue;const yy=y(Number(e.level));ctx.strokeStyle=e.kind==='CHoCH'?'#f4bd62':'#9aabff';ctx.setLineDash([3,3]);ctx.beginPath();ctx.moveTo(pad.l+i*cw,yy);ctx.lineTo(w-pad.r,yy);ctx.stroke();ctx.setLineDash([]);ctx.fillStyle=ctx.strokeStyle;ctx.font='10px system-ui';ctx.fillText(e.kind+' '+e.direction,pad.l+i*cw+3,Math.max(11,yy-4))}for(const e of ann.sweeps||[]){const i=Number(e.candle_index)-offset;if(i<0||i>=view.length)continue;const yy=y(Number(e.level));ctx.fillStyle='#f4bd62';ctx.beginPath();ctx.arc(pad.l+i*cw+cw/2,yy,3,0,Math.PI*2);ctx.fill()}const last=view[view.length-1];ctx.strokeStyle='#e6bc6d';ctx.setLineDash([4,4]);ctx.beginPath();ctx.moveTo(pad.l,y(last.close));ctx.lineTo(w-pad.r,y(last.close));ctx.stroke();ctx.setLineDash([]);
if(selectedSetup&&selectedSetup.symbol===$('symbol').value&&selectedSetup.timeframe===$('tf').value){const levels=[['Вход',selectedSetup.confirmation_price,'#e6bc6d'],['Лимит',selectedSetup.entry_limit,'#a9b8ff'],['SL',selectedSetup.stop_price,'#f07883'],['TP1',(selectedSetup.targets||[])[0],'#59d6ad'],['TP2',(selectedSetup.targets||[])[1],'#59d6ad'],['TP3',(selectedSetup.targets||[])[2],'#59d6ad']];for(const [label,price,color] of levels){const p=Number(price);if(!Number.isFinite(p)||p<lo||p>hi)continue;const yy=y(p);ctx.strokeStyle=color;ctx.setLineDash(label==='SL'?[4,3]:[2,3]);ctx.beginPath();ctx.moveTo(pad.l,yy);ctx.lineTo(w-pad.r,yy);ctx.stroke();ctx.setLineDash([]);ctx.fillStyle=color;ctx.font='10px system-ui';ctx.fillText(label+' '+fmt(p),pad.l+4,Math.max(11,yy-4))}}}
function openSetup(s){selectedSetup=s;$("symbol").value=s.symbol;$("tf").value=s.timeframe||"1m";$("chartPlaceholder").style.display="none";$("setupChart").style.display="grid";load()}
function row(label,value){const d=document.createElement('div');d.className='rowitem';const a=document.createElement('span');a.textContent=label;const b=document.createElement('strong');b.textContent=value;d.append(a,b);$('stats').append(d)}
async function loadStatus(){try{const st=await fetch('/api/data-status').then(r=>r.json());const connected=st.groups?.tradfi?.status==='connected'&&st.groups?.crypto?.status==='connected';$('connection').textContent=connected?'Поток активен':'Проверка потока';$('led').style.background=connected?'#59d6ad':'#f4bd62';$('stream').textContent=connected?'CONNECTED':'CONNECTING';$('series').textContent=fmt(st.latest_series);$('candleCount').textContent=fmt(st.stored_candles);$('history').textContent=st.history?.status||'—';return st}catch(e){$('connection').textContent='Ошибка статуса';console.error('Could not load market status',e);return null}}
async function load(){if(!selectedSetup)return;const symbol=$('symbol').value,tf=$('tf').value;$('chartTitle').textContent=symbol+' · '+tf;try{const an=await fetch('/api/smc-analysis/'+encodeURIComponent(symbol)+'/'+encodeURIComponent(tf)).then(r=>r.json());if(an.status!=='ok'){$('chartNote').textContent='Ряд прогревается: '+(an.candles||0)+' свечей';draw({candles:[]});return}draw(an);const cs=an.candles,last=cs[cs.length-1];$('lastPrice').textContent=fmt(last.close);$('chartNote').textContent='Свечей: '+cs.length+' · последнее закрытие: '+new Date(last.timestamp_ms).toLocaleString();const a=an.annotations;$('annotationCount').textContent=String(a.swings.length+a.structure_breaks.length+a.order_blocks.length+a.fvg.length+a.liquidity_levels.length+a.sweeps.length);$('stats').replaceChildren();row('Последняя цена',fmt(last.close));row('Premium / Discount',a.premium_discount||'Нет подтверждённого диапазона');row('ATR(14)',fmt(a.atr));row('Средний объём',fmt(a.average_volume));row('Swing points',String(a.swings.length));row('BOS / CHoCH',String(a.structure_breaks.length));row('Order Blocks',String(a.order_blocks.length));row('FVG',String(a.fvg.length));row('Liquidity levels',String(a.liquidity_levels.length));row('Sweeps',String(a.sweeps.length));const ev=[...a.structure_breaks.map(x=>({t:x.timestamp_ms,label:x.kind+' · '+x.direction+' · '+fmt(x.level)})),...a.sweeps.map(x=>({t:x.timestamp_ms,label:'Sweep '+x.direction+' · '+fmt(x.level)}))].sort((x,y)=>y.t-x.t).slice(0,6);$('events').replaceChildren();if(!ev.length){$('events').innerHTML='<div class="empty">На текущем окне событий нет</div>'}else ev.forEach(e=>{const d=document.createElement('div');d.className='event';const b=document.createElement('b');b.textContent=new Date(e.t).toLocaleTimeString();d.append(b,document.createTextNode('  '+e.label));$('events').append(d)})}catch(e){$('connection').textContent='Ошибка API';$('chartNote').textContent='Не удалось получить анализ. Проверьте статус сервиса.';console.error(e)}}
$('symbol').addEventListener('change',load);$('tf').addEventListener('change',load);async function loadSetups(){try{const r=await fetch('/api/setups'+($('showRejected')&&$('showRejected').checked?'?include_rejected=true':''));if(!r.ok)return;const data=await r.json();if($('marketHoursStatus'))$('marketHoursStatus').textContent='Режим: '+(data.scanner_mode||'shadow')+' · часы рынка: '+(data.market_hours?data.market_hours.mapped+'/'+data.market_hours.total:'проверка');const host=$('setups');host.replaceChildren();$('setupCount').textContent=String(data.candidates.length);if(!data.candidates.length){host.innerHTML='<div class="empty">Подходящих сетапов пока нет. Сигналы не выдумываются.</div>';return}for(const s of data.candidates.slice().reverse()){const d=document.createElement('div');d.className='event';const b=document.createElement('b');b.textContent=s.symbol+' · '+s.profile.toUpperCase()+' · '+s.direction.toUpperCase();const detail=document.createElement('div');detail.textContent='Статус '+s.status+' · скор '+s.score+'/10 · вход '+fmt(s.confirmation_price)+' · лимит '+fmt(s.entry_limit)+' · стоп '+fmt(s.stop_price)+' · RR '+fmt(s.risk_reward)+' · '+new Date(s.confirmation_time_ms).toLocaleString()+(s.reasons&&s.reasons.length?' · '+s.reasons.join(', '):'')+(s.decision_reasons&&s.decision_reasons.length?' · '+s.decision_reasons.join(', '):'');d.append(b,detail);d.style.cursor='pointer';d.title='Открыть график сетапа';d.addEventListener('click',()=>openSetup(s));host.append(d)}}catch(e){console.error('Could not load setup candidates',e)}}
async function loadActive(){try{const r=await fetch('/api/active-setups');if(!r.ok)return;const data=await r.json();const host=$('activeSetups');host.replaceChildren();if(!data.setups.length){host.innerHTML='<div class="empty">Пока нет принятых сетапов.</div>';return}for(const s of data.setups){const d=document.createElement('div');d.className='event';d.textContent=s.symbol+' · '+s.profile+' · '+s.direction+' · '+s.status+' · вход '+fmt(s.confirmation_price)+' · стоп '+fmt(s.stop_price)+' · TP '+s.targets.map(fmt).join(' / ');d.style.cursor='pointer';d.addEventListener('click',()=>openSetup(s));host.append(d)}}catch(e){console.error(e)}}
async function loadJournal(){try{const r=await fetch('/api/journal');if(!r.ok)return;const data=await r.json();const host=$('realizedJournal');host.replaceChildren();if(!data.trades.length){host.innerHTML='<div class="empty">Журнал пока пуст.</div>';return}for(const t of data.trades){const d=document.createElement('div');d.className='event';d.textContent=t.symbol+' · '+t.profile+' · '+t.direction+' · '+t.final_status+' · gross '+Number(t.gross_r).toFixed(2)+'R · комиссии '+Number(t.commission_r).toFixed(3)+'R · net '+Number(t.net_r).toFixed(2)+'R';d.style.cursor='pointer';d.addEventListener('click',()=>openSetup(t));host.append(d)}}catch(e){console.error(e)}}
if($('showRejected'))$('showRejected').addEventListener('change',loadSetups);window.addEventListener('resize',()=>{if(selectedSetup)load()});loadStatus();loadSetups();loadActive();loadJournal();let firstClosedCandleStatusLoaded=false;const eventSource=new EventSource('/api/events');eventSource.onmessage=e=>{try{const event=JSON.parse(e.data);if(event.type==='setup_candidate'){loadStatus();loadSetups();loadActive()}if(event.type==='setup_lifecycle'){loadStatus();loadSetups();loadActive();loadJournal()}if(event.type==='closed_candle'){if(!firstClosedCandleStatusLoaded){firstClosedCandleStatusLoaded=true;loadStatus()}if(selectedSetup&&event.symbol===selectedSetup.symbol&&event.timeframe===selectedSetup.timeframe){load()}}}catch(err){console.error('Invalid scanner event',err)}};eventSource.onerror=()=>{$('connection').textContent='Восстановление потока событий'};$('logout').addEventListener('click',async()=>{await fetch('/api/auth/logout',{method:'POST'});location.href='/login'});$('changePassword').addEventListener('click',async()=>{const current_password=prompt('Текущий пароль');if(current_password===null)return;const new_password=prompt('Новый пароль (минимум 12 символов)');if(new_password===null)return;const r=await fetch('/api/settings/password',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({current_password,new_password})});alert(r.ok?'Пароль изменён. Войдите заново при следующем входе.':'Не удалось сменить пароль. Проверьте текущий пароль и длину нового.');});

</script></body></html>
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


@app.get("/api/setups")
async def setup_candidates(include_rejected: bool = False) -> dict:
    """Current in-memory candidates detected automatically from closed candles."""
    status = market_data.status()
    connected = status.get("groups", {}).get("tradfi", {}).get("status") == "connected" and status.get("groups", {}).get("crypto", {}).get("status") == "connected"
    return {"status": "running" if connected else "warming_up",
            "last_scan_time_ms": _scanner_last_event_ms,
            "scanner_mode": "live" if SCANNER_LIVE_ENABLED else "shadow",
            "live_acceptance_enabled": SCANNER_LIVE_ENABLED,
            "exchange_metadata": status.get("exchange_metadata", {}),
            "active_count": _get_setup_store().active_count(),
            "market_hours": {
                "mapped": len((US_EQUITY_SYMBOLS | KRX_EQUITY_SYMBOLS | COMMODITY_SYMBOLS) & set(TRADFI_SYMBOLS)),
                "total": len(TRADFI_SYMBOLS),
                "unmapped": sorted(set(TRADFI_SYMBOLS) - US_EQUITY_SYMBOLS - KRX_EQUITY_SYMBOLS - COMMODITY_SYMBOLS),
            },
            "candidates": _get_setup_store().list_candidates(include_rejected=include_rejected)}


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
