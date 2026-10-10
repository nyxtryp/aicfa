"""Asynchronous, deduplicated Telegram delivery for newly activated AICFA setups."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import queue
import threading
import time
from typing import Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class TelegramSetupNotifier:
    """Durable outbox for setup-created notifications.

    The scanner only enqueues a persisted lifecycle result; network delivery is
    handled by a daemon worker so Telegram latency cannot block candle analysis.
    """

    def __init__(
        self,
        *,
        bot_token: str,
        chat_id: str,
        state_path: str | Path,
        sender: Callable[[str], None] | None = None,
    ) -> None:
        self.bot_token = str(bot_token).strip()
        self.chat_id = str(chat_id).strip()
        if not self.bot_token or not self.chat_id:
            raise ValueError("Telegram bot token and chat id are required")
        self.state_path = Path(state_path)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self._sender = sender or self._send
        self._lock = threading.RLock()
        self._queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self._sent: set[str] = set()
        self._pending: dict[str, str] = {}
        self._load()
        for item in self._pending.items():
            self._queue.put(item)
        self._worker = threading.Thread(
            target=self._run,
            name="aicfa-telegram-outbox",
            daemon=True,
        )
        self._worker.start()

    @classmethod
    def from_env(cls, *, data_dir: str | Path) -> "TelegramSetupNotifier | None":
        token = os.getenv("AICFA_TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
        chat_id = os.getenv("AICFA_TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_CHAT_ID")
        if not token or not chat_id:
            return None
        return cls(
            bot_token=token,
            chat_id=chat_id,
            state_path=Path(data_dir) / "journal" / "telegram_outbox.json",
        )

    def _load(self) -> None:
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(payload, dict):
            return
        sent = payload.get("sent", ())
        pending = payload.get("pending", {})
        if isinstance(sent, list):
            self._sent = {str(item) for item in sent}
        if isinstance(pending, dict):
            self._pending = {
                str(key): str(message)
                for key, message in pending.items()
                if isinstance(message, str)
            }

    def _persist(self) -> None:
        temporary = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(
                {"version": 1, "sent": sorted(self._sent), "pending": self._pending},
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
        temporary.replace(self.state_path)

    def _send(self, message: str) -> None:
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        body = urlencode({
            "chat_id": self.chat_id,
            "text": message,
            "disable_web_page_preview": "true",
        }).encode("utf-8")
        request = Request(url, data=body, method="POST")
        with urlopen(request, timeout=8.0) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict) or payload.get("ok") is not True:
            raise RuntimeError("Telegram API rejected sendMessage")

    @staticmethod
    def _setup_key(identity: object) -> str:
        payload = {
            "symbol": getattr(identity, "symbol", ""),
            "market_type": getattr(identity, "market_type", ""),
            "horizon": getattr(getattr(identity, "horizon", ""), "value", getattr(identity, "horizon", "")),
            "scenario": getattr(identity, "scenario", ""),
            "direction": getattr(identity, "direction", ""),
            "entry_zone": getattr(identity, "entry_zone", ()),
            "invalidation": getattr(identity, "invalidation", None),
            "targets": getattr(identity, "targets", ()),
        }
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _format_setup(identity: object, candidate: object) -> str:
        symbol = str(getattr(identity, "symbol", "UNKNOWN"))
        horizon = getattr(getattr(identity, "horizon", ""), "value", getattr(identity, "horizon", "unknown"))
        direction = str(getattr(candidate, "direction", getattr(identity, "direction", ""))).upper()
        scenario = str(getattr(candidate, "scenario", getattr(identity, "scenario", "setup")))
        entry = tuple(getattr(candidate, "entry_zone", ()) or ())
        entry_values = [float(level.value) for level in entry]
        entry_text = (
            f"{min(entry_values):.10g}–{max(entry_values):.10g}"
            if entry_values else "not available"
        )
        if entry_values and direction == "LONG":
            entry_limit = max(entry_values)
            entry_limit_label = "Maximum entry price"
        elif entry_values:
            entry_limit = min(entry_values)
            entry_limit_label = "Minimum entry price"
        else:
            entry_limit = None
            entry_limit_label = "Entry limit"
        invalidation = getattr(candidate, "invalidation_level", None)
        stop = f"{float(invalidation.value):.10g}" if invalidation is not None else "not available"
        targets = tuple(getattr(candidate, "target_levels", ()) or ())
        target_1 = f"{float(targets[0].value):.10g}" if len(targets) > 0 else "not available"
        target_2 = f"{float(targets[1].value):.10g}" if len(targets) > 1 else "not available"
        limit_text = f"{entry_limit:.10g}" if entry_limit is not None else "not available"
        return (
            "AICFA · NEW SETUP\n"
            f"{symbol} · {str(horizon).upper()} · {direction}\n"
            f"Scenario: {scenario}\n"
            f"Entry zone: {entry_text}\n"
            f"{entry_limit_label}: {limit_text}\n"
            f"SL: {stop}\nTP1: {target_1}\nTP2: {target_2}"
        )

    def notify_state(self, state: object) -> int:
        """Enqueue newly activated lifecycle results from an already-persisted scan."""
        queued = 0
        markets = getattr(getattr(state, "result", None), "markets", ()) or ()
        for market in markets:
            for event in getattr(market, "lifecycle_results", ()) or ():
                status = getattr(getattr(event, "status", None), "value", getattr(event, "status", None))
                if status != "active" or getattr(event, "reason", "") != "new independent setup activated":
                    continue
                candidate = getattr(event, "candidate", None)
                identity = getattr(event, "identity", None)
                if candidate is None or identity is None:
                    continue
                key = self._setup_key(identity)
                message = self._format_setup(identity, candidate)
                with self._lock:
                    if key in self._sent or key in self._pending:
                        continue
                    self._pending[key] = message
                    self._persist()
                    self._queue.put((key, message))
                queued += 1
        return queued

    def _run(self) -> None:
        while True:
            key, message = self._queue.get()
            try:
                self._sender(message)
                with self._lock:
                    self._pending.pop(key, None)
                    self._sent.add(key)
                    self._persist()
            except Exception as exc:
                print(
                    f"AICFA Telegram delivery failed; durable retry queued: "
                    f"{type(exc).__name__}: {exc}",
                    flush=True,
                )
                time.sleep(2.0)
                self._queue.put((key, message))
            finally:
                self._queue.task_done()
