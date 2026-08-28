"""L'analyse des sorties doit dire la verite sur ce qui gagne.

POURQUOI CE TEST EXISTE

L'operateur a lu son journal, vu « fermeture en stop » partout, et conclu
que le robot ne gagnait jamais. La conclusion etait fausse pour une raison
de vocabulaire : une fois le stop remonte au break-even ou porte par le
trailing, le toucher encaisse un GAIN. Le journal disait « stop », le
compte disait « benefice », et personne ne pouvait le savoir.

Ces tests verrouillent la distinction. Si un jour « stop suiveur » et
« stop initial » se remelangent, ils echouent — et c'est le code qu'il
faudra corriger, pas eux.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from comparer import CATEGORIES, categorie_de_sortie, config_pour, resumer
from gold_bot.core import ClosedTrade, Side
from gold_bot.settings import BotConfig

HEURE = 3600.0


def trade(reason: str, r: float, profit: float = 0.0, heures: float = 4.0,
          favorable: float = 0.0, partial: bool = False) -> ClosedTrade:
    return ClosedTrade(
        position_id="x", symbol="BTCUSD", side=Side.BUY, volume=1.0,
        entry_price=100.0, exit_price=100.0 + r,
        opened_at=0.0, closed_at=heures * HEURE,
        profit=profit if profit else r, r_multiple=r, reason=reason,
        max_favorable_r=favorable or max(r, 0.0), partial=partial,
    )


# --------------------------------------------------------------------------
# La distinction qui a fait croire que rien ne gagnait
# --------------------------------------------------------------------------
def test_un_stop_touche_en_gain_n_est_pas_une_perte():
    assert categorie_de_sortie("stop-loss touche", 1.4) == "stop suiveur"


def test_un_stop_touche_en_perte_reste_une_perte():
    assert categorie_de_sortie("stop-loss touche", -1.0) == "stop initial"


def test_le_stop_a_zero_compte_comme_perte():
    # Break-even exact : rien gagne, et les frais sont deja payes.
    assert categorie_de_sortie("stop-loss touche", 0.0) == "stop initial"


def test_chaque_motif_du_robot_a_une_categorie_connue():
    # Les motifs sont ceux reellement emis par le broker papier et le
    # gestionnaire de trade. Un motif inconnu tomberait dans « autre » et
    # disparaitrait des colonnes du rapport sans qu'on le remarque.
    motifs = [
        "objectif atteint",
        "stop-loss touche",
        "stop temporel : 2880 min sans progression (+0.05R)",
        "retournement confirme a +0.90R (dynamique -0.50 : ...)",
        "fin de periode de test",
    ]
    for m in motifs:
        cat = categorie_de_sortie(m, 0.5)
        assert cat in CATEGORIES, m
        assert cat != "autre", f"motif non classe : {m}"


# --------------------------------------------------------------------------
# Le resume
# --------------------------------------------------------------------------
def test_le_resume_separe_les_deux_sortes_de_stop():
    trades = [
        trade("stop-loss touche", 1.5),    # gain verrouille
        trade("stop-loss touche", 1.2),    # gain verrouille
        trade("stop-loss touche", -1.0),   # vraie perte
        trade("objectif atteint", 2.0),
    ]
    r = resumer(trades, partielles=0, profit=37.0, dd=5.0)
    assert r["sorties"]["stop suiveur"] == 2
    assert r["sorties"]["stop initial"] == 1
    assert r["sorties"]["objectif"] == 1
    assert r["trades"] == 4
    assert r["gagnants"] == 3


def test_les_prises_partielles_ne_comptent_pas_comme_des_trades():
    # Un trade coupe en deux ne fait pas deux trades : le compter ainsi
    # diluerait l'esperance par un demi-trade qui n'existe pas.
    trades = [trade("objectif atteint", 2.0)]
    r = resumer(trades, partielles=3, profit=10.0, dd=1.0)
    assert r["trades"] == 1
    assert r["partielles"] == 3


def test_la_duree_est_mediane_pas_moyenne():
    # Un trade laisse ouvert jusqu'a la fin de la periode de test peut
    # durer des semaines et deplacerait une moyenne a lui seul.
    trades = [trade("objectif atteint", 1.0, heures=2.0),
              trade("objectif atteint", 1.0, heures=4.0),
              trade("fin de periode de test", 0.1, heures=900.0)]
    r = resumer(trades, partielles=0, profit=1.0, dd=0.0)
    assert r["duree_mediane"] == 4.0


def test_le_benefice_rendu_est_l_ecart_entre_le_sommet_et_la_sortie():
    # Le trade est monte a 2 R et s'est ferme a 0,5 R : 1,5 R rendus au
    # marche. C'est ce chiffre qui dit si le probleme est l'entree ou la
    # protection.
    trades = [trade("stop-loss touche", 0.5, favorable=2.0)]
    r = resumer(trades, partielles=0, profit=1.0, dd=0.0)
    assert r["r_favorable"] - r["esperance"] == 1.5


def test_aucun_trade_ne_fait_pas_planter_le_resume():
    r = resumer([], partielles=0, profit=0.0, dd=0.0)
    assert r["trades"] == 0


# --------------------------------------------------------------------------
# Les variantes doivent changer ce qu'elles annoncent, et rien d'autre
# --------------------------------------------------------------------------
def _base() -> BotConfig:
    return BotConfig.load("robot.bitvavo.json")


def test_une_variante_ne_touche_qu_a_ce_qu_elle_nomme():
    base = _base()
    cfg = config_pour(base, {"tp_r_multiple": 1.5})
    assert cfg.trade.tp_r_multiple == 1.5
    assert cfg.trade.atr_stop_mult == base.trade.atr_stop_mult
    assert cfg.strategy.min_score == base.strategy.min_score


def test_le_plafond_de_cout_est_pose_dans_les_trois_sections():
    # Le desaccorder ferait filtrer a un endroit ce qu'un autre laisse
    # passer : le robot entrerait sur des trades que le dimensionnement
    # refuse ensuite, et le rejeu mesurerait une strategie fantome.
    cfg = config_pour(_base(), {"plafond_cout": 20.0})
    assert cfg.risk.max_cost_ratio_pct == 20.0
    assert cfg.strategy.max_cost_ratio_pct == 20.0
    assert cfg.trade.max_cost_ratio_pct == 20.0


def test_le_stop_temporel_suit_l_unite_de_temps():
    # 2880 min en H4 = 12 bougies. En H1, 12 bougies valent 720 min.
    base = _base()
    assert base.strategy.entry_tf == "H4"
    assert base.trade.time_stop_minutes == 2880.0
    cfg = config_pour(base, {"entry_tf": "H1"})
    assert cfg.trade.time_stop_minutes == 720.0


def test_le_stop_temporel_en_bougies_l_emporte_sur_la_transposition():
    cfg = config_pour(_base(), {"stop_temporel_bougies": 6})
    assert cfg.trade.time_stop_minutes == 6 * 240.0


# --------------------------------------------------------------------------
# Le rapport lui-meme
#
# Un tableau qui plante sur une variante sans trade, ou sur une division
# par zero, fait perdre l'execution entiere apres vingt minutes de rejeu.
# Ces cas sont donc verifies a vide, sans reseau.
# --------------------------------------------------------------------------
def _resultat(nom: str, n: int, esperance: float, duree: float = 8.0) -> dict:
    trades = [trade("objectif atteint", esperance, heures=duree)
              for _ in range(n)]
    r = resumer(trades, partielles=0, profit=esperance * n, dd=3.0)
    r["nom"] = nom
    return r


def test_le_rapport_survit_a_une_variante_sans_aucun_trade(capsys):
    from comparer import rapport
    rapport([_resultat("qui trade", 40, 0.3),
             {"nom": "qui ne trade pas", "trades": 0, "profit": 0.0,
              "partielles": 0, "drawdown": 0.0, "echecs": []}])
    sortie = capsys.readouterr().out
    assert "aucun trade" in sortie
    assert "CLASSEMENT" in sortie


def test_le_rapport_signale_un_echantillon_trop_petit(capsys):
    from comparer import rapport
    rapport([_resultat("trois trades", 3, 0.9)])
    sortie = capsys.readouterr().out
    assert "(trop peu)" in sortie
    assert "Aucune variante n'atteint 30 trades" in sortie


def test_le_rapport_dit_qu_il_ne_mesure_pas_le_nombre_de_positions(capsys):
    # Le rejeu ne tient qu'une position a la fois. Le rapport doit le dire
    # de lui-meme, sinon on lira ses chiffres comme ceux d'un portefeuille.
    from comparer import rapport
    rapport([_resultat("une variante", 40, 0.3)])
    sortie = capsys.readouterr().out
    assert "max_positions" in sortie


def test_le_rapport_designe_la_plus_rapide_qui_reste_gagnante(capsys):
    from comparer import rapport
    rapport([_resultat("lente mais forte", 40, 0.50, duree=60.0),
             _resultat("rapide et gagnante", 40, 0.20, duree=6.0),
             _resultat("rapide et perdante", 40, -0.40, duree=2.0)])
    sortie = capsys.readouterr().out
    assert "La plus rapide qui reste gagnante" in sortie
    assert "rapide et gagnante" in sortie
    # La perdante est plus rapide encore : elle ne doit pas etre proposee.
    ligne = [l for l in sortie.splitlines()
             if "plus rapide qui reste gagnante" in l][0]
    assert "perdante" not in ligne


def test_le_rapport_annonce_franchement_qu_aucune_variante_ne_gagne(capsys):
    from comparer import rapport
    rapport([_resultat("toutes perdantes", 40, -0.2)])
    sortie = capsys.readouterr().out
    assert "AUCUNE VARIANTE N'EST GAGNANTE" in sortie
