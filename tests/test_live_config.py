from __future__ import annotations

import os
import unittest

from gold_bot.settings import BotConfig


class TestLiveConfig(unittest.TestCase):
    # « bitvavo » au comptant, « bitvavo_margin » quand la vente a decouvert
    # est activee. Les deux designent la meme plateforme et le meme compte.
    BROKERS_BITVAVO = ("bitvavo", "bitvavo_margin")

    def test_robot_bitvavo_est_coherent(self):
        cfg = BotConfig.load("robot.bitvavo.json")
        self.assertIn(cfg.engine.broker, self.BROKERS_BITVAVO)
        self.assertFalse(cfg.engine.offline)
        self.assertLessEqual(cfg.risk.max_risk_pct, 1.5)
        self.assertEqual(cfg.validate(), [])

    def test_alias_gb_config_est_lu(self):
        old = os.environ.get("GB_CONFIG")
        old_file = os.environ.get("GB_CONFIG_FILE")
        try:
            os.environ["GB_CONFIG"] = "robot.bitvavo.json"
            os.environ.pop("GB_CONFIG_FILE", None)
            cfg = BotConfig.load()
            self.assertIn(cfg.engine.broker, self.BROKERS_BITVAVO)
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

    def test_broker_obsolete_refuse(self):
        cfg = BotConfig()
        cfg.engine.broker = "binance"
        self.assertTrue(any("broker invalide" in p for p in cfg.validate()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
