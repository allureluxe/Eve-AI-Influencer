from __future__ import annotations

from decimal import Decimal

from gold_bot.brokers.bitvavo import BitvavoBroker, BitvavoConfig, RegleMarche
from gold_bot.brokers.bitvavo_hardening import _TICKS, _tick_floor, _annuler_stop


def test_tick_size_is_authoritative():
    _TICKS["BTC-EUR"] = Decimal("0.01")
    rule = RegleMarche("BTC-EUR", price_precision=5)
    assert _tick_floor(rule, 61234.678, RegleMarche.arrondir_prix) == 61234.67
    _TICKS.pop("BTC-EUR", None)


def test_market_quantity_decimals_are_preserved():
    rule = RegleMarche("PEPE-EUR", amount_decimals=3)
    assert rule.arrondir_quantite(1.2349) == 1.234


def test_cancel_uses_exact_order_ids(monkeypatch):
    broker = BitvavoBroker(BitvavoConfig(api_key="k", api_secret="s", dry_run=False))
    broker._stops["BTCUSD"] = "known"
    calls = []

    def fake_call(method, path, params=None, corps=None, signe=True):
        calls.append((method, path, params))
        if path == "/ordersOpen":
            return [{
                "orderId": "known",
                "side": "sell",
                "orderType": "stopLossLimit",
                "operatorId": broker.config.operator_id,
                "created": 1,
            }, {
                "orderId": "foreign",
                "side": "sell",
                "orderType": "stopLossLimit",
                "operatorId": broker.config.operator_id + 1,
                "created": 2,
            }]
        return {}

    monkeypatch.setattr(broker, "_appel", fake_call)
    monkeypatch.setattr(broker, "symbol_for", lambda symbol: "BTC-EUR")
    _annuler_stop(broker, "BTCUSD")

    assert calls[0][1] == "/ordersOpen"
    assert any(c[1] == "/order" and c[2]["orderId"] == "known" for c in calls)
    assert not any(c[1] == "/order" and c[2]["orderId"] == "foreign" for c in calls)
