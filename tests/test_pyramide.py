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
    """Le renforcement ne s'arme pas tout seul : le rejeu tranche avant."""

    def test_le_reglage_livre_est_desarme(self):
        assert BotConfig.load("robot.bitvavo.json").risk.pyramide_max == 0

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
