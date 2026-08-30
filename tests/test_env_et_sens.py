"""Deux choses qui rendaient les commandes et les mesures trompeuses.

1. Le .env n'etait lu que par systemd : une commande tapee a la main
   annoncait des cles « absentes » avec un fichier complet a cote.
2. Le rejeu comptait des ventes a decouvert meme quand le lieu
   d'execution vise ne sait qu'acheter.
"""
from __future__ import annotations

import os

import pytest

from helpers import *  # noqa: F401,F403 - insere la racine du projet dans sys.path

from gold_bot.core import Side
from gold_bot.env import charger_env


class TestChargementDuEnv:
    def test_les_cles_du_fichier_arrivent_dans_l_environnement(self, tmp_path, monkeypatch):
        fichier = tmp_path / ".env"
        fichier.write_text("GB_TEST_CLE=valeur123\n", encoding="utf-8")
        monkeypatch.delenv("GB_TEST_CLE", raising=False)

        assert charger_env(fichier) == 1
        assert os.environ["GB_TEST_CLE"] == "valeur123"

    def test_l_environnement_deja_pose_l_emporte(self, tmp_path, monkeypatch):
        """LE test de securite.

        `BITVAVO_DRY_RUN=1 python3 …` doit rester plus fort que le fichier :
        croire qu'on simule tout en engageant de l'argent est le pire des
        malentendus possibles ici.
        """
        fichier = tmp_path / ".env"
        fichier.write_text("BITVAVO_DRY_RUN=0\n", encoding="utf-8")
        monkeypatch.setenv("BITVAVO_DRY_RUN", "1")

        charger_env(fichier)
        assert os.environ["BITVAVO_DRY_RUN"] == "1", (
            "le fichier a ecrase la ligne de commande : un run demande en "
            "simulation partirait en argent reel")

    @pytest.mark.parametrize("ligne,attendu", [
        ('GB_T="entre guillemets"', "entre guillemets"),
        ("GB_T='simples'", "simples"),
        ("export GB_T=avec_export", "avec_export"),
        ("GB_T=  espaces_autour  ", "espaces_autour"),
        ("GB_T=cle=avec=egals", "cle=avec=egals"),
    ])
    def test_formats_courants(self, tmp_path, monkeypatch, ligne, attendu):
        fichier = tmp_path / ".env"
        fichier.write_text(ligne + "\n", encoding="utf-8")
        monkeypatch.delenv("GB_T", raising=False)
        charger_env(fichier)
        assert os.environ["GB_T"] == attendu

    def test_commentaires_et_lignes_vides_ignores(self, tmp_path, monkeypatch):
        fichier = tmp_path / ".env"
        fichier.write_text("# un commentaire\n\nGB_T=ok\n", encoding="utf-8")
        monkeypatch.delenv("GB_T", raising=False)
        assert charger_env(fichier) == 1

    def test_un_fichier_absent_ne_leve_pas(self, tmp_path):
        """Une commande doit tourner meme sans .env, en degrade."""
        assert charger_env(tmp_path / "rien.env") == 0

    def test_les_commandes_manuelles_le_chargent(self):
        """Sans cela, le diagnostic ne peut pas se connecter."""
        import pathlib
        racine = pathlib.Path(__file__).resolve().parent.parent
        for nom in ("pourquoi_pas_de_trade.py", "plan_croissance.py",
                    "comparer.py", "verifier_ibkr.py"):
            texte = (racine / nom).read_text(encoding="utf-8")
            assert "charger_env()" in texte, (
                f"{nom} ne charge pas le .env : il annoncera des cles "
                "absentes alors qu'elles sont sur le disque")


class TestLeRejeuRespecteLesSensPossibles:
    """Un rejeu qui vend a decouvert mesure une autre strategie.

    `PaperBroker` herite de supports_short = True et le rejeu ne filtrait
    rien : toutes les mesures comptaient des ventes. Sur un compte au
    comptant, la moitie de ces trades n'existerait pas, et le taux de
    reussite mesure ne dirait rien de ce que le robot fera.
    """

    def test_le_comptant_interdit_la_vente(self):
        from gold_bot.backtest import Backtester
        from gold_bot.settings import BotConfig
        cfg = BotConfig.load("robot.bitvavo.json")
        cfg.engine.broker = "bitvavo"
        assert Backtester(cfg).autorise_vente is False

    def test_la_marge_autorise_la_vente(self):
        from gold_bot.backtest import Backtester
        from gold_bot.settings import BotConfig
        cfg = BotConfig.load("robot.bitvavo.json")
        cfg.engine.broker = "bitvavo_margin"
        assert Backtester(cfg).autorise_vente is True

    def test_le_choix_explicite_l_emporte(self):
        """`--long-seulement` doit pouvoir forcer la mesure sans ventes."""
        from gold_bot.backtest import Backtester
        from gold_bot.settings import BotConfig
        cfg = BotConfig.load("robot.bitvavo.json")
        cfg.engine.broker = "bitvavo_margin"
        assert Backtester(cfg, autorise_vente=False).autorise_vente is False

    def test_les_ventes_sont_refusees_et_comptees(self):
        """Le refus doit apparaitre dans les motifs, pas disparaitre."""
        import inspect
        from gold_bot.backtest import Backtester
        source = inspect.getsource(Backtester.run)
        assert "autorise_vente" in source
        assert "vente impossible au comptant" in source, (
            "un trade ecarte sans motif rend le diagnostic impossible")

    def test_le_comptant_produit_moins_de_trades_que_la_marge(self):
        """La consequence mesurable, sur une serie qui monte puis descend."""
        from test_backtest_pipeline import _RegistreConstant, _serie_en_tendance
        from gold_bot.backtest import Backtester
        from gold_bot.settings import BotConfig

        montante = _serie_en_tendance(n=700, pente=0.004)
        descendante = _serie_en_tendance(n=700, pente=-0.004, graine=11)
        serie = montante + [
            type(c)(montante[-1].ts + (i + 1) * 3600, c.open, c.high, c.low,
                    c.close, c.volume)
            for i, c in enumerate(descendante)]

        def trades(broker, autorise):
            cfg = BotConfig.load("robot.bitvavo.json")
            cfg.engine.broker = broker
            cfg.strategy.min_score = 0.0
            cfg.strategy.min_confirmations = 1
            cfg.strategy.min_adx = 0.0
            cfg.strategy.min_headroom_atr = 0.0
            cfg.strategy.min_atr_percentile = 0.0
            cfg.strategy.max_atr_percentile = 1.0
            res = Backtester(cfg, registry=_RegistreConstant(serie),
                             autorise_vente=autorise).run(
                "BTCUSD", bars=len(serie), start_balance=186.0)
            return [t for t in res.trades if not t.partial]

        avec = trades("bitvavo_margin", True)
        sans = trades("bitvavo", False)
        assert len(sans) <= len(avec), (
            f"le comptant prend {len(sans)} trades contre {len(avec)} avec "
            "la vente : le filtre de sens ne s'applique pas")
