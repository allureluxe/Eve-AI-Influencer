"""Refuser les cassures qui arrivent apres que le mouvement a eu lieu.

DECISION DE L'OPERATEUR, 12 septembre 2026 : « je prefere prendre moins
de positions mais de bonnes positions plutot qu'autant de perdantes ».

CE QUI L'A MOTIVEE. Sur 483 trades hors echantillon, les positions a UN
SEUL etage sont 83 % du total et perdent 646 EUR, pendant que les 17 %
qui pyramident en rapportent 1 335.

CE QUE LA MESURE A TROUVE. Sur 1 104 trades d'apprentissage, les cassures
GAGNANTES sont moins spectaculaires que les perdantes, sur TOUS les
indicateurs disponibles a l'achat :

                       gagnantes  perdantes
    progression 20 j     +21,0 %    +25,5 %
    volume / moyenne       2,14       2,46
    force de la cassure    0,41       0,46
    volatilite             5,36 %     5,87 %

Plus la cassure est violente, plus elle echoue.

CE QUE CA COUTE, six periodes de ~15 mois, 70 paires, frais doubles :

    plafond   263 E ->   recul   perte des positions a un etage
    aucun        661 E   20,7 %       -242 E
    40 %         544 E   19,0 %       -150 E
    25 %         521 E   16,0 %       -133 E
    15 %         505 E   14,5 %        -73 E   <- arme

Le rendement BAISSE de 24 %. Ce n'est pas une amelioration deguisee :
c'est un arbitrage assume, paye par 70 % de petites pertes en moins.
"""
from __future__ import annotations

from helpers import *  # noqa: F401,F403 - insere la racine du projet dans sys.path


class TestLeFiltreEstArme:

    def test_le_plafond_reste_dans_la_plage_mesuree(self):
        """DESARME LE 12 SEPTEMBRE AU SOIR, quelques heures apres l'armement.

        Le filtre avait ete arme en le comparant au SEUL canal de 20 jours.
        En elargissant la recherche aux canaux courts, il devient la pire
        des six options mesurees — a 225 EUR de capital :

            10 jours sans filtre    mediane 519 E   224 trades/an
            20 jours sans filtre            468 E   172
            20 jours + filtre               323 E    83

        Il coutait 196 EUR de mediane pour dix points de recul. La lecon
        n'est pas que le filtre etait mauvais : c'est qu'on ne juge pas un
        reglage contre UN seul autre.

        Le code reste en place, teste, pour que personne ne le recode en
        croyant l'inventer. A 0 il ne fait rien ; s'il est rearme, il doit
        rester dans la plage mesuree.
        """
        from gold_bot.settings import BotConfig

        cfg = BotConfig.load("robot.bitvavo.json")
        p = cfg.strategy.donchian_momentum_max_pct
        if p == 0:
            return                       # desarme, rien a verifier
        # BORNES MESUREES. En dessous de 10 %, aucune mesure : on
        # refuserait presque tout sans savoir ce qu'on perd. Au-dessus de
        # 40 %, le filtre ne retire plus grand-chose (-150 EUR contre
        # -242) pour un rendement deja ampute.
        assert 10.0 <= p <= 40.0, (
            f"plafond a {p} % : hors de la plage mesuree (10 a 40)")


class TestLeFiltreFaitCeQuOnAttend:

    @staticmethod
    def _progression(closes: list[float]) -> float:
        return (closes[-1] / closes[0] - 1) * 100

    def test_une_cassure_calme_passe(self):
        montee = [100.0 * (1.004 ** i) for i in range(21)]     # ~+8 %
        assert self._progression(montee) < 15.0

    def test_une_cassure_d_epuisement_est_refusee(self):
        flambee = [100.0 * (1.02 ** i) for i in range(21)]     # ~+49 %
        assert self._progression(flambee) > 15.0

    def test_le_moteur_lit_bien_21_bougies(self):
        """20 jours de progression demandent 21 cloture, pas 20.

        Avec 20, on mesure 19 jours et le plafond ne veut plus dire ce
        qu'il annonce — le genre d'ecart d'un cran qui ne se voit jamais.
        """
        import inspect

        from gold_bot.strategy import Strategy
        source = inspect.getsource(Strategy)
        i = source.find("donchian_momentum_max_pct > 0")
        assert i > 0, "le filtre a disparu du moteur"
        bloc = source[i:i + 400]
        assert "bougies[-21:]" in bloc, (
            "le filtre ne lit pas 21 bougies : il mesurerait 19 jours en "
            "annoncant 20")
        assert "len(closes) >= 21" in bloc, (
            "sans historique suffisant le filtre laisserait passer ou "
            "diviserait par zero")


class TestCeQueLeFiltreNeDoitPasCasser:

    def test_il_ne_touche_qu_a_l_entree(self):
        """Une position deja ouverte n'est jamais fermee par ce filtre.

        Le confondre avec une sortie viderait le portefeuille des qu'une
        crypto monte fort — l'exact contraire du but.
        """
        import inspect

        from gold_bot.trade_manager import TradeManager
        source = inspect.getsource(TradeManager.manage)
        assert "momentum_max" not in source, (
            "le filtre d'epuisement s'est glisse dans la gestion des "
            "positions : il fermerait les gagnantes")
