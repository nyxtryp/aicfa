from contextlib import asynccontextmanager
import asyncio
import logging
import time

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from app.backup import create_verified_backup
from app.market_data import MarketDataManager

logger = logging.getLogger("aicfa.backup")
BACKUP_INTERVAL_SECONDS = 24 * 60 * 60
BACKUP_RETRY_SECONDS = 60 * 60
backup_status = {"status": "waiting", "last_success_ms": None, "filename": None, "size_bytes": None, "last_error": None}

market_data = MarketDataManager()


async def _daily_backup_loop() -> None:
    """Back up after startup history finishes, then repeat daily."""
    history_task = market_data._history_task
    if history_task is not None:
        await asyncio.gather(history_task, return_exceptions=True)
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

PAGE = """<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#0b1020">
  <title>AICFA — SMC Scanner</title>
  <style>
    :root { color-scheme: dark; font-family: Inter, ui-sans-serif, system-ui, sans-serif; }
    * { box-sizing: border-box; }
    body { margin: 0; min-height: 100vh; background: #0b1020; color: #e8edf7; }
    main { width: min(920px, calc(100% - 32px)); margin: 10vh auto; }
    .eyebrow { color: #8b9bb8; font-size: .8rem; letter-spacing: .16em; text-transform: uppercase; }
    h1 { margin: 14px 0 8px; font-size: clamp(2.4rem, 7vw, 4.5rem); letter-spacing: -.055em; }
    .accent { color: #72e0c1; }
    p { color: #aab6cc; line-height: 1.7; max-width: 620px; }
    .panel { margin-top: 36px; padding: 22px; border: 1px solid #26334c; border-radius: 16px; background: #111a2d; }
    .status { display: inline-flex; gap: 9px; align-items: center; color: #f2c879; font-size: .9rem; }
    .dot { width: 8px; height: 8px; border-radius: 50%; background: #f2c879; }
    .note { margin-bottom: 0; font-size: .9rem; }
  </style>
</head>
<body>
  <main>
    <div class="eyebrow">Personal market analysis</div>
    <h1>AICFA<span class="accent">.</span></h1>
    <p>SMC Scanner — персональная панель анализа рынка. Сайт развёрнут, но рыночные данные, SMC-движок и торговые сигналы ещё не подключены.</p>
    <section class="panel" aria-live="polite">
      <div class="status"><span class="dot"></span> Каркас сайта запущен</div>
      <p class="note">Следующий этап — проверка окружения и публичного API Binance, затем реализация потока рыночных данных по техническому заданию.</p>
    </section>
  </main>
</body>
</html>
"""


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


@app.get("/api/backup-status")
async def backup_health() -> dict:
    """Expose the last verified backup result without leaking filesystem paths."""
    return dict(backup_status)
