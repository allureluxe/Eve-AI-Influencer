import os
import unittest
from unittest.mock import patch

from gold_bot.brokers.pionex_futures import PionexFuturesBroker, PionexFuturesConfig, PionexFuturesRule


class TestPionexFutures(unittest.TestCase):
    def test_symbol_conversion(self):
        broker = PionexFuturesBroker(PionexFuturesConfig(dry_run=True))
        self.assertEqual(broker.pionex_symbol("BTCUSD"), "BTC_USDT_PERP")
        self.assertEqual(broker.pionex_symbol("ETH_USDT"), "ETH_USDT_PERP")
        self.assertEqual(broker.pionex_symbol("ETH_USDT_PERP"), "ETH_USDT_PERP")

    def test_rule_rounding(self):
        rule = PionexFuturesRule(
            symbol="BTC_USDT_PERP",
            base_currency="BTC",
            quote_currency="USDT",
            base_step=0.001,
        )
        self.assertEqual(rule.size_down(1.2349), 1.234)

    def test_live_config_is_not_implicitly_forced_dry(self):
        with patch.dict(os.environ, {
            "PIONEX_API_KEY": "key",
            "PIONEX_API_SECRET": "secret",
            "PIONEX_DRY_RUN": "0",
        }, clear=False):
            cfg = PionexFuturesConfig.from_env()
            self.assertFalse(cfg.dry_run)
            self.assertEqual(cfg.quote_asset, "USDT")

    def test_dry_run_order_never_calls_private_api(self):
        cfg = PionexFuturesConfig(dry_run=True)
        broker = PionexFuturesBroker(cfg)
        broker._rules["BTC_USDT_PERP"] = PionexFuturesRule(
            symbol="BTC_USDT_PERP",
            base_currency="BTC",
            quote_currency="USDT",
            base_step=0.001,
            min_size_market=0.001,
            min_notional=1.0,
        )
        broker._book = lambda _symbol: (100.0, 101.0)
        broker._private = lambda *a, **k: (_ for _ in ()).throw(AssertionError("private API in dry-run"))
        oid = broker._place_market("BTC_USDT_PERP", __import__("gold_bot.core", fromlist=["Side"]).Side.BUY, 0.01, "LONG")
        self.assertTrue(oid.startswith("DRY-"))


if __name__ == "__main__":
    unittest.main()
