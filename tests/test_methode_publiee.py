"""La phrase "methode" montree dans l'application doit decrire le robot
REELLEMENT arme, jamais une version figee dans le code.

Ecrit le 19 sept. 2026 : ce texte etait une constante, et il a menti
pendant une semaine -- il annoncait "canal a 20 jours" et "pyramidage
jusqu'a 3 etages" alors que la configuration armee tournait a 10 jours
et en pyramidage illimite depuis le 12 septembre. C'est l'operateur qui
l'a vu dans l'app, pas un test.
"""
from __future__ import annotations

import importlib.util
import os
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from gold_bot.settings import BotConfig  # noqa: E402


def _module():
    chemin = os.path.join(RACINE, "ops", "publier_alluxe_bot_prive.py")
    spec = importlib.util.spec_from_file_location("publier_alluxe_bot_prive", chemin)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestLaMethodePubliee(unittest.TestCase):
    def setUp(self):
        self.methode = _module()._methode

    def test_elle_suit_le_canal_reellement_arme(self):
        cfg = BotConfig.load(os.path.join(RACINE, "robot.bitvavo.json"))
        canal = min(cfg.strategy.donchian_entrees)
        texte = self.methode(cfg)
        self.assertIn(f"{canal} jours", texte,
                      "le canal annonce ne vient pas de la configuration")
        # Le piege exact de septembre : un canal different de celui arme.
        if canal != 20:
            self.assertNotIn("20 jours", texte)

    def test_elle_dit_illimite_quand_le_pyramidage_l_est(self):
        cfg = BotConfig.load(os.path.join(RACINE, "robot.bitvavo.json"))
        texte = self.methode(cfg)
        if cfg.risk.pyramide_max >= 99:
            self.assertIn("illimite", texte)
            self.assertNotIn("3 etages", texte)
        else:
            self.assertIn(str(cfg.risk.pyramide_max), texte)

    def test_elle_suit_le_stop_temporel_et_le_suiveur(self):
        cfg = BotConfig.load(os.path.join(RACINE, "robot.bitvavo.json"))
        texte = self.methode(cfg)
        jours = round((cfg.trade.time_stop_minutes or 0) / 1440.0)
        self.assertIn(f"{jours} jours", texte)
        self.assertIn(f"{cfg.trade.trail_atr_mult:.1f}".replace(".", ",") + " ATR",
                      texte)

    def test_un_reglage_different_donne_un_texte_different(self):
        """Le coeur du sujet : si la config bouge, la phrase bouge."""
        cfg = BotConfig.load(os.path.join(RACINE, "robot.bitvavo.json"))
        avant = self.methode(cfg)
        cfg.strategy.donchian_entrees = [55]
        cfg.risk.pyramide_max = 3
        apres = self.methode(cfg)
        self.assertNotEqual(avant, apres)
        self.assertIn("55 jours", apres)
        self.assertIn("3 etages", apres)


if __name__ == "__main__":
    unittest.main()
