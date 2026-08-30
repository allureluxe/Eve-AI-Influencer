"""Le R annonce n'est pas le R encaisse, et l'ecart decide du RISQUE.

`ClosedTrade.r_multiple` se calcule sur les prix seuls
(`Position.r_multiple`) : il ignore la commission. `profit`, lui, est net.
L'ecart vaut exactement le rapport frais/risque — 47 % au M30, soit pres
d'un demi-R par trade.

Mesure du 30 aout, en argent reel : 7 trades, esperance annoncee
+0,446 R, profit encaisse +0,31 EUR. Le meme journal donne +0,186 R nets.

Ce n'est pas un detail d'affichage. `croissance.palier_courant` promeut
au risque superieur des que l'esperance depasse +0,05 R : sur le brut,
une strategie qui PERD peut declencher la promotion et faire monter la
mise. C'est precisement l'erreur que le module existe pour empecher.
"""
from __future__ import annotations

import time

from helpers import *  # noqa: F401,F403 - insere la racine du projet dans sys.path

from gold_bot.core import ClosedTrade, Side
from gold_bot.croissance import diagnostiquer
from gold_bot.state import TradeJournal


def _trade(r, profit, entree=100.0, sortie=None, volume=1.0, pid="p"):
    """Un trade dont le R brut et le profit net sont fixes separement."""
    if sortie is None:
        sortie = entree + r          # 1 R = 1 unite de prix pour volume 1
    return ClosedTrade(position_id=pid, symbol="SOLUSD", side=Side.BUY,
                       volume=volume, entry_price=entree, exit_price=sortie,
                       opened_at=time.time() - 60, closed_at=time.time(),
                       profit=profit, r_multiple=r, reason="test")


class TestLeRNetSeDeduitDuJournal:
    """Sans connaitre le stop : le brut donne la valeur de 1 R en devise."""

    def test_sans_frais_le_net_egale_le_brut(self):
        # +2 R brut, volume 1, prix 100 -> 102 : gain brut 2.0, profit 2.0
        assert abs(TradeJournal.r_net(_trade(2.0, 2.0)) - 2.0) < 1e-9

    def test_les_frais_reduisent_le_r(self):
        """Gain brut 2,0 mais seulement 1,5 encaisse : 0,5 R de frais."""
        assert abs(TradeJournal.r_net(_trade(2.0, 1.5)) - 1.5) < 1e-9

    def test_un_gain_brut_peut_devenir_une_perte_nette(self):
        """Le trade de 16h56 : +0,27 R annonces, -0,02 EUR encaisses."""
        net = TradeJournal.r_net(_trade(0.27, -0.02, volume=1.0))
        assert net is not None and net < 0, net

    def test_le_volume_est_pris_en_compte(self):
        """Le piege : oublier le volume rend le risque faux d'un facteur N."""
        # +2 R, volume 10, prix 100 -> 102 : brut 20.0, profit 15.0
        t = ClosedTrade(position_id="p", symbol="SOLUSD", side=Side.BUY,
                        volume=10.0, entry_price=100.0, exit_price=102.0,
                        opened_at=0.0, closed_at=1.0, profit=15.0,
                        r_multiple=2.0, reason="test")
        assert abs(TradeJournal.r_net(t) - 1.5) < 1e-9

    def test_une_vente_est_traitee_dans_le_bon_sens(self):
        t = ClosedTrade(position_id="p", symbol="SOLUSD", side=Side.SELL,
                        volume=1.0, entry_price=100.0, exit_price=98.0,
                        opened_at=0.0, closed_at=1.0, profit=1.5,
                        r_multiple=2.0, reason="test")
        assert abs(TradeJournal.r_net(t) - 1.5) < 1e-9

    def test_un_trade_a_zero_R_ne_casse_rien(self):
        assert TradeJournal.r_net(_trade(0.0, -0.05, sortie=100.0)) is None


class TestLaPromotionSeDecideSurLeNet:
    """La raison d'etre de tout ce fichier."""

    def test_un_avantage_brut_qui_perd_en_net_ne_promeut_pas(self):
        """+0,20 R annonces, -0,25 R encaisses : le risque ne doit PAS monter.

        Sans cette regle, le robot augmenterait la mise sur une strategie
        perdante — en composant plus vite vers zero.
        """
        stats = {"trades": 60, "esperance_R": 0.20, "esperance_R_nette": -0.25,
                 "taux_reussite_pct": 55.0}
        diag = diagnostiquer(capital=186.0, cible=3000.0, stats=stats,
                             trades_par_jour=6.0)
        assert diag.palier.nom == "preuve", (
            f"promu a « {diag.palier.nom} » sur une esperance nette negative")
        assert diag.palier.risque_pct == 0.60

    def test_un_avantage_net_reel_promeut(self):
        """L'envers : un outil qui ne promeut jamais bloque la croissance."""
        stats = {"trades": 60, "esperance_R": 0.45, "esperance_R_nette": 0.20,
                 "taux_reussite_pct": 60.0}
        diag = diagnostiquer(capital=186.0, cible=3000.0, stats=stats,
                             trades_par_jour=6.0)
        assert diag.palier.nom == "croissance"

    def test_un_journal_sans_net_retombe_sur_le_brut(self):
        """Compatibilite : un historique ancien ne doit pas figer le robot."""
        stats = {"trades": 60, "esperance_R": 0.45, "taux_reussite_pct": 60.0}
        diag = diagnostiquer(capital=186.0, cible=3000.0, stats=stats,
                             trades_par_jour=6.0)
        assert diag.palier.nom == "croissance"


class TestLeJournalExposeLesDeux:
    def test_stats_rend_les_deux_esperances(self, tmp_path):
        j = TradeJournal(path=str(tmp_path / "t.jsonl"))
        j.trades = [_trade(2.0, 1.5, pid="a"), _trade(-1.0, -1.2, sortie=99.0, pid="b")]
        st = j.stats()
        assert st["esperance_R"] == 0.5
        # nets : +1,5 et -1,2  ->  moyenne +0,15
        assert abs(st["esperance_R_nette"] - 0.15) < 1e-9
        assert st["esperance_R_nette"] < st["esperance_R"], (
            "les frais doivent toujours reduire le R, jamais l'augmenter")
