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
