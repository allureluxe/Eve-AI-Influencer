import unittest
from unittest.mock import patch

from gold_bot.brokers import PionexFuturesBroker, PionexFuturesConfig
from gold_bot.brokers.base import BrokerError
# `gold_bot.brokers.PionexFuturesBroker` est un alias vers la classe durcie :
# c'est elle qui part en live. Pour tester la recuperation apres un 404, il
# faut la classe parente, celle dont l'override attrape l'erreur.
from gold_bot.brokers.pionex_futures import PionexFuturesBroker as BasePionexFuturesBroker
from gold_bot.brokers.pionex_futures_hardened import HardenedPionexFuturesBroker
from gold_bot.core import Side


class TestPionexFuturesHardened(unittest.TestCase):
    def test_public_bookticker_uses_futures_bookticker_endpoint(self):
        broker = HardenedPionexFuturesBroker(PionexFuturesConfig(dry_run=True))
        seen = {}

        def fake_public(path, params=None):
            seen["path"] = path
            seen["params"] = params
            return {"result": True, "data": {"tickers": [{"bidPrice": "100", "askPrice": "101"}]}}

        broker._public = fake_public
        self.assertEqual(broker._book("BTC_USDT_PERP"), (100.0, 101.0))
        self.assertEqual(seen["path"], "/api/v1/market/bookTicker")
        self.assertEqual(seen["params"], {"symbol": "BTC_USDT_PERP"})

    def test_live_alias_points_to_hardened_class(self):
        self.assertIs(PionexFuturesBroker, HardenedPionexFuturesBroker)
        broker = HardenedPionexFuturesBroker(PionexFuturesConfig(dry_run=True))
        self.assertTrue(broker.is_live)
        self.assertTrue(broker.supports_short)
        self.assertEqual(broker.pionex_symbol("BTCUSDT"), "BTC_USDT_PERP")

    def test_account_detail_maps_equity_and_available_margin(self):
        broker = HardenedPionexFuturesBroker(PionexFuturesConfig(dry_run=False))
        broker._private = lambda method, path, **kwargs: {
            "result": True,
            "data": {
                "balances": [{
                    "coin": "USDT",
                    "assets": "220",
                    "free": "200",
                    "frozen": "20",
                    "available": "190",
                    "unrealizedPnL": "5",
                    "totalInitialMargin": "30",
                }]
            },
        }
        broker._refresh_account()
        self.assertEqual(broker.account().equity, 225.0)
        self.assertEqual(broker.account().margin_free, 190.0)
        self.assertEqual(broker.account().margin_used, 30.0)

    def test_market_order_confirmation_uses_position_delta(self):
        broker = HardenedPionexFuturesBroker(PionexFuturesConfig(dry_run=False))
        broker._pending_market_orders["123"] = {
            "filled": 0.10,
            "symbol": "SOL_USDT_PERP",
            "position_side": "LONG",
            "before": 0.0,
            "opening": True,
        }
        broker._position_volume = lambda symbol, position_side: 0.10
        result = broker._wait_order("SOL_USDT_PERP", "123")
        self.assertEqual(result["status"], "FILLED")
        self.assertEqual(float(result["filledSize"]), 0.10)

    def test_http_404_after_post_does_not_trigger_blind_retry(self):
        broker = HardenedPionexFuturesBroker(PionexFuturesConfig(dry_run=False))
        # Un volume constant ne prouverait rien : la recuperation cherche une
        # VARIATION de position. Premiere lecture avant l'ordre (rien ouvert),
        # lectures suivantes apres le 404 (la position est bien passee).
        lectures = iter([0.0])
        broker._position_volume = lambda symbol, position_side: next(lectures, 0.10)
        with patch.object(
            BasePionexFuturesBroker,
            "_order",
            side_effect=BrokerError("Pionex HTTP 404: Route Not Found"),
        ):
            order_id = broker._order("SOL_USDT_PERP", Side.BUY, 0.10, Side.BUY, "gb-open-test")
        self.assertTrue(order_id.startswith("RECOVERED-"))
        self.assertIn(order_id, broker._pending_market_orders)


if __name__ == "__main__":
    unittest.main()
