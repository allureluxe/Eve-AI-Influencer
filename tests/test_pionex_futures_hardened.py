import unittest

from gold_bot.brokers import PionexFuturesBroker, PionexFuturesConfig
from gold_bot.brokers.pionex_futures_hardened import HardenedPionexFuturesBroker


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

    def test_live_alias_is_hardened_futures_broker(self):
        self.assertIs(PionexFuturesBroker, HardenedPionexFuturesBroker)
        broker = PionexFuturesBroker(PionexFuturesConfig(dry_run=True))
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


if __name__ == "__main__":
    unittest.main()
