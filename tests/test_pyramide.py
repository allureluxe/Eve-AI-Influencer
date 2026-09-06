"""Renforcer une montee : ouvrir un 2e, puis un 3e etage sur le meme actif.

Demande de l'operateur, mot pour mot : « grosse montee, plus
d'investissement — si le bot voit que ca continue de monter il ouvre une
2e, si ca continue encore une 3e, et elles se fermeront toutes au stop
suiveur en benefice ».

Trois verrous l'interdisaient, et il fallait les lever tous les trois :

  1. `check_exposure` refusait toute seconde position sur un symbole ;
  2. le scan retirait les symboles detenus AVANT evaluation (`exclude`) ;
  3. le rejeu ne tenait qu'une position a la fois — donc meme arme, le
     banc d'essai aurait rendu un resultat identique au temoin et on en
     aurait conclu que le renforcement ne sert a rien.

Le troisieme est le plus vicieux : il ne casse rien, il ment.
"""
from __future__ import annotations

import time

from helpers import *  # noqa: F401,F403 - insere la racine du projet dans sys.path

from gold_bot.core import Position, Side
from gold_bot.risk import RiskConfig, RiskManager
from gold_bot.settings import BotConfig
from gold_bot.universe import Universe


def _position(symbole="SOLUSD", entree=100.0, stop=98.0, pid="p1") -> Position:
    return Position(id=pid, symbol=symbole, side=Side.BUY, volume=1.0,
                    entry_price=entree, stop_loss=stop, take_profit=104.0,
                    opened_at=time.time(), initial_risk=2.0)


def _gestionnaire(**reglages) -> RiskManager:
    cfg = RiskConfig(**reglages)
    rm = RiskManager(cfg)
    rm.sync_account(1000.0, 1000.0, "EUR")
    return rm


class TestLaPyramideResteFermeeParDefaut:
    """Le renforcement ne s'arme pas tout seul : le rejeu tranche avant.

    Il a tranche le 6 septembre 2026, et POUR une fois en faveur du
    renforcement — c'est le seul reglage teste cette session-la qui passe
    le walk-forward. Le defaut du CODE reste desarme ; c'est la
    configuration livree qui l'arme, sur mesure et pas sur principe.
    """

    def test_le_reglage_livre_est_arme_a_trois_unites(self):
        """3 unites, pas 4 ni l'illimite : c'est ce que la mesure designe.

        Hors echantillon, frais doubles, 70 paires, 2,2 ans :

            sans pyramidage   -10,9 %   Sharpe -0,17   recul 26,9 %
            2 unites           -0,3 %   Sharpe +0,14   recul 30,8 %
            3 unites          +35,8 %   Sharpe +0,53   recul 35,4 %   <- arme
            4 unites          +23,9 %   Sharpe +0,42   recul 41,3 %
            6 unites          -40,8 %   Sharpe +0,05   recul 76,6 %
            ILLIMITE          -84,4 %   Sharpe -0,57   recul 95,3 %

        Le manuel Turtle dit 4 unites. Sur CES marches et CES frais, la
        mesure dit 3. On suit la mesure. Et l'illimite — demande a un
        moment — est la pire des six : le monter n'est pas « debrider »,
        c'est reproduire un resultat mesure a -84 %.
        """
        assert BotConfig.load("robot.bitvavo.json").risk.pyramide_max == 2

    def test_le_relevement_turtle_accompagne_le_desserrage(self):
        """`pyramide_locked_r_min` desserre : son remplacant doit etre arme.

        Les deux protegent la meme chose par deux chemins opposes. Le
        notre attend que l'etage precedent ne puisse plus perdre AVANT
        d'ajouter ; la Turtle ajoute tous les 0,5 N mais remonte le stop
        de TOUTE la pyramide sous la derniere unite. Desserrer le premier
        sans armer le second laisse trois fois le risque sur une crypto
        sans filet.
        """
        cfg = BotConfig.load("robot.bitvavo.json")
        if cfg.risk.pyramide_locked_r_min < 0.05:
            assert cfg.trade.pyramide_relevement_turtle, (
                "pyramide_locked_r_min est desserre sans que le relevement "
                "Turtle soit arme : le pyramidage n'a plus aucun filet")

    def test_le_defaut_du_code_est_desarme(self):
        assert RiskConfig().pyramide_max == 0

    def test_desarme_une_seconde_position_est_refusee(self):
        rm = _gestionnaire()
        inst = Universe().get("SOLUSD")
        ok, why = rm.check_exposure(inst, Side.BUY, [_position()], Universe().get)
        assert not ok
        assert "deja ouverte" in why


class TestLaPyramideNeSOuvreQueSurUnGainAcquis:
    """La regle qui rend l'empilement tenable, et la seule qui compte.

    Un etage ne s'ajoute que si les precedents ne peuvent PLUS perdre —
    stop au-dessus de l'entree. Sans elle, trois entrees sur la meme
    crypto triplent le risque, et un retournement brutal — ce qui arrive
    precisement apres une grosse montee — les prend toutes les trois.
    """

    def test_un_etage_dont_le_stop_est_sous_l_entree_bloque_tout(self):
        rm = _gestionnaire(pyramide_max=2)
        inst = Universe().get("SOLUSD")
        # Stop a 98 pour une entree a 100 : la position peut encore perdre.
        ok, why = rm.check_exposure(inst, Side.BUY, [_position(stop=98.0)],
                                    Universe().get)
        assert not ok, "renforcement accepte sur une position qui peut encore perdre"
        assert "verrouille" in why

    def test_un_etage_au_dela_du_seuil_ouvre_la_porte(self):
        rm = _gestionnaire(pyramide_max=2)
        inst = Universe().get("SOLUSD")
        # Stop a 100.5 pour une entree a 100 : +0.25R deja verrouille.
        ok, why = rm.check_exposure(inst, Side.BUY, [_position(stop=100.5)],
                                    Universe().get)
        assert ok, why

    def test_le_nombre_d_etages_est_borne(self):
        rm = _gestionnaire(pyramide_max=1)
        inst = Universe().get("SOLUSD")
        etages = [_position(stop=100.5, pid="p1"), _position(stop=100.5, pid="p2")]
        ok, why = rm.check_exposure(inst, Side.BUY, etages, Universe().get)
        assert not ok
        assert "maximum 1" in why

    def test_un_etage_a_contre_sens_est_refuse(self):
        """Ce serait une couverture : deux positions qui s'annulent en
        payant deux fois les frais."""
        rm = _gestionnaire(pyramide_max=2)
        inst = Universe().get("SOLUSD")
        ok, why = rm.check_exposure(inst, Side.SELL, [_position(stop=100.5)],
                                    Universe().get)
        assert not ok
        assert "sens oppose" in why


class TestChaqueEtageRisqueMoinsQueLePrecedent:
    """La concentration, elle, n'est pas bornee par la regle du stop.

    A 96 EUR de capital, deux etages pleins mettent tout le compte sur une
    seule crypto. La decroissance geometrique garde le sommet raisonnable.
    """

    def test_le_second_etage_risque_moins(self):
        rm = _gestionnaire(pyramide_max=2, pyramide_fraction_risque=0.6,
                           max_cost_ratio_pct=100.0)
        inst = Universe().get("SOLUSD")
        seul = rm.size_position(inst, Side.BUY, 100.0, 98.0, 104.0,
                                [], Universe().get)
        renfort = rm.size_position(inst, Side.BUY, 100.0, 98.0, 104.0,
                                   [_position(stop=100.5)], Universe().get)
        assert seul.allowed and renfort.allowed, (seul.reason, renfort.reason)
        assert renfort.risk_pct < seul.risk_pct, (
            f"etage 2 risque {renfort.risk_pct:.3f}% contre {seul.risk_pct:.3f}% "
            "pour le premier : la pyramide concentre le compte")
        assert abs(renfort.risk_pct / seul.risk_pct - 0.6) < 0.05


class TestLeRejeuSaitEmpiler:
    """Le verrou qui ne casse rien mais qui ment.

    `if broker.positions(): continue` tenait UNE position a la fois. Armer
    la pyramide sans lever cette ligne aurait rendu un resultat identique
    au temoin — et on en aurait conclu que le renforcement ne sert a rien
    alors qu'il n'avait jamais eu lieu.
    """

    def test_hors_pyramide_le_rejeu_ne_tient_qu_une_position(self):
        """Les mesures du 30 aout doivent rester comparables."""
        import inspect
        from gold_bot.backtest import Backtester
        src = inspect.getsource(Backtester.run)
        assert "pyramide_max <= 0" in src, (
            "le rejeu ne distingue plus le mode simple du mode pyramide")

    def test_le_rejeu_ouvre_vraiment_plusieurs_etages(self):
        """Le test qui aurait attrape le mensonge.

        Sur une tendance franche, seuils desarmes, pyramide armee : le
        rejeu doit produire des trades qui se CHEVAUCHENT dans le temps.
        Sans chevauchement, aucun etage ne s'est jamais ajoute.
        """
        from gold_bot.backtest import Backtester
        from test_backtest_pipeline import _RegistreConstant, _serie_en_tendance

        cfg = BotConfig.load("robot.bitvavo.json")
        cfg.strategy.min_score = 0.0
        cfg.strategy.min_confirmations = 1
        cfg.strategy.min_adx = 0.0
        cfg.strategy.min_headroom_atr = 0.0
        cfg.strategy.min_atr_percentile = 0.0
        cfg.strategy.max_atr_percentile = 1.0
        cfg.strategy.min_atr_price_ratio = 0.0
        cfg.risk.pyramide_max = 2
        cfg.risk.min_seconds_between_trades = 0.0
        cfg.risk.max_positions = 6

        res = Backtester(cfg, registry=_RegistreConstant(_serie_en_tendance())).run(
            "BTCUSD", bars=700, start_balance=1000.0)
        assert res.trades, (
            "aucun trade : le test ne mesure rien. Motifs : "
            f"{sorted(res.rejections.items(), key=lambda kv: -kv[1])[:5]}")

        chevauchements = sum(
            1 for i, a in enumerate(res.trades) for b in res.trades[i + 1:]
            if b.opened_at < a.closed_at and a.opened_at < b.closed_at)
        assert chevauchements > 0, (
            f"{len(res.trades)} trades, aucun ne chevauche un autre : le "
            "rejeu tient toujours une seule position, la pyramide n'a "
            "jamais ete mesuree")


class TestLeStopCommunDeLaPyramide:
    """Les etages sortent ENSEMBLE, pas un par un par le haut.

    Le defaut corrige ici : chaque etage suivait son propre plus-haut avec
    la meme distance ATR. L'etage 2, entre plus haut, se retrouvait avec un
    stop AU-DESSUS de celui de l'etage 1 — au moindre repli c'est le
    renfort qui sautait, en payant l'aller-retour complet, pendant que la
    base survivait. On perdait exactement l'etage qu'on venait d'ajouter
    parce que ca montait.
    """

    @staticmethod
    def _gestionnaire(commun: bool):
        from gold_bot.trade_manager import TradeManager, TradeManagerConfig
        return TradeManager(TradeManagerConfig(pyramide_stop_commun=commun))

    @staticmethod
    def _pyramide():
        """Base a 100 (stop deja monte a 106), renfort a 110 (stop 108).

        Le renfort a le stop le plus haut : c'est lui qui saute en premier
        au moindre repli. Le point mort collectif vaut 105, il ne contraint
        donc pas ici — on mesure bien l'effet du niveau partage seul.
        """
        base = _position(entree=100.0, stop=106.0, pid="base")
        haut = _position(entree=110.0, stop=108.0, pid="haut")
        return base, haut

    def test_l_etage_haut_ne_se_resserre_pas_devant_les_autres(self):
        base, haut = self._pyramide()
        partage = self._gestionnaire(True).stop_partage(haut, [base, haut])
        assert partage == 106.0, (
            "le niveau partage doit valoir le stop le plus lache de la "
            f"pyramide (106.0), pas {partage}")
        assert partage < haut.stop_loss, (
            "l'etage haut garde un stop plus serre que les autres : il "
            "sortira encore seul au premier repli")

    def test_le_niveau_partage_ne_passe_pas_sous_le_point_mort_collectif(self):
        """Une pyramide ne doit jamais sortir collectivement perdante."""
        tm = self._gestionnaire(True)
        # Base a 100 avec un stop tres bas : le point mort collectif (105)
        # devient contraignant.
        base = _position(entree=100.0, stop=90.0, pid="base")
        haut = _position(entree=110.0, stop=108.0, pid="haut")
        partage = tm.stop_partage(haut, [base, haut])
        mort = tm.point_mort_collectif([base, haut])
        assert mort == 105.0
        assert partage == 105.0, (
            f"niveau partage {partage} sous le point mort collectif {mort} : "
            "la pyramide sortirait dans le rouge")

    def test_une_position_seule_n_est_pas_une_pyramide(self):
        base = _position(pid="base")
        assert self._gestionnaire(True).stop_partage(base, [base]) is None

    def test_desarme_rien_ne_change(self):
        """Sans le reglage, le comportement d'origine est intact."""
        from gold_bot.trade_manager import TradeManagerConfig
        assert TradeManagerConfig().pyramide_stop_commun is False


class TestLeRelevementTurtleRemonteToutePyramide:
    """Le filet qui remplace « n'ajouter que sur un etage a l'abri ».

    La Turtle renforce tot — tous les 0,5 N, bien avant que l'etage
    precedent ne soit a l'abri. Ce qui rend ca tenable n'est pas une
    condition d'entree mais une consequence : chaque unite ajoutee
    remonte le stop de TOUTE la pyramide sous elle. Sans ce relevement,
    desserrer `pyramide_locked_r_min` empile trois risques pleins sur une
    seule crypto — exactement le scenario que le reglage d'origine
    interdisait.
    """

    @staticmethod
    def _tm(arme: bool = True, stop_mult: float = 1.6):
        from gold_bot.trade_manager import TradeManager, TradeManagerConfig
        return TradeManager(TradeManagerConfig(
            pyramide_relevement_turtle=arme, atr_stop_mult=stop_mult))

    def test_le_plancher_suit_la_derniere_unite(self):
        """Base a 100, renfort a 110, ATR 4 : plancher a 110 - 1,6 x 4."""
        base = _position(entree=100.0, stop=96.8, pid="base")
        time.sleep(0.001)                      # l'ordre d'ouverture compte
        haut = _position(entree=110.0, stop=96.8, pid="haut")
        plancher = self._tm().plancher_turtle(haut, [base, haut], atr=4.0)
        assert plancher == 103.6, (
            f"plancher {plancher} au lieu de 110 - 1,6 x 4 = 103.6 : le "
            "relevement ne suit pas la derniere unite posee")
        assert plancher > base.entry_price, (
            "le plancher doit passer AU-DESSUS de l'entree de la base : "
            "c'est ce qui borne le risque de la pyramide entiere")

    def test_une_position_seule_n_est_pas_relevee(self):
        base = _position(pid="base")
        assert self._tm().plancher_turtle(base, [base], atr=4.0) is None

    def test_sans_atr_aucun_relevement(self):
        """Un ATR nul ne doit pas produire un plancher egal a l'entree."""
        base = _position(entree=100.0, pid="base")
        haut = _position(entree=110.0, pid="haut")
        assert self._tm().plancher_turtle(haut, [base, haut], atr=0.0) is None

    def test_un_autre_symbole_n_entre_pas_dans_la_famille(self):
        """Deux cryptos ne forment pas une pyramide, meme ouvertes ensemble."""
        sol = _position(symbole="SOLUSD", entree=100.0, pid="sol")
        ada = _position(symbole="ADAUSD", entree=110.0, pid="ada")
        assert self._tm().plancher_turtle(sol, [sol, ada], atr=4.0) is None

    def test_desarme_le_defaut_du_code_ne_releve_rien(self):
        from gold_bot.trade_manager import TradeManagerConfig
        assert TradeManagerConfig().pyramide_relevement_turtle is False
