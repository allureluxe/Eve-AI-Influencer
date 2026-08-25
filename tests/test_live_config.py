from __future__ import annotations

import os
import tempfile
import unittest

from gold_bot.settings import BotConfig


class TestLiveConfig(unittest.TestCase):
    def test_robot_binance_est_coherent(self):
        cfg = BotConfig.load("robot.binance.json")
        self.assertEqual(cfg.engine.broker, "binance")
        self.assertEqual(cfg.engine.offline, False)
        self.assertLessEqual(cfg.risk.max_risk_pct, 1.5)
        self.assertEqual(cfg.validate(), [])

    def test_alias_gb_config_est_lu(self):
        old = os.environ.get("GB_CONFIG")
        old_file = os.environ.get("GB_CONFIG_FILE")
        try:
            os.environ["GB_CONFIG"] = "robot.binance.json"
            os.environ.pop("GB_CONFIG_FILE", None)
            cfg = BotConfig.load()
            self.assertEqual(cfg.engine.broker, "binance")
        finally:
            if old is None:
                os.environ.pop("GB_CONFIG", None)
            else:
                os.environ["GB_CONFIG"] = old
            if old_file is None:
                os.environ.pop("GB_CONFIG_FILE", None)
            else:
                os.environ["GB_CONFIG_FILE"] = old_file

    def test_risque_superieur_a_15_pourcent_refuse(self):
        cfg = BotConfig()
        cfg.risk.max_risk_pct = 1.51
        self.assertTrue(any("plafond de securite" in p for p in cfg.validate()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
