"""`donchian_sens` : acheter la cassure du plus-HAUT (armé) ou du plus-BAS.

Question de l'opérateur, 9 oct. : « au lieu d'acheter le plus haut de
10 jours, pourquoi ne pas acheter le plus bas ? ». Le réglage existe pour
le banc d'essai ; le défaut reste « haut », et aucune configuration armée
ne doit basculer sans mesure.
"""
import json
from pathlib import Path

import pytest

from gold_bot.core import Candle, Tick
from gold_bot.indicators import IndicatorSet
from gold_bot.strategy import Strategy, StrategyConfig
from gold_bot.trade_manager import TradeManager, TradeManagerConfig
from gold_bot.universe import Universe

RACINE = Path(__file__).resolve().parents[1]


def _serie(motif):
    return [Candle(ts=1_600_000_000 + i * 86400, open=p, high=p * 1.01,
                   low=p * 0.99, close=p, volume=1000.0)
            for i, p in enumerate(motif)]


def _evaluer(motif, sens):
    bougies = _serie(motif)
    ind = IndicatorSet(history=400)
    for c in bougies:
        ind.update(c)
    cfg = StrategyConfig(
        famille="donchian", entry_tf="D1", donchian_entrees=(10,),
        donchian_sens=sens, min_score=0.0, min_confirmations=0, min_adx=0.0,
        min_headroom_atr=0.0, min_atr_percentile=0.0, max_atr_percentile=1.0,
        min_atr_price_ratio=0.0,
    )
    s = Strategy(cfg, TradeManager(TradeManagerConfig()), macro=None)
    prix = bougies[-1].close
    ev = s.evaluate(Universe().get("BTCUSD"), {"M15": ind, "H1": ind, "D1": ind},
                    Tick(bougies[-1].ts, prix * 0.9999, prix * 1.0001),
                    news=None, charts=None, now=bougies[-1].ts)
    return next(g for g in ev.gates if g.name == "donchian")


#: un palier puis une chute franche sous le plus-bas de 10 jours
CHUTE = [100.0] * 60 + [100.0] * 12 + [92.0]
#: un palier puis une cassure franche au-dessus du plus-haut
HAUSSE = [100.0] * 60 + [100.0] * 12 + [108.0]


def test_le_defaut_reste_la_cassure_du_plus_haut():
    assert StrategyConfig().donchian_sens == "haut"


@pytest.mark.parametrize("fichier", ["robot.bitvavo.json", "robot.demo.json"])
def test_aucune_configuration_armee_n_achete_le_plus_bas(fichier):
    cfg = json.loads((RACINE / fichier).read_text())
    assert cfg["strategy"].get("donchian_sens", "haut") == "haut"


def test_sens_bas_achete_sous_le_plus_bas():
    assert _evaluer(CHUTE, "bas").passed is True
    assert _evaluer(CHUTE, "haut").passed is False


def test_sens_bas_ignore_la_cassure_du_plus_haut():
    assert _evaluer(HAUSSE, "haut").passed is True
    assert _evaluer(HAUSSE, "bas").passed is False
