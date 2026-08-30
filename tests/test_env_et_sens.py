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


class TestSommeilSurSpread:
    """61 instruments sur 70 refuses au spread, re-interroges a chaque cycle.

    Un spread trop large est une propriete de liquidite : il tient des
    heures. Redemander tout l'historique d'un instrument pour lui opposer
    le meme refus a chaque tour gaspille le quota de la plateforme et
    allonge le scan — 26,7 secondes mesurees pour une cadence de 10.
    """

    class _FauxScanner:
        def __init__(self):
            self.endormis = {}

        def sleep_symbol(self, symbole, secondes, motif):
            self.endormis[symbole] = (secondes, motif)

    @staticmethod
    def _evaluation(symbole, gates_rates, valide=False):
        from gold_bot.strategy import Evaluation, Gate
        ev = Evaluation(symbol=symbole, asset_class="crypto")
        ev.gates = [Gate(nom, False, "") for nom in gates_rates]
        if valide:
            ev.gates = [Gate("spread", True, "")]
        return ev

    def _resultat(self, evaluations):
        from gold_bot.strategy import Evaluation  # noqa: F401
        return type("R", (), {"evaluations": evaluations})()

    def _moteur(self):
        from gold_bot.dual_scalping_engine import MultiEntryScalpingMixin
        moteur = MultiEntryScalpingMixin.__new__(MultiEntryScalpingMixin)
        moteur.scanner = self._FauxScanner()
        return moteur

    def test_un_refus_de_spread_endort_l_instrument(self):
        moteur = self._moteur()
        moteur._endormir_les_spreads_trop_larges(
            self._resultat([self._evaluation("PEPEUSD", ["spread"])]))
        assert "PEPEUSD" in moteur.scanner.endormis

    def test_le_sommeil_reste_court(self):
        """Un spread s'elargit sur annonce puis se resserre."""
        from gold_bot.dual_scalping_engine import MultiEntryScalpingMixin
        assert 0 < MultiEntryScalpingMixin.SOMMEIL_SPREAD_SECONDES <= 3600, (
            "un sommeil trop long appauvrirait l'univers sans qu'on le voie")

    def test_un_refus_multiple_n_endort_pas(self):
        """Refuse aussi ailleurs : il peut redevenir valide sans changer de liquidite."""
        moteur = self._moteur()
        moteur._endormir_les_spreads_trop_larges(
            self._resultat([self._evaluation("BTCUSD", ["spread", "volatilite"])]))
        assert moteur.scanner.endormis == {}

    def test_un_instrument_valide_n_est_jamais_endormi(self):
        moteur = self._moteur()
        ev = self._evaluation("UNIUSD", [], valide=True)
        moteur._endormir_les_spreads_trop_larges(self._resultat([ev]))
        assert moteur.scanner.endormis == {}


class TestUnRobotArreteLeDit:
    """Un robot qui ne cherche pas doit le dire, et fort.

    Le 30 aout, le robot est reste arrete sur un drawdown TOUTE la
    journee. Les cycles tournaient, le journal paraissait sain, et le
    motif — « drawdown maximal atteint » — etait journalise en debug, donc
    invisible en production. L'operateur a cherche du cote de la strategie
    pendant des heures pour un coupe-circuit.
    """

    def test_le_motif_de_blocage_est_un_avertissement(self):
        import inspect
        from gold_bot.dual_scalping_engine import MultiEntryScalpingMixin
        source = inspect.getsource(MultiEntryScalpingMixin._look_for_entry)
        assert "logger.warning" in source, (
            "le motif de non-recherche n'est pas journalise en avertissement : "
            "un robot fige passerait de nouveau inapercu")
        assert "logger.debug(\"pas de recherche" not in source

    def test_le_rappel_est_periodique_et_non_a_chaque_cycle(self):
        """Ni silencieux, ni une ligne toutes les dix secondes."""
        from gold_bot.dual_scalping_engine import MultiEntryScalpingMixin
        assert 60.0 <= MultiEntryScalpingMixin.INTERVALLE_RAPPEL_REFUS <= 3600.0

    def test_la_reprise_est_annoncee(self):
        import inspect
        from gold_bot.dual_scalping_engine import MultiEntryScalpingMixin
        source = inspect.getsource(MultiEntryScalpingMixin._look_for_entry)
        assert "recherche reprise" in source, (
            "sans message de reprise, on ne sait pas si le deblocage a marche")


class TestLeRecalageRefuseUnServiceActif:
    """Recaler l'etat pendant que le robot tourne ne sert a rien.

    Le service garde son etat EN MEMOIRE et le reecrit a chaque cycle : le
    recalage tient quelques secondes, puis le sommet revient. C'est ce qui
    a fait croire le 30 aout que l'arret avait ete leve alors qu'il ne
    l'etait pas.
    """

    def test_l_outil_verifie_le_service(self):
        import pathlib
        racine = pathlib.Path(__file__).resolve().parent.parent
        texte = (racine / "reinitialiser_arret.py").read_text(encoding="utf-8")
        assert "service_actif" in texte
        assert "systemctl" in texte

    def test_sans_systemctl_on_ne_bloque_pas(self, monkeypatch):
        """Hors d'un VPS systemd, l'outil doit rester utilisable."""
        import sys
        sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
        import importlib
        module = importlib.import_module("reinitialiser_arret")
        monkeypatch.setattr(module.shutil if hasattr(module, "shutil") else __import__("shutil"),
                            "which", lambda _nom: None)
        assert module.service_actif() is False


class TestPurgeDeLaSemaineHeritee:
    """Le compteur hebdomadaire est DISTINCT de l'arret.

    Le moteur remet la semaine a zero quand l'empreinte de strategie
    change. Mais si le changement a deja eu lieu — l'empreinte est deja
    enregistree — le compteur reste, et le robot trade a 40 % de sa taille
    sans qu'aucun arret ne soit visible. L'outil doit donc pouvoir purger
    la semaine SANS qu'il y ait de drawdown a recaler.
    """

    def test_l_outil_traite_la_semaine_independamment_de_l_arret(self):
        import pathlib
        racine = pathlib.Path(__file__).resolve().parent.parent
        texte = (racine / "reinitialiser_arret.py").read_text(encoding="utf-8")
        assert "_semaine_a_purger" in texte
        assert "not etat.halted and sommet <= capital and semaine" in texte, (
            "la semaine n'est purgeable que via un recalage de drawdown : "
            "un robot qui tourne a moitie de taille resterait ainsi")

    def test_une_semaine_negative_est_detectee(self, tmp_path, monkeypatch):
        import json
        import sys
        racine = __import__("pathlib").Path(__file__).resolve().parent.parent
        sys.path.insert(0, str(racine))
        fichier = tmp_path / "obj.json"
        fichier.write_text(json.dumps({
            "realized_this_week": -5.79, "trades_this_week": 8,
            "week_start_equity": 100.0, "level": 1}), encoding="utf-8")
        monkeypatch.setenv("GB_OBJECTIVE_FILE", str(fichier))

        import importlib
        module = importlib.import_module("reinitialiser_arret")
        from gold_bot.settings import BotConfig
        cfg = BotConfig.load("robot.bitvavo.json")

        resultat = module._semaine_a_purger(cfg)
        assert resultat is not None
        ancien, mult, _ = resultat
        assert ancien == pytest.approx(-5.79)
        assert mult < 1.0, "une semaine negative doit reduire la taille"

    def test_une_semaine_neutre_n_est_pas_signalee(self, tmp_path, monkeypatch):
        import json
        import sys
        racine = __import__("pathlib").Path(__file__).resolve().parent.parent
        sys.path.insert(0, str(racine))
        fichier = tmp_path / "obj.json"
        fichier.write_text(json.dumps({"realized_this_week": 0.0}), encoding="utf-8")
        monkeypatch.setenv("GB_OBJECTIVE_FILE", str(fichier))

        import importlib
        module = importlib.import_module("reinitialiser_arret")
        from gold_bot.settings import BotConfig
        assert module._semaine_a_purger(BotConfig.load("robot.bitvavo.json")) is None
