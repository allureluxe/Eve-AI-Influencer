"""Le plan de croissance : le risque monte apres PREUVE, pas par impatience.

Un compte grandit par `risque x esperance`. Ces deux facteurs ne jouent pas
le meme role : l'esperance porte le SIGNE, le risque n'est qu'un
amplificateur. Augmenter le second sans connaitre le premier ne fait pas
grandir plus vite — ca amplifie ce qui est deja la, perte comprise.
"""
from __future__ import annotations

import math

import pytest

from helpers import *  # noqa: F401,F403 - insere la racine du projet dans sys.path

from gold_bot.croissance import (ECHANTILLON_MINIMAL, PALIERS, Diagnostic,
                                 diagnostiquer, drawdown_probable,
                                 palier_courant, projeter)


def stats(trades: int, esperance: float, reussite: float = 45.0) -> dict:
    return {"trades": trades, "esperance_R": esperance,
            "taux_reussite_pct": reussite}


class TestUneEsperanceNegativeNeSeRattrapePas:
    """LE point du module. Tout le reste en decoule."""

    def test_esperance_negative_rend_la_cible_inatteignable(self):
        for risque in (0.6, 1.0, 1.5, 5.0):
            jours = projeter(186.0, 3000.0, risque, -0.10, 6.0)
            assert jours is None, (
                f"a {risque} % de risque, une esperance negative ne doit "
                "jamais produire une duree : elle rend la cible impossible")

    def test_esperance_nulle_non_plus(self):
        assert projeter(186.0, 3000.0, 1.5, 0.0, 6.0) is None

    def test_augmenter_le_risque_n_inverse_jamais_le_signe(self):
        """Le risque amplifie, il ne corrige pas.

        C'est la croyance qui coute le plus cher : « je perds, donc je
        monte la taille pour me refaire ».
        """
        petit = projeter(186.0, 3000.0, 0.6, -0.05, 6.0)
        gros = projeter(186.0, 3000.0, 5.0, -0.05, 6.0)
        assert petit is None and gros is None

    def test_avec_une_esperance_positive_le_risque_accelere(self):
        lent = projeter(186.0, 3000.0, 0.6, 0.20, 6.0)
        rapide = projeter(186.0, 3000.0, 1.5, 0.20, 6.0)
        assert lent is not None and rapide is not None
        assert rapide < lent


class TestLesPaliersExigentUnePreuve:
    def test_sans_historique_on_reste_au_palier_le_plus_prudent(self):
        p = palier_courant(trades=0, esperance_r=0.0, capital=186.0)
        assert p.nom == "preuve"
        assert p.risque_pct == pytest.approx(PALIERS[0].risque_pct)

    def test_un_echantillon_trop_court_ne_debloque_rien(self):
        """Dix trades gagnants ne prouvent rien : c'est du bruit."""
        p = palier_courant(trades=10, esperance_r=0.80, capital=500.0)
        assert p.nom == "preuve", (
            "une esperance flatteuse sur 10 trades a fait monter le risque")

    def test_une_esperance_etablie_debloque_le_palier_suivant(self):
        p = palier_courant(trades=ECHANTILLON_MINIMAL, esperance_r=0.10,
                           capital=500.0)
        assert p.nom == "croissance"

    def test_une_esperance_negative_sur_grand_echantillon_ne_debloque_rien(self):
        """Le cas du 28 aout : 72 trades, -0,406 R."""
        p = palier_courant(trades=72, esperance_r=-0.406, capital=186.0)
        assert p.nom == "preuve"

    def test_les_paliers_sont_de_plus_en_plus_exigeants(self):
        for avant, apres in zip(PALIERS, PALIERS[1:]):
            assert apres.risque_pct > avant.risque_pct
            assert apres.trades_minimum >= avant.trades_minimum
            assert apres.esperance_minimale >= avant.esperance_minimale

    def test_le_plafond_dur_du_robot_n_est_jamais_depasse(self):
        """validate() refuse au-dela de 1,5 % : aucun palier ne doit y mener."""
        for p in PALIERS:
            assert p.risque_pct <= 1.5


class TestFiabiliteDeLEsperance:
    def test_une_esperance_dans_le_bruit_est_signalee(self):
        d = diagnostiquer(500.0, 3000.0, stats(50, 0.05), 6.0)
        # 2 / sqrt(50) = 0,283 : +0,05 R est tres en dessous.
        assert d.echantillon_suffisant()
        assert not d.esperance_fiable()

    def test_une_esperance_franche_sur_grand_echantillon_est_retenue(self):
        d = diagnostiquer(500.0, 3000.0, stats(400, 0.25), 6.0)
        assert d.esperance_fiable()

    def test_le_seuil_de_fiabilite_se_resserre_avec_l_echantillon(self):
        """Plus de trades, moins d'incertitude : c'est tout l'interet d'attendre."""
        assert not diagnostiquer(500.0, 3000.0, stats(50, 0.20), 6.0).esperance_fiable()
        assert diagnostiquer(500.0, 3000.0, stats(400, 0.20), 6.0).esperance_fiable()


class TestLaDureeEstUneConsequence:
    def test_de_186_a_3000_prend_des_mois_meme_avec_un_bon_avantage(self):
        """L'honnetete du chiffre compte plus que sa gentillesse.

        +0,20 R est deja un bon systeme — le rejeu H4 du 28 aout donnait
        +0,267 R. Meme la, x16 ne se fait pas en quelques semaines.
        """
        jours = projeter(186.0, 3000.0, 1.5, 0.20, 6.0)
        assert jours is not None
        assert jours > 100, f"projection irrealiste : {jours:.0f} jours"

    def test_la_formule_compose_bien(self):
        """Verification directe de l'arithmetique."""
        capital, cible, risque, esp, cadence = 100.0, 200.0, 1.0, 0.10, 5.0
        jours = projeter(capital, cible, risque, esp, cadence)
        g = risque / 100.0 * esp
        attendu = math.log(cible / capital) / (cadence * math.log(1 + g))
        assert jours == pytest.approx(attendu)

    def test_une_cible_deja_atteinte_ne_demande_aucun_jour(self):
        assert projeter(3000.0, 3000.0, 1.0, 0.2, 6.0) == pytest.approx(0.0)


class TestLaSerieNoire:
    def test_un_risque_plus_eleve_creuse_le_drawdown(self):
        petit = drawdown_probable(0.6, 45.0)
        gros = drawdown_probable(1.5, 45.0)
        assert gros["perte_pct"] > petit["perte_pct"]

    def test_une_reussite_plus_faible_allonge_la_serie(self):
        assert (drawdown_probable(1.0, 30.0)["serie_attendue"]
                > drawdown_probable(1.0, 60.0)["serie_attendue"])

    def test_la_serie_attendue_reste_plausible(self):
        """A 45 % de reussite sur 200 trades, ~9 pertes d'affilee."""
        d = drawdown_probable(1.0, 45.0, trades=200)
        assert 6 <= d["serie_attendue"] <= 12


class TestLeMoteurApplique:
    """Le plan ne sert a rien s'il n'est qu'un rapport."""

    def test_le_moteur_plafonne_le_risque_sur_le_palier(self):
        import inspect
        from gold_bot.engine import TradingEngine
        source = inspect.getsource(TradingEngine._appliquer_palier_de_croissance)
        assert "diagnostiquer" in source
        assert "base_risk_pct" in source

    def test_le_palier_ne_descend_jamais_sous_le_ticket_minimum(self):
        """Sinon le robot se figerait en croyant se proteger.

        Le calibrage remonte le risque quand le lot minimum de la
        plateforme l'exige. Ce n'est pas une preference, c'est une
        condition d'existence du trade : le palier plafonne ce qu'on
        CHOISIT de risquer, pas ce que l'arithmetique impose.
        """
        import inspect
        from gold_bot.engine import TradingEngine
        source = inspect.getsource(TradingEngine._appliquer_palier_de_croissance)
        assert "_risque_plancher" in source
        assert "max(" in source, (
            "le plancher du ticket minimum n'est plus respecte")

    def test_le_risque_configure_est_memorise_avant_toute_correction(self):
        import inspect
        from gold_bot.engine import TradingEngine
        source = inspect.getsource(TradingEngine.__init__)
        assert "_risque_configure" in source, (
            "sans reference au risque voulu, un plafond applique une fois "
            "deviendrait definitif")


class _FauxMoteur:
    """Le strict necessaire pour exercer la methode du moteur, sans reseau."""

    from gold_bot.engine import TradingEngine
    _appliquer_palier_de_croissance = TradingEngine._appliquer_palier_de_croissance

    def __init__(self, demande, plancher, stats_journal, equity=186.0):
        from gold_bot.risk import RiskConfig, RiskManager
        self.risk = RiskManager(RiskConfig(base_risk_pct=demande))
        self.risk.account.equity = equity
        self._risque_configure = demande
        self._risque_plancher = plancher
        # Debut de l'echantillon de la strategie en cours : le palier ne
        # compte que les trades posterieurs.
        self._strategie_depuis = 0.0
        self.journal = type(
            "J", (), {"stats": lambda _s, since=0.0: stats_journal})()


class TestLePalierEstVraimentApplique:
    """Pas de l'inspection de source : le comportement observe."""

    def test_sans_historique_le_risque_demande_est_rabaisse(self):
        m = _FauxMoteur(demande=1.5, plancher=0.0, stats_journal=stats(0, 0.0))
        m._appliquer_palier_de_croissance()
        assert m.risk.config.base_risk_pct == pytest.approx(0.60), (
            "une configuration a 1,5 % doit etre ramenee au palier « preuve »")

    def test_une_esperance_negative_maintient_le_plafond(self):
        m = _FauxMoteur(demande=1.5, plancher=0.0,
                        stats_journal=stats(72, -0.406))
        m._appliquer_palier_de_croissance()
        assert m.risk.config.base_risk_pct == pytest.approx(0.60)

    def test_un_avantage_prouve_rend_le_risque_demande(self):
        m = _FauxMoteur(demande=1.5, plancher=0.0,
                        stats_journal=stats(200, 0.25))
        m._appliquer_palier_de_croissance()
        assert m.risk.config.base_risk_pct == pytest.approx(1.5), (
            "l'avantage est etabli : le palier ne doit plus rien retenir")

    def test_le_palier_ne_rend_jamais_plus_que_ce_qui_est_demande(self):
        """Le palier plafonne ; il n'augmente pas le risque tout seul."""
        m = _FauxMoteur(demande=0.4, plancher=0.0,
                        stats_journal=stats(400, 0.40))
        m._appliquer_palier_de_croissance()
        assert m.risk.config.base_risk_pct == pytest.approx(0.4)

    def test_le_ticket_minimum_l_emporte_sur_le_palier(self):
        """Sans cela le robot se figerait : aucun lot ne serait atteignable."""
        m = _FauxMoteur(demande=1.5, plancher=0.9, stats_journal=stats(0, 0.0))
        m._appliquer_palier_de_croissance()
        assert m.risk.config.base_risk_pct == pytest.approx(0.9)

    def test_un_journal_illisible_ne_bloque_pas_le_cycle(self):
        """Un diagnostic rate ne doit jamais arreter le robot."""
        m = _FauxMoteur(demande=0.8, plancher=0.0, stats_journal={})

        def casse(_self=None):
            raise RuntimeError("journal corrompu")

        m.journal = type("J", (), {"stats": casse})()
        m._appliquer_palier_de_croissance()          # ne doit pas lever
        assert m.risk.config.base_risk_pct == pytest.approx(0.8)


class TestLEchantillonSuitLaStrategie:
    """Un echantillon ne veut dire quelque chose que s'il mesure UNE strategie.

    Observe le 30 aout : quelques minutes apres le passage au M30, le plan
    annoncait « 8 trades, 0,0 % de reussite, esperance -0,109 R » et
    refusait de promouvoir le risque. Ces huit trades venaient de la
    configuration precedente. La nouvelle n'en avait fait aucun.

    Deux degats, et le second est le pire : le palier reste verrouille par
    des pertes qui ne le concernent pas, et l'operateur croit que la
    strategie qu'il vient d'armer perd.
    """

    @staticmethod
    def _config(**changements):
        from gold_bot.settings import BotConfig
        cfg = BotConfig.load("robot.bitvavo.json")
        for cle, valeur in changements.items():
            section = cfg.trade if hasattr(cfg.trade, cle) else cfg.strategy
            setattr(section, cle, valeur)
        return cfg

    def test_l_unite_de_temps_change_l_empreinte(self):
        from gold_bot.version_strategie import empreinte
        assert empreinte(self._config(entry_tf="M30")) != \
            empreinte(self._config(entry_tf="H4"))

    def test_le_stop_et_l_objectif_changent_l_empreinte(self):
        from gold_bot.version_strategie import empreinte
        base = empreinte(self._config())
        assert empreinte(self._config(atr_stop_mult=2.2)) != base
        assert empreinte(self._config(tp_r_multiple=3.0)) != base

    def test_le_risque_par_trade_ne_change_PAS_l_empreinte(self):
        """Le palier fait varier le risque : il ne doit pas s'auto-invalider.

        Changer la taille des positions ne change pas la qualite des
        signaux. Si le risque comptait dans l'empreinte, chaque promotion
        de palier remettrait l'echantillon a zero — et aucun palier ne
        pourrait jamais etre atteint.
        """
        from gold_bot.version_strategie import empreinte
        cfg = self._config()
        avant = empreinte(cfg)
        cfg.risk.base_risk_pct = 1.5
        cfg.risk.max_risk_pct = 1.5
        assert empreinte(cfg) == avant

    def test_la_meme_configuration_donne_la_meme_empreinte(self):
        from gold_bot.version_strategie import empreinte
        assert empreinte(self._config()) == empreinte(self._config())

    def test_le_palier_ne_compte_que_les_trades_de_la_strategie(self):
        """Le moteur doit passer la fenetre au journal, pas tout lire."""
        import inspect
        from gold_bot.engine import TradingEngine
        source = inspect.getsource(TradingEngine._appliquer_palier_de_croissance)
        assert "_strategie_depuis" in source, (
            "le palier lit tout l'historique : une strategie neuve heriterait "
            "des pertes de celle qu'elle remplace")
