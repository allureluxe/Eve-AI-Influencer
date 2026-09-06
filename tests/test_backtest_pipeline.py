"""Le banc d'essai doit pouvoir produire des trades.

Un rejeu qui renvoie zero trade sur toutes les variantes ressemble a une
strategie sans avantage. C'en etait une autre : un filtre qui refusait
tout, silencieusement, avant meme que la strategie ait son mot a dire.
Ces tests separent les deux cas.
"""
from __future__ import annotations

import math
import time

import pytest

from helpers import *  # noqa: F401,F403 - insere la racine du projet dans sys.path

from gold_bot.backtest import Backtester
from gold_bot.core import Candle
from gold_bot.settings import BotConfig
from gold_bot.universe import Universe, spread_estime


class TestPlafondDeSpreadDesCryptos:
    """Un plafond ABSOLU n'a pas de sens sur un catalogue BTC -> PEPE."""

    def test_aucune_crypto_ne_porte_de_plafond_absolu(self):
        """La regression qui rendait BTCUSD intradable.

        BTCUSD portait max_spread = 30 pour un spread estime de 34 a
        68 000 (5 points de base). Resultat : 450 rejets sur 450 au rejeu,
        sur le filtre « spread », et la meme chose en argent reel — la
        crypto la plus liquide de l'univers etait ecartee en permanence.
        """
        univers = Universe()
        fautifs = [i.symbol for i in univers
                   if i.asset_class == "crypto" and math.isfinite(i.max_spread)]
        assert not fautifs, (
            f"plafond de spread absolu sur {fautifs} : le controle relatif "
            "strategy.max_spread_atr_ratio est le seul valable a toutes les "
            "echelles de prix")

    @pytest.mark.parametrize("symbole,prix", [
        ("BTCUSD", 68_000.0), ("ETHUSD", 3_000.0),
        ("SOLUSD", 150.0), ("XRPUSD", 0.50),
    ])
    def test_le_spread_estime_passe_le_plafond_de_l_instrument(self, symbole, prix):
        """Le test qui aurait attrape le defaut a l'origine."""
        inst = Universe().get(symbole)
        assert inst is not None
        assert spread_estime(inst, prix) <= inst.max_spread, (
            f"{symbole} a {prix:.0f} : le spread modelise depasse le plafond "
            "de l'instrument, il sera refuse a chaque evaluation")


class _RegistreConstant:
    """Registre de test : sert la meme serie de bougies a toutes les unites."""

    def __init__(self, bougies: list[Candle]) -> None:
        self.bougies = bougies

    def candles(self, symbol, asset_class, timeframe, limit):  # noqa: D102
        return self.bougies[-limit:]


def _serie_en_tendance(n: int = 700, depart: float = 68_000.0,
                       pente: float = 0.004, amplitude: float = 0.012,
                       graine: int = 7) -> list[Candle]:
    """Une hausse bruitee, assez volatile pour passer les planchers.

    Ni realiste ni destinee a l'etre : elle sert a verifier que la chaine
    evaluation -> dimensionnement -> ouverture fonctionne. Une strategie de
    suivi de tendance qui ne trade pas ICI ne tradera nulle part.

    Le bruit n'est pas cosmetique. Une amplitude CONSTANTE rend le
    percentile d'ATR degenere — toutes les valeurs egales, donc le rang
    tombe hors des bornes min/max — et le filtre « volatilite » refuse
    alors tout, ce qui ressemble a s'y meprendre a une strategie sans
    signal.
    """
    import random

    alea = random.Random(graine)
    out, prix, t0 = [], depart, time.time() - n * 3600
    for i in range(n):
        ouverture = prix
        # La pente varie de bougie en bougie : sans cela l'ATR est constant.
        prix *= 1.0 + pente * alea.uniform(-0.6, 2.2)
        etendue = amplitude * alea.uniform(0.35, 1.9)
        haut = max(ouverture, prix) * (1 + etendue / 2)
        bas = min(ouverture, prix) * (1 - etendue / 2)
        out.append(Candle(t0 + i * 3600, ouverture, haut, bas, prix, 1000.0))
    return out


def _serie_en_escalier(n: int = 700, depart: float = 68_000.0,
                       marche: float = 0.004) -> list[Candle]:
    """Une hausse qui ne redescend JAMAIS toucher le niveau precedent.

    Chaque bougie ouvre au-dessus de la cloture precedente et ne fait que
    monter. C'est le decrochage : un ordre limite pose au meilleur acheteur
    reste dans le carnet, le prix part sans lui, et le trade est perdu.

    Irrealiste tel quel, et c'est voulu — on isole la non-execution pour
    verifier qu'elle est bien modelisee. Sur une hausse ordinaire, des
    bougies de 1,2 % d'amplitude redescendent toujours toucher une limite
    posee 0,05 % plus bas : le vrai risque est le decrochage, pas le bruit.
    """
    out, prix, t0 = [], depart, time.time() - n * 3600
    for i in range(n):
        ouverture = prix * (1.0 + marche)          # ouvre AU-DESSUS
        fermeture = ouverture * (1.0 + marche)
        out.append(Candle(t0 + i * 3600, ouverture, fermeture,
                          ouverture, fermeture, 1000.0))
        prix = fermeture
    return out


class TestLaChaineProduitDesTrades:
    def test_la_mecanique_ouvre_des_positions(self):
        """Isole la MECANIQUE de la selectivite de la configuration.

        On desarme volontairement les seuils de decision : ce test ne dit
        rien de la qualite de la strategie, il verifie que la chaine
        evaluation -> dimensionnement -> ouverture -> cloture fonctionne.
        S'il echoue, aucun rejeu n'a de sens, quelles que soient les
        variantes essayees.
        """
        cfg = BotConfig.load("robot.bitvavo.json")
        cfg.strategy.min_score = 0.0
        cfg.strategy.min_confirmations = 1
        cfg.strategy.min_adx = 0.0
        cfg.strategy.min_headroom_atr = 0.0
        cfg.strategy.min_atr_percentile = 0.0
        cfg.strategy.max_atr_percentile = 1.0

        registre = _RegistreConstant(_serie_en_tendance())
        res = Backtester(cfg, registry=registre).run("BTCUSD", bars=700,
                                                     start_balance=186.0)
        assert res.evaluations > 0, "aucune evaluation : le rejeu n'a rien parcouru"
        assert res.trades, (
            "aucun trade malgre des seuils desarmes et une tendance franche : "
            "la chaine evaluation -> dimensionnement -> ouverture est cassee. "
            f"Motifs : {sorted(res.rejections.items(), key=lambda kv: -kv[1])[:5]}")

    def test_la_configuration_livree_reste_selective(self):
        """L'envers du test precedent, et il compte autant.

        Une configuration qui trade sur n'importe quoi n'a pas d'avantage,
        elle a du volume. Sur la meme serie, la config en service doit
        prendre MOINS de trades que la version desarmee.
        """
        serie = _serie_en_tendance()
        livree = BotConfig.load("robot.bitvavo.json")
        permissive = BotConfig.load("robot.bitvavo.json")
        permissive.strategy.min_score = 0.0
        permissive.strategy.min_confirmations = 1
        permissive.strategy.min_adx = 0.0
        permissive.strategy.min_headroom_atr = 0.0
        permissive.strategy.min_atr_percentile = 0.0
        permissive.strategy.max_atr_percentile = 1.0

        n_livree = len(Backtester(livree, registry=_RegistreConstant(serie)).run(
            "BTCUSD", bars=700, start_balance=186.0).trades)
        n_permissive = len(Backtester(permissive, registry=_RegistreConstant(serie)).run(
            "BTCUSD", bars=700, start_balance=186.0).trades)
        assert n_livree <= n_permissive, (
            f"la config livree prend {n_livree} trades contre {n_permissive} "
            "sans aucun filtre : les seuils ne filtrent plus rien")

    def test_les_motifs_de_rejet_sont_rapportes(self):
        """Sans eux, « zero trade » ne se diagnostique pas."""
        cfg = BotConfig.load("robot.bitvavo.json")
        # Une serie plate : rien ne doit passer, mais on doit savoir POURQUOI.
        plate = _serie_en_tendance(pente=0.0, amplitude=0.0004)
        res = Backtester(cfg, registry=_RegistreConstant(plate)).run(
            "BTCUSD", bars=700, start_balance=186.0)
        assert res.rejections, "un rejeu sans trade doit nommer ce qui a refuse"
        assert sum(res.rejections.values()) > 0


class TestEntreeEnOrdreLimite:
    """Moins de frais, mais des trades rates. Les deux doivent etre modelises.

    Modeliser la baisse de tarif sans modeliser les non-executions donnerait
    un resultat flatteur et faux — exactement le genre d'hypothese qui fait
    armer une strategie que personne n'a testee.
    """

    @staticmethod
    def _permissive():
        cfg = BotConfig.load("robot.bitvavo.json")
        cfg.strategy.min_score = 0.0
        cfg.strategy.min_confirmations = 1
        cfg.strategy.min_adx = 0.0
        cfg.strategy.min_headroom_atr = 0.0
        cfg.strategy.min_atr_percentile = 0.0
        cfg.strategy.max_atr_percentile = 1.0
        cfg.strategy.min_atr_price_ratio = 0.0
        return cfg

    def test_l_ordre_limite_rate_des_trades(self):
        """Sur une hausse franche, le prix ne revient pas toucher la limite."""
        serie = _serie_en_tendance(n=700, pente=0.004)
        au_marche = Backtester(self._permissive(),
                               registry=_RegistreConstant(serie)).run(
            "BTCUSD", bars=700, start_balance=186.0)
        en_limite = Backtester(self._permissive(),
                               registry=_RegistreConstant(serie),
                               entree_limite=True).run(
            "BTCUSD", bars=700, start_balance=186.0)

        assert len(en_limite.trades) <= len(au_marche.trades), (
            f"l'ordre limite prend {len(en_limite.trades)} trades contre "
            f"{len(au_marche.trades)} au marche : les non-executions ne sont "
            "pas modelisees, le resultat serait flatteur")

    def test_les_non_executions_sont_comptees(self):
        """Un trade rate doit se voir dans les motifs, pas disparaitre.

        Il faut pour cela une serie ou le prix PART SANS REVENIR : sur une
        hausse ordinaire, des bougies de 1,2 % d'amplitude redescendent
        toujours toucher une limite posee 0,05 % plus bas, et l'ordre est
        servi a tous les coups. C'est realiste — le vrai risque de
        non-execution est le decrochage, pas le bruit.
        """
        serie = _serie_en_escalier(n=700)
        res = Backtester(self._permissive(), registry=_RegistreConstant(serie),
                         entree_limite=True).run(
            "BTCUSD", bars=700, start_balance=186.0)
        assert "limite non servie" in res.rejections, (
            "aucune non-execution comptee sur une serie qui ne redescend "
            "jamais : le modele accepte tout, donc il ne modelise rien. "
            f"Motifs : {sorted(res.rejections.items(), key=lambda kv: -kv[1])[:5]}")

    def test_le_mode_marche_reste_le_defaut(self):
        """La mesure de reference porte sur des ordres AU MARCHE."""
        assert Backtester(self._permissive()).entree_limite is False

    def test_le_broker_n_arme_pas_les_limites_tout_seul(self):
        """Armer sans remesurer reviendrait a trader une strategie non testee."""
        from gold_bot.brokers.bitvavo import BitvavoConfig
        assert BitvavoConfig().entree_limite is False
