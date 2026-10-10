import json
import threading
from types import SimpleNamespace

from aicfa.telegram_notifications import TelegramSetupNotifier
from aicfa.setup_analysis import SetupLevel


def _state_with_new_setup():
    candidate = SimpleNamespace(
        direction="long",
        scenario="liquidity_reversal",
        entry_zone=(
            SetupLevel(100.0, "1m", "FVG low"),
            SetupLevel(101.0, "1m", "FVG high"),
        ),
        invalidation_level=SetupLevel(98.0, "1m", "structural stop"),
        target_levels=(
            SetupLevel(106.0, "5m", "TP1"),
            SetupLevel(110.0, "15m", "TP2"),
        ),
    )
    identity = SimpleNamespace(
        symbol="BTC/USDT",
        market_type="futures",
        horizon=SimpleNamespace(value="scalping"),
        scenario="liquidity_reversal",
        direction="long",
        entry_zone=((100.0, "1m", "FVG low"), (101.0, "1m", "FVG high")),
        invalidation=(98.0, "1m", "structural stop"),
        targets=((106.0, "5m", "TP1"), (110.0, "15m", "TP2")),
    )
    event = SimpleNamespace(
        status=SimpleNamespace(value="active"),
        reason="new independent setup activated",
        candidate=candidate,
        identity=identity,
    )
    market = SimpleNamespace(lifecycle_results=(event,))
    return SimpleNamespace(result=SimpleNamespace(markets=(market,)))


def test_telegram_outbox_sends_new_setup_once_and_persists_dedupe(tmp_path):
    sent_messages = []
    delivered = threading.Event()

    def sender(message):
        sent_messages.append(message)
        delivered.set()

    state_path = tmp_path / "journal" / "telegram_outbox.json"
    notifier = TelegramSetupNotifier(
        bot_token="test-token",
        chat_id="test-chat",
        state_path=state_path,
        sender=sender,
    )
    state = _state_with_new_setup()

    assert notifier.notify_state(state) == 1
    assert delivered.wait(2)
    assert notifier.notify_state(state) == 0
    notifier._queue.join()

    assert len(sent_messages) == 1
    assert "BTC/USDT" in sent_messages[0]
    assert "SCALPING" in sent_messages[0]
    assert "Maximum entry price: 101" in sent_messages[0]
    assert "SL: 98" in sent_messages[0]
    assert "TP1: 106" in sent_messages[0]
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert len(payload["sent"]) == 1
    assert payload["pending"] == {}


def test_telegram_notifier_requires_both_environment_values(monkeypatch, tmp_path):
    monkeypatch.delenv("AICFA_TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("AICFA_TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    assert TelegramSetupNotifier.from_env(data_dir=tmp_path) is None
