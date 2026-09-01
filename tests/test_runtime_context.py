from __future__ import annotations

import time

import pytest

from helpers import *  # noqa: F401,F403

from gold_bot.core import BrokerTransaction, Side
from gold_bot.runtime_context import RunLock, instance_key, runtime_paths, runtime_report
from gold_bot.settings import BotConfig


def test_instance_key_suffixe_les_fichiers():
    cfg = BotConfig.load("robot.bitvavo.json")
    cfg.engine.instance_id = "vps-prod"
    assert instance_key(cfg) == "bitvavo-vps-prod"
    paths = runtime_paths(cfg)
    assert paths.trades.endswith("data/trades-bitvavo-vps-prod.jsonl")
    assert paths.state.endswith("data/state-bitvavo-vps-prod.json")
    assert paths.objectives.endswith("data/objectives-bitvavo-vps-prod.json")


def test_runtime_report_expose_la_source_chargee():
    cfg = BotConfig.load("robot.bitvavo.json")
    report = runtime_report(cfg, trades_count=12)
    assert report["config_source"].endswith("/robot.bitvavo.json")
    assert report["instance"] == "bitvavo"
    assert report["trades_count"] == 12


def test_run_lock_refuse_un_second_process(tmp_path):
    path = str(tmp_path / "robot.lock")
    first = RunLock(path, {"instance": "bitvavo"})
    second = RunLock(path, {"instance": "bitvavo"})
    first.acquire()
    try:
        with pytest.raises(RuntimeError, match="instance deja active"):
            second.acquire()
    finally:
        first.release()


def test_reconciliation_alerte_si_bitvavo_vend_sans_journal(monkeypatch):
    from gold_bot.engine import TradingEngine

    now = 1_700_000_000.0
    notes = []

    class FauxBroker:
        name = "bitvavo"

        def recent_transactions(self, since=0.0):
            return [BrokerTransaction(
                tx_id="1", order_id="o1", market="UNI-EUR", symbol="UNIUSD",
                side=Side.SELL, amount=2.0, price=4.5, fee=0.03,
                timestamp=now - 60, quote_amount=9.0, source="bitvavo")]

    class FauxNotifier:
        def warning(self, title, body="", data=None, **_kwargs):
            notes.append((title, body, data or {}))

    engine = TradingEngine.__new__(TradingEngine)
    engine.broker = FauxBroker()
    engine.journal = type("Journal", (), {"trades": [], "path": "data/trades-bitvavo.jsonl"})()
    engine.store = type("Store", (), {
        "state": type("State", (), {
            "started_at": now - 3600,
            "last_reconciliation_ts": 0.0,
            "last_exchange_tx_ts": 0.0,
        })()
    })()
    engine.notifier = FauxNotifier()

    monkeypatch.setattr("gold_bot.engine.time.time", lambda: now)
    engine._reconcile_exchange_activity()

    assert notes
    assert notes[0][0] == "Journal local en retard sur Bitvavo"
    assert notes[0][2]["ventes_broker"] == 1
