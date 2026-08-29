"""Le tableau de stops du forex ne decrit pas la crypto.

CE QUE CETTE ERREUR A DEJA COUTE

CLAUDE.md le raconte : le premier calcul annoncait « M15 = 78 % du risque
en frais », tire d'un tableau de stops types qui ne correspondait pas a la
crypto. Il ecartait le H4 en le calculant a 19 % au lieu de 15 %. « C'est
cette erreur qui a fait perdre une journee sur le D1. »

Le raisonnement a ete corrige dans CLAUDE.md — mais le tableau, lui, est
reste celui du forex dans le code. Ces tests verrouillent la correction
des deux cotes.
"""
from __future__ import annotations

from helpers import *  # noqa: F401,F403 - insere la racine du projet dans sys.path

from gold_bot.calibrage import (COUT_INCOMPRESSIBLE, STOP_TYPIQUE,
                                STOP_TYPIQUE_CRYPTO, calibrer,
                                stops_typiques_pour)
from gold_bot.universe import Universe

FRAIS_BITVAVO = 0.0025          # par cote, tarif normal hors promotion


def cout_en_r(unite: str, stops: dict[str, float],
              frais_par_cote: float = FRAIS_BITVAVO) -> float:
    """Part du risque mangee par un aller-retour, sur cette unite."""
    return (2 * frais_par_cote + COUT_INCOMPRESSIBLE) / stops[unite]


# --------------------------------------------------------------------------
# Le tableau lui-meme
# --------------------------------------------------------------------------
def test_les_stops_crypto_sont_les_atr_mesures_fois_le_multiplicateur():
    # ATR reellement mesures dans les journaux du 28 aout, x 1,8 :
    #   M15  0,56 %  ->  1,01 %      H4  2,24 %  ->  4,03 %
    #   D1   5,46 %  ->  9,83 %
    assert STOP_TYPIQUE_CRYPTO["M15"] == 0.0101
    assert STOP_TYPIQUE_CRYPTO["H4"] == 0.0403
    assert STOP_TYPIQUE_CRYPTO["D1"] == 0.0983


def test_la_crypto_bouge_plus_que_le_forex_sur_toutes_les_unites():
    for unite in STOP_TYPIQUE:
        assert STOP_TYPIQUE_CRYPTO[unite] > STOP_TYPIQUE[unite], unite


def test_les_stops_croissent_avec_l_unite_de_temps():
    ordre = ["M1", "M3", "M5", "M15", "M30", "H1", "H4", "D1"]
    valeurs = [STOP_TYPIQUE_CRYPTO[u] for u in ordre]
    assert valeurs == sorted(valeurs)


def test_le_bon_tableau_est_choisi_selon_ce_qu_on_trade():
    assert stops_typiques_pour("crypto") is STOP_TYPIQUE_CRYPTO
    assert stops_typiques_pour("CRYPTO") is STOP_TYPIQUE_CRYPTO
    assert stops_typiques_pour("forex") is STOP_TYPIQUE
    # Vide = tableau historique : les appels qui ne precisent rien ne
    # doivent pas changer de comportement.
    assert stops_typiques_pour("") is STOP_TYPIQUE


# --------------------------------------------------------------------------
# L'arithmetique que CLAUDE.md documente
# --------------------------------------------------------------------------
def test_le_h4_coute_bien_15_pourcent_du_risque_et_non_19():
    """L'erreur exacte qui a fait perdre une journee."""
    juste = cout_en_r("H4", STOP_TYPIQUE_CRYPTO)
    faux = cout_en_r("H4", STOP_TYPIQUE)
    assert round(juste * 100) == 15, f"H4 devrait couter 15 % du risque, pas {juste:.1%}"
    assert round(faux * 100) == 19, "le tableau du forex donnait bien 19 %"


def test_le_m15_reste_hors_de_portee_du_plafond_de_15_pourcent():
    """La conclusion tenait pour le M15 : il reste inaccessible."""
    cout = cout_en_r("M15", STOP_TYPIQUE_CRYPTO)
    assert cout > 0.15, "le M15 doit rester au-dessus du plafond de cout"
    assert round(cout * 100) == 59


def test_le_d1_est_le_moins_cher():
    assert cout_en_r("D1", STOP_TYPIQUE_CRYPTO) < cout_en_r("H4", STOP_TYPIQUE_CRYPTO)
    assert round(cout_en_r("D1", STOP_TYPIQUE_CRYPTO) * 100) == 6


# --------------------------------------------------------------------------
# Ce que ca change au calibrage
# --------------------------------------------------------------------------
def test_hors_promotion_le_m15_n_est_plus_declare_tenable_en_crypto():
    """Le coeur du bug : le tableau du forex declarait tenable une unite
    que le cout rend impraticable des que la promotion se ferme."""
    forex = calibrer(186.0, 5.0, FRAIS_BITVAVO, 0.5, 0.6,
                     plafond_cout_pct=15.0)
    crypto = calibrer(186.0, 5.0, FRAIS_BITVAVO, 0.5, 0.6,
                      plafond_cout_pct=15.0, classe_actif="crypto")
    assert "M15" not in crypto.unites, (
        "le M15 coute 59 % du risque en crypto : le plafond de 15 % l'exclut")
    # Et le H4, lui, redevient atteignable la ou le tableau du forex
    # l'ecartait a tort.
    assert "H4" in crypto.unites
    assert crypto.unites != forex.unites


def test_l_univers_en_service_est_bien_reconnu_comme_crypto():
    # Sans ca, le robot passerait la chaine vide et retomberait en silence
    # sur le tableau du forex.
    assert Universe().classe_dominante() == "crypto"


def test_un_univers_vide_ne_choisit_pas_de_classe_au_hasard():
    from gold_bot.universe import Universe as U
    assert U(instruments=[]).classe_dominante() == ""
