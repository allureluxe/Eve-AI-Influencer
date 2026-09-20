"""Le filtre de tendance de fond sur les cassures de canal.

Propose par l'agent d'Alluxe le 19 septembre (« trend-following
multi-time-frame EMA ») et demande a l'essai par l'operateur le
20 : « teste-moi ces methodes ».

LE CAS QU'IL PROTEGE, et il faut prouver qu'il se produit : une cassure
dans un marche qui DESCEND. Le prix depasse son plus-haut de dix jours
tout en restant sous sa moyenne longue, parce que ces dix jours
n'etaient qu'un repli dans une baisse. Le robot achete alors un piege.

Un raffinement qui « corrige » un cas doit d'abord prouver que le cas
EXISTE -- c'est ecrit noir sur blanc dans CLAUDE.md, apres un
raffinement arme pour rien en septembre.
"""
import pytest

from gold_bot.core import Candle, Tick
from gold_bot.indicators import IndicatorSet
from gold_bot.strategy import Strategy, StrategyConfig
from gold_bot.trade_manager import TradeManager, TradeManagerConfig
from gold_bot.universe import Universe


def _serie(motif):
    """Construit des bougies a partir d'une liste de prix de cloture."""
    bougies = []
    for i, prix in enumerate(motif):
        bougies.append(Candle(ts=1_600_000_000 + i * 86400,
                              open=prix, high=prix * 1.01, low=prix * 0.99,
                              close=prix, volume=1000.0))
    return bougies


def _indicateurs(bougies):
    ind = IndicatorSet(history=400)
    for c in bougies:
        ind.update(c)
    return ind


def _cotation(bougies):
    """Le prix courant, avec un ecart achat/vente negligeable : ce test
    porte sur le filtre de tendance, pas sur le cout d'execution."""
    prix = bougies[-1].close
    return Tick(bougies[-1].ts, prix * 0.9999, prix * 1.0001)


def _toutes_unites(bougies):
    """La strategie exige M15, H1 et D1 avant meme de regarder la cassure.

    La branche donchian ne lit QUE l'unite d'entree : donner les memes
    bougies aux trois ne change donc rien a ce qu'on mesure ici, et
    evite de fabriquer trois series qui n'apprendraient rien de plus.
    """
    ind = _indicateurs(bougies)
    return {"M15": ind, "H1": ind, "D1": ind}


def _strategie(periode_moyenne=0):
    cfg = StrategyConfig(
        famille="donchian", entry_tf="D1", donchian_entrees=(10,),
        donchian_ema_periode=periode_moyenne, min_score=0.0,
        min_confirmations=0, min_adx=0.0, min_headroom_atr=0.0,
        min_atr_percentile=0.0, max_atr_percentile=1.0,
        min_atr_price_ratio=0.0,
    )
    return Strategy(cfg, TradeManager(TradeManagerConfig()), macro=None)


#: Une BAISSE de fond, avec un rebond final qui casse le canal 10 jours.
#: C'est exactement le piege : la cassure est vraie, la tendance est
#: contre.
REPLI_DANS_UNE_BAISSE = (
    [100 - i * 0.8 for i in range(60)]      # 60 jours de baisse reguliere
    + [52 + i * 1.2 for i in range(12)]     # un rebond de 12 jours
)

#: Une HAUSSE de fond, un palier, puis une cassure franche. La cassure
#: est vraie ET la tendance est d'accord : le filtre ne doit PAS la
#: bloquer.
#:
#: Le palier est necessaire. Dans une hausse reguliere, la meche haute
#: de chaque bougie (close x 1,01 ici) depasse la cloture de la
#: suivante : aucune cassure n'est jamais detectee, et le test passait
#: au vert sans rien mesurer.
CASSURE_EN_HAUSSE = (
    [50 + i * 0.9 for i in range(58)]    # 58 jours de hausse
    + [102.0] * 12                        # un palier de 12 jours
    + [108.0]                             # la cassure
)


class TestLeCasQueLeFiltreProtegeEXISTE:
    """Sans cette preuve, le filtre corrigerait un probleme imaginaire."""

    def test_une_cassure_arrive_bien_dans_un_marche_qui_baisse(self):
        bougies = _serie(REPLI_DANS_UNE_BAISSE)
        prix = bougies[-1].close
        plus_haut_10j = max(c.high for c in bougies[-11:-1])
        moyenne_50 = sum(c.close for c in bougies[-50:]) / 50
        assert prix > plus_haut_10j, "pas de cassure : le test ne mesure rien"
        assert prix < moyenne_50, (
            "le prix n'est pas sous sa moyenne : ce n'est pas le piege visé")


class TestLeFiltreBloqueLaCassurePiege:
    def test_desarme_la_cassure_passe(self):
        bougies = _serie(REPLI_DANS_UNE_BAISSE)
        s = _strategie(periode_moyenne=0)
        ev = s.evaluate(Universe().get("BTCUSD"), _toutes_unites(bougies),
                        _cotation(bougies), news=None, charts=None,
                        now=bougies[-1].ts)
        noms = {g.name for g in ev.gates}
        assert "tendance_de_fond" not in noms, (
            "le filtre s'applique alors qu'il est desarme")

    def test_arme_la_cassure_est_refusee(self):
        bougies = _serie(REPLI_DANS_UNE_BAISSE)
        s = _strategie(periode_moyenne=50)
        ev = s.evaluate(Universe().get("BTCUSD"), _toutes_unites(bougies),
                        _cotation(bougies), news=None, charts=None,
                        now=bougies[-1].ts)
        porte = next((g for g in ev.gates if g.name == "tendance_de_fond"), None)
        assert porte is not None, "le filtre ne s'est pas execute"
        assert porte.passed is False, f"la cassure piege est passee : {porte.detail}"
        assert "SOUS la moyenne" in porte.detail


class TestIlNeBLOQUEPASLesBONNESCassures:
    """Un filtre qui refuse tout ne filtre rien : il eteint la strategie."""

    def test_une_cassure_en_hausse_passe_le_filtre(self):
        bougies = _serie(CASSURE_EN_HAUSSE)
        s = _strategie(periode_moyenne=50)
        ev = s.evaluate(Universe().get("BTCUSD"), _toutes_unites(bougies),
                        _cotation(bougies), news=None, charts=None,
                        now=bougies[-1].ts)
        porte = next((g for g in ev.gates if g.name == "tendance_de_fond"), None)
        assert porte is not None, "le filtre ne s'est pas execute"
        assert porte.passed is True, f"une bonne cassure a ete bloquee : {porte.detail}"


class TestIlEstDESARMEPartout:
    """Tant que la mesure n'a pas tranche."""

    @pytest.mark.parametrize("fichier", ["robot.bitvavo.json", "robot.demo.json",
                                         "robot.demo2.json", "robot.demo3.json"])
    def test_aucune_configuration_ne_l_arme(self, fichier):
        import os
        from gold_bot.settings import BotConfig
        racine = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        cfg = BotConfig.load(os.path.join(racine, fichier))
        assert cfg.strategy.donchian_ema_periode == 0, (
            f"{fichier} arme le filtre de tendance sans mesure")
