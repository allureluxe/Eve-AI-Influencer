"""Les decisions de l'operateur, verrouillees.

Plusieurs sessions travaillent sur cette branche et sur la meme
configuration, qui engage de l'argent reel. Un fichier de consignes se
contourne sans bruit ; un test rouge, non.

Ces valeurs ont ete choisies apres audit chiffre, le 27 aout. Elles ne
sont pas des valeurs par defaut a optimiser. Si l'un de ces tests echoue,
ce n'est pas le test qu'il faut changer — c'est qu'un reglage a bouge sans
que la decision correspondante ait ete prise.

Le raisonnement complet est dans CLAUDE.md, a la racine du depot.
"""
from __future__ import annotations

import pytest

from helpers import *  # noqa: F401,F403 - insere la racine du projet dans sys.path

from gold_bot.calibrage import COUT_INCOMPRESSIBLE, calibrer
from gold_bot.promotion import Promotion
from gold_bot.settings import BotConfig

FRAIS_BITVAVO = 0.0025          # par cote, palier de base


def config() -> BotConfig:
    return BotConfig.load("robot.bitvavo.json")


class TestPlafondDeCout:
    """Les frais ne peuvent pas manger plus de 15 % du risque.

    Remonter ce plafond « garde le M15 viable » en retirant la mesure, pas
    en changeant le probleme : au tarif normal un aller-retour M15 coute
    0,78 R, et il faut alors gagner plus d'une fois sur deux pour seulement
    rentrer dans ses frais.
    """

    @pytest.mark.parametrize("section", ["risk", "strategy", "trade"])
    def test_le_plafond_reste_a_15_pour_cent(self, section):
        valeur = getattr(getattr(config(), section), "max_cost_ratio_pct")
        assert valeur == pytest.approx(15.0), (
            f"{section}.max_cost_ratio_pct vaut {valeur} au lieu de 15.0 — "
            "voir CLAUDE.md avant de modifier")

    def test_ce_plafond_donne_bien_le_d1_au_tarif_normal(self):
        """La consequence voulue, verifiee et non supposee."""
        cfg = config()
        cal = calibrer(equity=51.0, ticket_minimum=5.0,
                       frais_par_cote=FRAIS_BITVAVO,
                       risk_pct_demande=cfg.risk.base_risk_pct,
                       risk_pct_max=cfg.risk.max_risk_pct,
                       plafond_cout_pct=cfg.risk.max_cost_ratio_pct,
                       plafond_positions=cfg.risk.max_positions,
                       part_engageable_pct=cfg.risk.max_capital_engaged_pct)
        assert cal.unites == ["D1"]

    def test_aucun_capital_ne_debloque_une_unite_plus_rapide(self):
        """Ce n'est pas un probleme d'argent, c'est une division.

        Le stop minimum ne depend que des frais et du plafond de cout : le
        capital n'entre pas dans ce calcul. Relancer le calibrage de 51 EUR
        a 20 000 EUR le montre.
        """
        cfg = config()
        for equity in (51.0, 500.0, 5_000.0, 20_000.0):
            cal = calibrer(equity=equity, ticket_minimum=5.0,
                           frais_par_cote=FRAIS_BITVAVO,
                           risk_pct_demande=cfg.risk.base_risk_pct,
                           risk_pct_max=cfg.risk.max_risk_pct,
                           plafond_cout_pct=cfg.risk.max_cost_ratio_pct,
                           plafond_positions=cfg.risk.max_positions,
                           part_engageable_pct=cfg.risk.max_capital_engaged_pct)
            assert cal.unites == ["D1"], f"a {equity:.0f} EUR : {cal.unites}"


class TestAucunLevier:
    """Le compte est au comptant.

    Un levier multiplie les gains ET les pertes. Sur un systeme dont
    l'esperance n'est pas etablie, il ne rend rien gagnant : il fait perdre
    plus vite.
    """

    def test_le_levier_reste_a_un(self):
        levier = config().risk.max_leverage
        assert levier == pytest.approx(1.0), (
            f"max_leverage vaut {levier} — voir CLAUDE.md avant de modifier")


class TestFenetreSansCommission:
    """Le bloc « promotion » ramene AUTOMATIQUEMENT le robot au D1.

    Sans lui, plus rien ne le fait quand la fenetre se ferme.
    """

    def test_le_bloc_est_present_et_borne(self):
        p = Promotion.depuis_config(config().promotion)
        assert p.active, "bloc promotion absent ou desactive — voir CLAUDE.md"
        assert p.fin, "une fenetre sans date de fin n'expire jamais"

    def test_elle_porte_sa_propre_fin(self):
        import datetime as dt
        p = Promotion.depuis_config(config().promotion)
        fin = dt.date.fromisoformat(p.fin)
        assert p.en_cours(fin) is True
        assert p.en_cours(fin + dt.timedelta(days=1)) is False

    def test_apres_expiration_le_tarif_reel_revient(self):
        import datetime as dt
        p = Promotion.depuis_config(config().promotion)
        lendemain = dt.date.fromisoformat(p.fin) + dt.timedelta(days=1)
        assert p.frais_effectifs(FRAIS_BITVAVO, lendemain) == pytest.approx(FRAIS_BITVAVO)


class TestLeSimulateurResteDisponible:
    """Un lieu d'execution qui n'engage rien doit toujours etre la.

    « paper » avait ete retire des brokers valides : plus de dry-run, plus
    de rejeu historique, et aucun moteur constructible en test.
    """

    def test_le_simulateur_passe_la_validation(self):
        cfg = BotConfig()
        cfg.engine.broker = "paper"
        assert not [p for p in cfg.validate() if "broker" in p]

    def test_le_mode_hors_ligne_marche_avec_le_simulateur(self):
        cfg = BotConfig()
        cfg.engine.broker = "paper"
        cfg.engine.offline = True
        assert not [p for p in cfg.validate() if "hors ligne" in p]

    def test_le_mode_hors_ligne_reste_refuse_en_reel(self):
        """La garantie d'origine ne doit pas disparaitre avec la correction."""
        cfg = BotConfig()
        cfg.engine.broker = "bitvavo"
        cfg.engine.offline = True
        assert [p for p in cfg.validate() if "hors ligne" in p]


class TestLeCoutEstBienCeQuOnCroit:
    """L'arithmetique qui fonde tout le reste, verifiee ici meme."""

    def test_le_cout_incompressible_survit_a_toute_promotion(self):
        """Spread et glissement se paient au marche, pas a la plateforme."""
        assert COUT_INCOMPRESSIBLE > 0

    @pytest.mark.parametrize("unite,stop,attendu", [
        ("M15", 0.0077, 0.78), ("H1", 0.0154, 0.39),
        ("H4", 0.0308, 0.19), ("D1", 0.0600, 0.10)])
    def test_cout_par_unite_de_temps(self, unite, stop, attendu):
        cout = (2 * FRAIS_BITVAVO + COUT_INCOMPRESSIBLE) / stop
        assert cout == pytest.approx(attendu, abs=0.01)
