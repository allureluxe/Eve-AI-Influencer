"""Le capital decide de ce que la strategie peut faire.

Principe pose dans V8_ARCHITECTURE.md du robot tiers : « No fixed 220 EUR
assumption is embedded in the engine ». Ces tests verifient qu'aucun
capital n'est supposE, et surtout que le calibrage refuse plutot que de
forcer quand la fenetre des stops praticables est vide.
"""
from __future__ import annotations

import pytest

from helpers import *  # noqa: F401,F403 - insere la racine du projet dans sys.path

from gold_bot.calibrage import STOP_TYPIQUE, Calibrage, calibrer


class TestFenetreDesStops:
    def test_frais_bas_ouvrent_les_unites_rapides(self):
        """OKX a 0,10 % : le H1 redevient praticable."""
        c = calibrer(220, 1.0, 0.0010, 0.22, 0.5)
        assert c.viable
        assert "H1" in c.unites
        assert c.unite_conseillee == "H1"

    def test_frais_eleves_repoussent_vers_les_unites_lentes(self):
        """Bitvavo a 0,25 % : le H1 sort, seul le D1 tient."""
        c = calibrer(220, 5.0, 0.0025, 0.22, 0.5)
        assert c.viable
        assert "H1" not in c.unites
        assert c.unite_conseillee == "D1"

    def test_le_mur_du_bas_vient_des_frais(self):
        c = calibrer(1000, 1.0, 0.0025, 0.22, 0.5, plafond_cout_pct=15.0)
        assert c.stop_min_pct == pytest.approx(2 * 0.0025 / 0.15)

    def test_le_mur_du_haut_vient_du_ticket_minimum(self):
        """Plus le stop s'elargit, plus la position retrecit."""
        c = calibrer(200, 5.0, 0.0010, 0.25, 0.25)
        assert c.stop_max_pct == pytest.approx((200 * 0.0025) / 5.0)

    def test_sans_ticket_minimum_aucun_mur_haut(self):
        c = calibrer(220, 0.0, 0.0010, 0.22, 0.5)
        assert c.stop_max_pct == float("inf")
        assert c.viable


class TestRisqueRemonte:
    def test_le_risque_monte_pour_atteindre_le_ticket(self):
        """Sans cela, un petit capital ne pourrait rien ouvrir du tout."""
        c = calibrer(120, 5.0, 0.0025, 0.10, 1.0)
        assert c.risk_pct > c.risk_pct_demande
        assert c.viable

    def test_le_plafond_de_l_utilisateur_est_respecte(self):
        """Le calibrage ne depasse JAMAIS le maximum ecrit en configuration."""
        c = calibrer(40, 5.0, 0.0025, 0.10, 0.30)
        assert c.risk_pct <= 0.30 + 1e-9

    def test_le_risque_ne_baisse_jamais(self):
        c = calibrer(100000, 5.0, 0.0010, 0.22, 0.5)
        assert c.risk_pct == pytest.approx(0.22)


class TestCapitalInsuffisant:
    def test_fenetre_vide_refuse_au_lieu_de_forcer(self):
        """Un capital trop petit doit produire un refus, pas un trade fragile."""
        c = calibrer(20, 5.0, 0.0025, 0.22, 0.5)
        assert not c.viable
        assert c.unites == []
        assert c.explication

    def test_le_capital_manquant_est_chiffre(self):
        c = calibrer(20, 5.0, 0.0025, 0.22, 0.5)
        assert c.capital_minimum > 20
        # Au capital annonce, la fenetre doit effectivement s'ouvrir.
        mieux = calibrer(c.capital_minimum * 1.05, 5.0, 0.0025, 0.22, 0.5)
        assert mieux.stop_max_pct >= mieux.stop_min_pct

    def test_capital_nul(self):
        c = calibrer(0, 5.0, 0.0025, 0.22, 0.5)
        assert not c.viable
        assert "nul" in c.explication

    def test_fenetre_ouverte_mais_aucune_unite_dedans(self):
        """Cas subtil : la fenetre existe, mais aucune unite n'y tombe.

        A 50 EUR sur Bitvavo, les stops praticables vont de 3,33 % a 5 %.
        Le H4 (3,08 %) est trop serre, le D1 (6 %) trop large. Le robot
        doit refuser plutot que de forcer l'un des deux.
        """
        c = calibrer(50, 5.0, 0.0025, 0.22, 0.5)
        assert not c.viable
        assert c.stop_max_pct > c.stop_min_pct, "la fenetre n'est pas vide"
        assert c.unites == []
        assert c.capital_minimum > 50

    def test_le_capital_annonce_ouvre_vraiment_la_porte(self):
        """Le minimum annonce doit etre exact, pas approximatif."""
        c = calibrer(50, 5.0, 0.0025, 0.22, 0.5)
        assert calibrer(c.capital_minimum, 5.0, 0.0025, 0.22, 0.5).viable


class TestAucunCapitalSuppose:
    """Le point que V8_ARCHITECTURE.md exige explicitement."""

    def test_le_calibrage_varie_avec_le_capital(self):
        petit = calibrer(100, 5.0, 0.0025, 0.22, 1.0)
        grand = calibrer(10000, 5.0, 0.0025, 0.22, 1.0)
        assert grand.stop_max_pct > petit.stop_max_pct
        assert grand.positions >= petit.positions

    def test_aucun_capital_en_dur_dans_le_code(self):
        """La docstring cite 220 EUR, le CODE ne doit pas le contenir."""
        import ast
        import inspect
        import gold_bot.calibrage as mod
        arbre = ast.parse(inspect.getsource(mod))
        constantes = [n.value for n in ast.walk(arbre)
                      if isinstance(n, ast.Constant) and isinstance(n.value, (int, float))]
        for interdit in (220, 59.53, 1000):
            assert interdit not in constantes, \
                f"un capital code en dur ({interdit}) s'est glisse dans le calibrage"

    def test_unites_triees_de_la_plus_rapide_a_la_plus_lente(self):
        c = calibrer(5000, 1.0, 0.0005, 0.22, 1.0)
        indices = [list(STOP_TYPIQUE).index(u) for u in c.unites]
        assert indices == sorted(indices)


class TestResume:
    def test_resume_lisible(self):
        lignes = calibrer(220, 1.0, 0.0010, 0.22, 0.5).resume()
        assert any("stop praticable" in l for l in lignes)
        assert any("unites praticables" in l for l in lignes)

    def test_resume_annonce_le_refus(self):
        lignes = calibrer(20, 5.0, 0.0025, 0.22, 0.5).resume()
        assert any("AUCUNE" in l for l in lignes)

    def test_pourcentages_pas_multiplies_deux_fois(self):
        """Regression : le risque s'affichait a 33 % au lieu de 0,33 %."""
        c = calibrer(50, 5.0, 0.0025, 0.22, 1.0)
        ligne = next((l for l in c.resume() if "remonte" in l), "")
        if ligne:
            assert "33.330 %" not in ligne
            assert c.risk_pct < 1.0


class TestPrechauffageDuBacktest:
    """Les unites superieures doivent avoir leur propre historique.

    Les regrouper depuis la serie d'entree les affame : 1439 bougies H1 ne
    donnent que 60 bougies journalieres. Les indicateurs D1 n'etaient prets
    qu'aux trois quarts du parcours, et le backtest mesurait surtout son
    propre temps de chauffe — 1050 bougies sur 1439 rejetees pour
    « donnees insuffisantes ».
    """

    def test_le_prechauffage_ne_montre_pas_le_futur(self, monkeypatch):
        """Garde-fou : seules les bougies ANTERIEURES au parcours comptent.

        Prechauffer avec des bougies posterieures donnerait au robot des
        informations qu'il ne pouvait pas connaitre — le backtest
        deviendrait un oracle et ses resultats, une fiction.
        """
        import inspect

        from gold_bot.backtest import Backtester
        source = inspect.getsource(Backtester.run)
        assert "c.ts < debut" in source, \
            "le prechauffage doit filtrer sur l'anteriorite stricte"

    def test_le_prechauffage_est_tolerant_a_une_panne(self):
        """Une source muette ne doit pas faire echouer tout le backtest."""
        import inspect

        from gold_bot.backtest import Backtester
        source = inspect.getsource(Backtester.run)
        bloc = source[source.index("PRECHAUFFAGE"):source.index("warmup = 150")]
        assert "except" in bloc, "le prechauffage doit survivre a une source indisponible"


class TestCompteReel51Euros:
    """Le cas mesure sur le compte Bitvavo reel de l'utilisateur.

    Frais 0,250 % lus chez Bitvavo, ticket minimum 5,00 EUR, capital 51 EUR.
    """

    def test_51_euros_ne_passait_pas_a_0_5_pct(self):
        c = calibrer(51.0, 5.0, 0.0025, 0.22, 0.5)
        assert not c.viable, "a 0,5 % de risque maximum, 51 EUR est sous le seuil"
        assert c.capital_minimum == pytest.approx(60.0)

    def test_51_euros_passe_a_0_6_pct(self):
        c = calibrer(51.0, 5.0, 0.0025, 0.22, 0.6)
        assert c.viable
        assert c.unites == ["D1"], "seul le D1 tient a 0,25 % de frais"
        assert c.risk_pct == pytest.approx(0.588, abs=1e-3)

    def test_le_risque_reste_modeste_en_valeur_absolue(self):
        """0,588 % de 51 EUR : trente centimes par trade."""
        c = calibrer(51.0, 5.0, 0.0025, 0.22, 0.6)
        assert 51.0 * c.risk_pct / 100 < 0.35

    def test_la_configuration_livree_correspond(self):
        from gold_bot.settings import BotConfig
        cfg = BotConfig.load("robot.bitvavo.json")
        assert cfg.risk.max_risk_pct == pytest.approx(0.6)
        assert cfg.validate() == []


class TestRegistreCentralise:
    """Le verrou de devise a ete oublie deux fois avant d'etre centralise.

    D'abord dans le backtest, puis dans les trois commandes du terminal.
    Chaque appelant reconstruisait le registre a sa facon, et un oubli ne
    produisait aucune erreur — juste des prix en dollars pour des ordres
    en euros.
    """

    def test_un_seul_point_de_construction(self):
        import pathlib
        racine = pathlib.Path(__file__).resolve().parent.parent
        fautifs = []
        for chemin in list(racine.glob("*.py")) + list(racine.glob("gold_bot/**/*.py")):
            if chemin.name in ("__init__.py", "engine.py"):
                continue
            texte = chemin.read_text(encoding="utf-8", errors="replace")
            if "build_registry(" in texte and "def build_registry" not in texte:
                fautifs.append(chemin.name)
        assert not fautifs, (
            f"ces fichiers construisent le registre directement au lieu de "
            f"passer par registre_pour() : {fautifs}")

    def test_le_registre_herite_de_la_devise_du_broker(self):
        from gold_bot.engine import registre_pour
        from gold_bot.settings import BotConfig
        cfg = BotConfig.load("robot.bitvavo.json")
        assert registre_pour(cfg).devise_crypto == "EUR"

    def test_un_broker_en_dollars_garde_ses_sources(self):
        from gold_bot.engine import registre_pour
        from gold_bot.settings import BotConfig
        cfg = BotConfig.load("robot.bitvavo.json")
        cfg.engine.broker = "binance_spot"
        assert registre_pour(cfg).devise_crypto == ""
