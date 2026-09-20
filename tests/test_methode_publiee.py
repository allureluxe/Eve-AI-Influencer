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


class TestLaFamilleMomentumNEstPasDecriteCommeUnCanal:
    """Lire le bon FICHIER ne suffit pas : il faut lire le bon CHAMP.

    Ce module a ete ecrit le 19 septembre pour que la methode affichee
    soit lue et non recopiee. Le 20, en armant la famille « momentum »
    sur la demo 2, il annoncait toujours « Canal 10 j » : il lisait
    `donchian_entrees`, qui existe dans TOUTES les configurations, y
    compris celles qui ne s'en servent pas. Un champ inutilise rend un
    chiffre plausible et faux -- la pire des deux options.
    """

    def _config_momentum(self):
        from gold_bot.settings import BotConfig
        cfg = BotConfig.load("robot.demo.json")
        cfg.strategy.famille = "momentum"
        cfg.strategy.momentum_formation = 28
        cfg.trade.detention_max_jours = 5.0
        cfg.trade.time_stop_minutes = 0.0
        return cfg

    def test_le_resume_ne_parle_jamais_de_canal(self):
        from gold_bot.methode import resume_methode
        texte = resume_methode(self._config_momentum())
        assert "Canal" not in texte, texte
        assert "Momentum 28 j" in texte, texte

    def test_la_phrase_ne_parle_jamais_de_cassure(self):
        from gold_bot.methode import phrase_methode
        texte = phrase_methode(self._config_momentum())
        assert "cassure" not in texte.lower(), texte
        assert "28 jours" in texte and "5e jour" in texte, texte

    def test_les_deux_comptes_demo_ne_disent_pas_la_meme_chose(self):
        # Un selecteur qui ne distingue pas ce qu'il selectionne ne sert
        # a rien. C'est arrive trois fois en deux jours.
        from gold_bot.settings import BotConfig
        from gold_bot.methode import resume_methode
        un = resume_methode(BotConfig.load("robot.demo.json"))
        deux = resume_methode(BotConfig.load("robot.demo2.json"))
        assert un != deux, f"les deux comptes affichent « {un} »"

    def test_la_famille_donchian_est_inchangee(self):
        from gold_bot.settings import BotConfig
        from gold_bot.methode import resume_methode, phrase_methode
        cfg = BotConfig.load("robot.demo.json")
        assert "Canal" in resume_methode(cfg)
        assert "cassure de canal" in phrase_methode(cfg)
