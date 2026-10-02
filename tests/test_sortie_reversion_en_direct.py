"""La sortie de la famille « reversion » existe en direct, pas seulement au rejeu.

2 oct. 2026, en armant la demo 3 : le moteur reel n'avait aucune sortie
« retour a la moyenne » -- une position achetee au creux n'aurait ete
vendue qu'au stop ou au stop temporel.
"""
import inspect

from helpers import *  # noqa: F401,F403 - insere le chemin du projet

from gold_bot.strategy import StrategyConfig, retour_a_la_moyenne


def _cfg():
    c = StrategyConfig()
    c.reversion_ma_periode, c.reversion_sortie_atr = 5, 0.5
    return c


def test_sous_la_bande_on_garde():
    # SMA 10, prix 8, ATR 1 : ecart 2 ATR > 0,5 -> on reste
    assert not retour_a_la_moyenne(_cfg(), [10] * 5, 8.0, 1.0)


def test_revenu_dans_la_bande_on_sort():
    assert retour_a_la_moyenne(_cfg(), [10] * 5, 9.6, 1.0)


def test_sans_assez_d_historique_on_ne_decide_rien():
    assert not retour_a_la_moyenne(_cfg(), [10] * 3, 12.0, 1.0)


def test_le_moteur_et_le_rejeu_partagent_la_regle():
    from gold_bot import backtest, engine
    assert "retour_a_la_moyenne(" in inspect.getsource(engine.TradingEngine)
    assert "retour_a_la_moyenne(" in inspect.getsource(backtest)
