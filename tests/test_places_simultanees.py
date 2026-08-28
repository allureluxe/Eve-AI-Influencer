"""Le calcul des places simultanees ne doit pas se tromper de coupable.

L'operateur veut plus de positions : « il prend peu de positions a mon
gout, sur une journee il y a enormement d'opportunites avec 70 instruments,
donc il y a un truc qui va pas ».

Le piege qu'on rend impossible ici : desserrer `max_positions` alors que le
budget de risque plafonne exactement au meme endroit, ne rien voir changer,
et conclure que le reglage est casse alors qu'il etait simplement masque.
"""
from __future__ import annotations

from helpers import *  # noqa: F401,F403 - insere la racine du projet dans sys.path

from gold_bot.capacite import AUCUN_PLAFOND, places_simultanees
from gold_bot.settings import BotConfig


def test_le_plus_petit_des_plafonds_l_emporte():
    cap = places_simultanees(max_positions=6, max_par_groupe=1, n_groupes=10,
                             max_risque_total_pct=1.8, risque_par_trade_pct=0.5)
    # 1.8 / 0.5 = 3 : le budget de risque, pas les 6 places annoncees.
    assert cap.places == 3
    assert cap.bride_par == ["budget de risque"]


def test_deux_verrous_a_la_meme_hauteur_sont_tous_les_deux_nommes():
    cap = places_simultanees(max_positions=3, max_par_groupe=1, n_groupes=14,
                             max_risque_total_pct=1.8, risque_par_trade_pct=0.5)
    assert cap.places == 3
    assert set(cap.bride_par) == {"max_positions", "budget de risque"}
    assert cap.plusieurs_verrous


def test_un_seul_verrou_ne_declenche_pas_l_avertissement():
    cap = places_simultanees(max_positions=2, max_par_groupe=1, n_groupes=14,
                             max_risque_total_pct=6.0, risque_par_trade_pct=0.5)
    assert cap.places == 2
    assert cap.bride_par == ["max_positions"]
    assert not cap.plusieurs_verrous


def test_les_groupes_correles_peuvent_brider_seuls():
    # Peu de groupes disponibles : meme avec un plafond genereux et du
    # budget, le robot ne peut pas diversifier.
    cap = places_simultanees(max_positions=10, max_par_groupe=1, n_groupes=2,
                             max_risque_total_pct=9.0, risque_par_trade_pct=0.5)
    assert cap.places == 2
    assert cap.bride_par == ["groupes correles"]


def test_le_capital_bride_quand_le_ticket_minimum_est_trop_gros():
    cap = places_simultanees(max_positions=10, max_par_groupe=1, n_groupes=10,
                             max_risque_total_pct=9.0, risque_par_trade_pct=0.5,
                             places_par_capital=2)
    assert cap.places == 2
    assert cap.bride_par == ["capital"]


def test_le_capital_non_renseigne_n_invente_pas_de_plafond():
    # 0 = « je ne sais pas », pas « zero position possible ».
    cap = places_simultanees(3, 1, 10, 3.0, 0.5, places_par_capital=0)
    assert cap.places == 3
    assert "capital" not in cap.limites


def test_un_plafond_a_zero_ne_bloque_pas_tout():
    # Meme convention que le reste du projet : 0 ou moins = aucun plafond.
    # Sans ce test, un `max_positions: 0` cense « liberer » le robot le
    # bloquerait entierement — c'est l'inverse de l'intention.
    cap = places_simultanees(max_positions=0, max_par_groupe=1, n_groupes=10,
                             max_risque_total_pct=3.0, risque_par_trade_pct=0.5)
    assert cap.places == 6


def test_un_risque_par_trade_nul_ne_divise_pas_par_zero():
    cap = places_simultanees(3, 1, 10, 3.0, 0.0)
    assert cap.places == 3


def test_le_plafond_capital_doit_etre_demande_sans_bornage():
    """`positions_tenables` borne son resultat par le plafond qu'on lui passe.

    Lui passer `max_positions` lui fait renvoyer `max_positions`, et la
    ligne « capital » repeterait alors un autre verrou en se faisant passer
    pour une contrainte independante. C'est pour ca que `etat.py` lui passe
    AUCUN_PLAFOND et laisse la comparaison a `places_simultanees`.
    """
    from gold_bot.engine import positions_tenables
    borne, _ = positions_tenables(186.0, 5.0, 80.0, 3)
    libre, _ = positions_tenables(186.0, 5.0, 80.0, AUCUN_PLAFOND)
    assert borne == 3
    assert libre > 3, "le capital reel permet bien plus que trois tickets"


# --------------------------------------------------------------------------
def test_la_configuration_en_service_est_bridee_a_trois_par_deux_verrous():
    """Constat, pas prescription : ce test dit ce que la config FAIT.

    S'il echoue un jour, ce n'est pas une regression — c'est que le nombre
    de positions a ete change, et le test doit etre mis a jour en meme
    temps que la decision, pas avant.
    """
    r = BotConfig.load("robot.bitvavo.json").risk
    cap = places_simultanees(r.max_positions, r.max_per_correlation_group,
                             n_groupes=14,
                             max_risque_total_pct=r.max_total_risk_pct,
                             risque_par_trade_pct=r.base_risk_pct)
    assert cap.places == 3
    assert cap.plusieurs_verrous, (
        "deux verrous a la meme hauteur : en desserrer un seul ne changerait rien")


# --------------------------------------------------------------------------
# Le capital sur lequel tout ce rapport est calcule
#
# `engine.start_balance` vaut 1000 par defaut et n'est PAS renseigne dans
# robot.bitvavo.json. `etat.py` s'en servait : tout le rapport etait calcule
# sur un compte imaginaire dix fois trop gros, et annoncait des unites de
# temps « tenables » que le vrai capital ne tient pas.
# --------------------------------------------------------------------------
def test_start_balance_n_est_pas_le_capital_du_compte():
    """Le piege lui-meme, verrouille : si un jour start_balance devient la
    vraie valeur, ce test le signale au lieu de laisser le doute."""
    cfg = BotConfig.load("robot.bitvavo.json")
    assert cfg.engine.start_balance == 1000.0, (
        "valeur par defaut : ne decrit aucun compte reel")


def _etat(reference: float = 0.0, sommet: float = 0.0):
    from gold_bot.state import BotState
    return BotState(account_reference=reference, peak_equity=sommet)


def test_le_capital_vient_de_ce_que_le_robot_a_enregistre():
    from etat import capital_connu
    cfg = BotConfig.load("robot.bitvavo.json")
    valeur, provenance = capital_connu(_etat(reference=186.0), cfg)
    assert valeur == 186.0
    assert "enregistre" in provenance


def test_a_defaut_de_reference_le_dernier_sommet_sert():
    from etat import capital_connu
    cfg = BotConfig.load("robot.bitvavo.json")
    valeur, provenance = capital_connu(_etat(sommet=190.5), cfg)
    assert valeur == 190.5
    assert "sommet" in provenance


def test_sans_aucun_capital_reel_le_rapport_le_dit_franchement():
    # Retomber sur 1000 en silence est exactement ce qui a produit le bug.
    from etat import capital_connu
    cfg = BotConfig.load("robot.bitvavo.json")
    valeur, provenance = capital_connu(_etat(), cfg)
    assert valeur == 1000.0
    assert provenance.startswith("AUCUN")
