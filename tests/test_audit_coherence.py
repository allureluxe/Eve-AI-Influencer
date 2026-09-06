"""Les incoherences qui ne provoquent aucune erreur.

Ce fichier ne teste pas du code : il teste que la configuration en
service tient ensemble. Les defauts qu'il attrape ne plantent rien, ne
loguent rien, et faussent des decisions — la pire categorie.
"""
from __future__ import annotations

from helpers import *  # noqa: F401,F403 - insere la racine du projet dans sys.path

from gold_bot.croissance import PALIERS
from gold_bot.settings import BotConfig


def config():
    return BotConfig.load("robot.bitvavo.json")


class TestLesPaliersDeCroissanceSontAtteignables:
    """`effective_risk_pct` finit par min(max_risk_pct, risk).

    Un palier au-dessus de ce plafond est atteint sur le papier — le
    journal l'annonce, `plan_croissance.py` compte avec — mais le risque
    reel reste au plafond. La projection de croissance est alors fausse
    de l'ecart, precisement au moment ou le compte est cense accelerer.
    """

    def test_le_moteur_annonce_les_paliers_rabotes(self):
        cfg = config()
        problemes = cfg.paliers_inatteignables()
        attendus = [p for p in PALIERS if p.risque_pct > cfg.risk.max_risk_pct]
        assert len(problemes) == len(attendus)
        for p in attendus:
            assert any(p.nom in msg for msg in problemes)

    def test_le_detecteur_ne_crie_pas_quand_tout_va_bien(self):
        """L'envers : un avertissement permanent finit par etre ignore."""
        cfg = config()
        cfg.risk.max_risk_pct = max(p.risque_pct for p in PALIERS)
        assert cfg.paliers_inatteignables() == []


class TestLesBornesDeRisqueTiennentEnsemble:

    def test_le_risque_de_base_ne_depasse_pas_le_plafond_dur(self):
        cfg = config()
        assert cfg.risk.base_risk_pct <= cfg.risk.max_risk_pct

    def test_le_plancher_est_sous_le_risque_de_base(self):
        cfg = config()
        assert cfg.risk.min_risk_pct <= cfg.risk.base_risk_pct

    def test_le_budget_total_couvre_au_moins_deux_positions(self):
        """Un budget total sous deux fois le risque unitaire ne laisserait
        ouvrir qu'une position — les cinq autres places seraient
        decoratives."""
        cfg = config()
        assert cfg.risk.max_total_risk_pct >= 2 * cfg.risk.base_risk_pct

    def test_le_plancher_de_volatilite_suit_le_plafond_de_cout(self):
        """Sinon le robot evalue en boucle ce que le dimensionnement refuse."""
        cfg = config()
        borne = cfg.atr_minimal_utile()
        assert cfg.strategy.min_atr_price_ratio >= borne * 0.95, (
            f"plancher {cfg.strategy.min_atr_price_ratio:.5f} sous la borne "
            f"derivee {borne:.5f}")

    def test_le_filtre_de_spread_ne_depasse_pas_le_plafond_de_cout(self):
        cfg = config()
        plafond_en_r = cfg.risk.max_cost_ratio_pct / 100.0
        assert cfg.strategy.max_spread_atr_ratio <= plafond_en_r * cfg.trade.atr_stop_mult + 1e-9


class TestLeCoutEstCoherentDansLesTroisSections:
    """Le plafond de cout vit dans risk, strategy et trade.

    Les desaccorder ferait filtrer a un endroit ce qu'un autre laisse
    passer, sans qu'aucun message ne le dise.
    """

    def test_les_trois_plafonds_sont_egaux(self):
        cfg = config()
        assert (cfg.risk.max_cost_ratio_pct
                == cfg.strategy.max_cost_ratio_pct
                == cfg.trade.max_cost_ratio_pct)

    def test_le_ratio_minimal_est_coherent_avec_l_objectif(self):
        """Un objectif sous le ratio minimal exige ferait refuser CHAQUE
        trade au dimensionnement, en silence."""
        cfg = config()
        assert cfg.trade.tp_r_multiple >= cfg.risk.min_rr - 1e-9
        assert cfg.trade.tp_r_multiple >= cfg.strategy.min_rr - 1e-9


class TestLePlafondDurNeContourneRienDuTout:
    """max_risk_pct passe a 1,5 % le 30 aout, sur decision de l'operateur.

    Le plafond dur borne, il n'AUTORISE pas : c'est le palier de
    croissance qui decide, et lui exige un echantillon reel. Le relever
    ne doit donc rien changer tant que l'avantage n'est pas prouve —
    sinon on aurait simplement augmente le risque sur une strategie
    inconnue, ce que tout ce mecanisme existe pour empecher.
    """

    @staticmethod
    def _risque(trades, esperance_nette, variation_pct=0.0):
        from gold_bot.croissance import diagnostiquer
        from gold_bot.risk import RiskManager

        cfg = config()
        rm = RiskManager(cfg.risk)
        reference = 100.0
        equity = reference * (1 + variation_pct / 100.0)
        rm.sync_account(equity=equity, balance=equity)
        rm.account.reference_equity = reference
        diag = diagnostiquer(equity, 0.0, {
            "trades": trades, "esperance_R_nette": esperance_nette,
            "taux_reussite_pct": 55.0}, 0.0)
        # Le moteur applique exactement ceci a chaque cycle.
        rm.config.base_risk_pct = min(cfg.risk.base_risk_pct, diag.palier.risque_pct)
        return diag.palier.nom, rm.effective_risk_pct()[0]

    def test_sans_echantillon_le_risque_reste_a_la_preuve(self):
        nom, risque = self._risque(trades=7, esperance_nette=0.19)
        assert nom == "preuve"
        assert abs(risque - config().risk.base_risk_pct) < 1e-9, (
            f"{risque:.3f} % risques sur 7 trades : relever le plafond dur "
            "ne doit RIEN changer tant que l'avantage n'est pas prouve")

    def test_une_esperance_nette_negative_ne_promeut_jamais(self):
        """Meme avec 300 trades : c'est le signe qui compte, pas le nombre."""
        nom, risque = self._risque(trades=300, esperance_nette=-0.10)
        assert nom == "preuve"
        assert risque <= config().risk.base_risk_pct + 1e-9

    def test_l_avantage_confirme_debloque_le_palier_haut(self):
        """L'envers : un plafond qui ne sert jamais serait decoratif."""
        nom, _ = self._risque(trades=150, esperance_nette=0.20)
        assert nom == "acceleration"

    def test_le_plafond_dur_borne_toujours_l_echelle_adaptative(self):
        """L'echelle multiplie jusqu'a x1,8 ; le plafond doit rester dessus."""
        cfg = config()
        _, risque = self._risque(trades=150, esperance_nette=0.20, variation_pct=50.0)
        assert risque <= cfg.risk.max_risk_pct + 1e-9
