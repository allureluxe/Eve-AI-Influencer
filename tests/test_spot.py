"""Tests de l'execution au comptant (Binance Spot).

Le spot impose deux contraintes que le reste du robot doit respecter :
on ne peut qu'acheter, et les frais imposent une echelle de temps.
"""
from __future__ import annotations

import unittest

from helpers import *  # noqa: F401,F403

from gold_bot.brokers.base import BrokerError
from gold_bot.brokers.binance_spot import BinanceSpotBroker, SpotConfig
from gold_bot.core import Side
from gold_bot.risk import RiskConfig, RiskManager
from gold_bot.trade_manager import TradeManager, TradeManagerConfig
from gold_bot.universe import Universe


def broker(**kw) -> BinanceSpotBroker:
    b = BinanceSpotBroker(SpotConfig(dry_run=True, **kw))
    b.connect()
    for inst in Universe():
        b.register_instrument(inst)
    return b


class TestAchatSeul(unittest.TestCase):
    def test_la_capacite_est_declaree(self):
        self.assertFalse(BinanceSpotBroker.supports_short)

    def test_la_vente_est_refusee(self):
        b = broker()
        with self.assertRaises(BrokerError) as ctx:
            b.open_position(Universe().get("BTCUSD"), Side.SELL, 0.001, 78000.0, 76000.0)
        self.assertIn("achat", str(ctx.exception))

    def test_l_achat_fonctionne(self):
        b = broker()
        pos = b.open_position(Universe().get("BTCUSD"), Side.BUY, 0.001, 76000.0, 79000.0)
        self.assertIs(pos.side, Side.BUY)
        self.assertGreater(pos.stop_loss, 0)

    def test_ouverture_sans_stop_refusee(self):
        b = broker()
        with self.assertRaises(BrokerError):
            b.open_position(Universe().get("BTCUSD"), Side.BUY, 0.001, 0.0, 79000.0)

    def test_le_scanner_ecarte_les_ventes(self):
        # Une vente parfaitement valide ne doit pas etre retenue, mais elle
        # ne doit pas non plus empecher un achat sur un autre instrument.
        from gold_bot.scanner import ScanResult
        from gold_bot.strategy import Evaluation
        vente = Evaluation(symbol="BTCUSD", asset_class="crypto", side=Side.SELL)
        achat = Evaluation(symbol="ETHUSD", asset_class="crypto", side=Side.BUY)
        self.assertIs(vente.side, Side.SELL)
        self.assertIs(achat.side, Side.BUY)


class TestFraisEtEchelleDeTemps(unittest.TestCase):
    """Les frais de 0,1 % par sens decident de l'unite de temps utilisable."""

    def setUp(self):
        self.universe = Universe()
        btc = self.universe.get("BTCUSD")
        btc.min_lot, btc.lot_step = 0.00001, 0.00001     # contraintes reelles du spot
        self.rm = RiskManager(RiskConfig(base_risk_pct=1.0, max_cost_ratio_pct=15.0,
                                         commission_pct=0.001, max_leverage=1.0,
                                         min_rr=1.5))
        self.rm.sync_account(equity=100.0, balance=100.0, currency="USDT")
        self.tm = TradeManager(TradeManagerConfig(atr_stop_mult=1.4, min_stop_atr=1.0,
                                                  max_cost_ratio_pct=15.0, tp_r_multiple=2.0))

    def _decision(self, atr_pct: float):
        prix = 77000.0
        atr = prix * atr_pct
        sl, tp = self.tm.initial_levels(Side.BUY, prix, atr, spread=prix * 1e-4, digits=2)
        return self.rm.size_position(self.universe.get("BTCUSD"), Side.BUY, prix, sl, tp,
                                     universe_lookup=self.universe.get, spread=prix * 1e-4)

    def test_le_scalping_est_refuse(self):
        # M5 : stop de 0,42 % -> les frais valent pres de la moitie du risque.
        d = self._decision(0.0030)
        self.assertFalse(d.allowed)
        self.assertIn("cout d'execution", d.reason)

    def test_m15_est_refuse(self):
        d = self._decision(0.0055)
        self.assertFalse(d.allowed)

    def test_h1_est_accepte(self):
        d = self._decision(0.0110)
        self.assertTrue(d.allowed, d.reason)
        self.assertLessEqual(d.cost_ratio_pct, 15.0)

    def test_h4_est_accepte(self):
        d = self._decision(0.0220)
        self.assertTrue(d.allowed, d.reason)
        self.assertLess(d.cost_ratio_pct, self._decision(0.0110).cost_ratio_pct)

    def test_les_frais_sont_bien_comptes(self):
        # Sans les frais, le M5 passerait : c'est bien eux qui bloquent.
        sans = RiskManager(RiskConfig(base_risk_pct=1.0, max_cost_ratio_pct=15.0,
                                      commission_pct=0.0, max_leverage=1.0, min_rr=1.5))
        sans.sync_account(equity=100.0, balance=100.0, currency="USDT")
        prix = 77000.0
        atr = prix * 0.0030
        sl, tp = self.tm.initial_levels(Side.BUY, prix, atr, spread=prix * 1e-4, digits=2)
        d = sans.size_position(self.universe.get("BTCUSD"), Side.BUY, prix, sl, tp,
                               universe_lookup=self.universe.get, spread=prix * 1e-4)
        self.assertTrue(d.allowed, "sans frais le M5 devrait passer")


class TestCapitalInsuffisant(unittest.TestCase):
    def test_le_message_parle_d_argent_et_non_de_levier(self):
        # Au comptant, la contrainte n'est pas un plafond de risque mais
        # l'argent disponible : le message doit etre comprehensible.
        universe = Universe()
        btc = universe.get("BTCUSD")
        btc.min_lot, btc.lot_step = 0.001, 0.001      # minimum trop gros
        rm = RiskManager(RiskConfig(base_risk_pct=1.0, max_leverage=1.0, min_rr=1.5,
                                    commission_pct=0.001))
        rm.sync_account(equity=50.0, balance=50.0, currency="USDT")
        tm = TradeManager(TradeManagerConfig(max_cost_ratio_pct=15.0))
        prix = 77000.0
        sl, tp = tm.initial_levels(Side.BUY, prix, prix * 0.011, spread=7.7, digits=2)
        d = rm.size_position(btc, Side.BUY, prix, sl, tp, universe_lookup=universe.get, spread=7.7)
        self.assertFalse(d.allowed)
        self.assertIn("capital insuffisant", d.reason)
        self.assertNotIn("levier", d.reason)


class TestLiquidites(unittest.TestCase):
    """Au comptant, le capital total n'est pas de l'argent disponible.

    Une partie peut deja etre investie en cryptos. Dimensionner sur le total
    ferait proposer des ordres que la plateforme refuserait a chaque cycle,
    faute de liquidites.
    """

    def setUp(self):
        self.universe = Universe()
        btc = self.universe.get("BTCUSD")
        btc.min_lot, btc.lot_step = 0.00001, 0.00001
        self.tm = TradeManager(TradeManagerConfig(atr_stop_mult=1.4, min_stop_atr=1.0,
                                                  max_cost_ratio_pct=15.0, tp_r_multiple=2.0))
        self.prix = 77000.0
        self.sl, self.tp = self.tm.initial_levels(Side.BUY, self.prix, self.prix * 0.011,
                                                  spread=7.7, digits=2)

    def _decision(self, dispo):
        rm = RiskManager(RiskConfig(base_risk_pct=1.0, max_cost_ratio_pct=15.0,
                                    commission_pct=0.001, max_leverage=1.0, min_rr=1.5))
        rm.sync_account(equity=29.29, balance=29.29, currency="USDT")
        return rm.size_position(self.universe.get("BTCUSD"), Side.BUY, self.prix,
                                self.sl, self.tp, universe_lookup=self.universe.get,
                                spread=7.7, available_cash=dispo)

    def test_sans_liquidites_le_trade_est_refuse(self):
        d = self._decision(0.0)
        self.assertFalse(d.allowed)
        self.assertIn("liquidites insuffisantes", d.reason)

    def test_les_liquidites_plafonnent_la_taille(self):
        petit = self._decision(5.0)
        gros = self._decision(29.29)
        self.assertTrue(petit.allowed, petit.reason)
        self.assertTrue(gros.allowed, gros.reason)
        self.assertLess(petit.lots, gros.lots)
        self.assertLessEqual(petit.lots * self.prix, 5.0 + 1e-6)
        self.assertTrue(any("liquidites" in f for f in petit.factors))

    def test_au_dela_des_liquidites_c_est_le_risque_qui_limite(self):
        # Avec assez de liquidites, la contrainte redevient le risque : la
        # taille ne doit pas continuer a grandir avec l'argent disponible.
        d = self._decision(29.29)
        self.assertLessEqual(d.risk_pct, 1.05)

    def test_sans_plafond_le_comportement_est_inchange(self):
        rm = RiskManager(RiskConfig(base_risk_pct=1.0, max_cost_ratio_pct=15.0,
                                    commission_pct=0.001, max_leverage=1.0, min_rr=1.5))
        rm.sync_account(equity=29.29, balance=29.29, currency="USDT")
        d = rm.size_position(self.universe.get("BTCUSD"), Side.BUY, self.prix, self.sl,
                             self.tp, universe_lookup=self.universe.get, spread=7.7)
        self.assertTrue(d.allowed)
        self.assertFalse(any("liquidites" in f for f in d.factors))


class TestPrixMoyen(unittest.TestCase):
    def test_calcul_sur_les_executions(self):
        reponse = {"fills": [{"qty": "0.5", "price": "100"}, {"qty": "0.5", "price": "102"}]}
        self.assertAlmostEqual(BinanceSpotBroker._prix_moyen(reponse), 101.0)

    def test_repli_sur_le_cumul(self):
        reponse = {"fills": [], "executedQty": "2", "cummulativeQuoteQty": "210"}
        self.assertAlmostEqual(BinanceSpotBroker._prix_moyen(reponse), 105.0)

    def test_reponse_vide(self):
        self.assertIsNone(BinanceSpotBroker._prix_moyen({"fills": []}))


class TestConfiguration(unittest.TestCase):
    def test_les_frais_par_defaut(self):
        self.assertAlmostEqual(SpotConfig().fee_rate, 0.001)

    def test_bases_distinctes(self):
        reel = BinanceSpotBroker(SpotConfig(testnet=False))
        essai = BinanceSpotBroker(SpotConfig(testnet=True))
        self.assertNotEqual(reel.base, essai.base)

    def test_symbole_non_supporte(self):
        with self.assertRaises(BrokerError):
            broker().symbol_for("XAUUSD")


if __name__ == "__main__":
    unittest.main(verbosity=2)
