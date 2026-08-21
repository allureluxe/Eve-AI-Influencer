"""Tests de l'adaptateur Binance Futures.

Ils portent sur ce qui peut couter de l'argent : arrondis, contraintes de
la plateforme, protection de la position, et refus quand quelque chose ne
va pas. Aucun appel reseau : tout passe par le mode simulation.
"""
from __future__ import annotations

import unittest

from helpers import *  # noqa: F401,F403 - insere le chemin du projet

from gold_bot.brokers.base import BrokerError
from gold_bot.brokers.binance import (SYMBOLES, BinanceBroker, BinanceConfig,
                                      RegleSymbole)
from gold_bot.core import Side
from gold_bot.universe import Universe


def broker(**kw) -> BinanceBroker:
    cfg = BinanceConfig(dry_run=True, **kw)
    b = BinanceBroker(cfg)
    b.connect()
    for inst in Universe():
        b.register_instrument(inst)
    return b


class TestArrondis(unittest.TestCase):
    def setUp(self):
        self.regle = RegleSymbole("BTCUSDT", step_size=0.001, tick_size=0.10,
                                  min_qty=0.001, min_notional=5.0,
                                  quantity_precision=3, price_precision=1)

    def test_la_quantite_est_arrondie_vers_le_bas(self):
        # Vers le bas et jamais vers le haut : un arrondi genereux ferait
        # depasser le risque prevu a chaque ordre.
        self.assertAlmostEqual(self.regle.arrondir_quantite(0.0047), 0.004)
        self.assertAlmostEqual(self.regle.arrondir_quantite(0.0019), 0.001)

    def test_une_quantite_exacte_n_est_pas_rabotee(self):
        self.assertAlmostEqual(self.regle.arrondir_quantite(0.005), 0.005)

    def test_le_prix_suit_le_pas_de_cotation(self):
        self.assertAlmostEqual(self.regle.arrondir_prix(68123.456), 68123.5)

    def test_pas_de_lot_entier(self):
        # SOL se traite par unites entieres sur Binance.
        sol = RegleSymbole("SOLUSDT", step_size=1.0, min_qty=1.0, quantity_precision=0)
        self.assertAlmostEqual(sol.arrondir_quantite(2.9), 2.0)
        self.assertAlmostEqual(sol.arrondir_quantite(0.4), 0.0)


class TestSymboles(unittest.TestCase):
    def test_correspondance(self):
        self.assertEqual(broker().symbol_for("BTCUSD"), "BTCUSDT")

    def test_un_symbole_absent_est_refuse(self):
        with self.assertRaises(BrokerError):
            broker().symbol_for("XAUUSD")

    def test_supports_repond_sans_lever(self):
        b = broker()
        self.assertTrue(b.supports("BTCUSD"))
        self.assertFalse(b.supports("XAUUSD"))
        self.assertFalse(b.supports("EURUSD"))


class TestOuverture(unittest.TestCase):
    def setUp(self):
        self.broker = broker()
        self.universe = Universe()
        self.btc = self.universe.get("BTCUSD")

    def test_ouverture_sans_stop_refusee(self):
        with self.assertRaises(BrokerError):
            self.broker.open_position(self.btc, Side.BUY, 0.004, 0.0, 68500.0)

    def test_quantite_sous_le_minimum_refusee(self):
        with self.assertRaises(BrokerError) as ctx:
            self.broker.open_position(self.btc, Side.BUY, 0.0001, 67900.0, 68200.0)
        self.assertIn("minimum", str(ctx.exception))

    def test_notionnel_insuffisant_refuse(self):
        # Binance impose un notionnel minimal : une position trop petite est
        # rejetee par la plateforme, autant le detecter avant d'envoyer.
        self.broker._regles["BTCUSDT"] = RegleSymbole(
            "BTCUSDT", step_size=0.001, min_qty=0.001, min_notional=5000.0)
        with self.assertRaises(BrokerError) as ctx:
            self.broker.open_position(self.btc, Side.BUY, 0.001, 67900.0, 68200.0)
        self.assertIn("notionnel", str(ctx.exception))

    def test_ouverture_valide(self):
        pos = self.broker.open_position(self.btc, Side.BUY, 0.004, 67900.0, 68200.0)
        self.assertEqual(pos.symbol, "BTCUSD")
        self.assertIs(pos.side, Side.BUY)
        self.assertGreater(pos.stop_loss, 0)
        self.assertGreater(pos.take_profit, 0)
        self.assertEqual(len(self.broker.positions()), 1)

    def test_le_sens_vente_est_possible(self):
        # C'est la raison d'etre du choix des futures plutot que du spot.
        pos = self.broker.open_position(self.btc, Side.SELL, 0.004, 68200.0, 67700.0)
        self.assertIs(pos.side, Side.SELL)


class TestDeplacementDuStop(unittest.TestCase):
    """Binance ne modifie pas un ordre stop : il faut l'annuler et le reposer.

    On ne repose donc que si le niveau a reellement bouge, sinon le quota
    d'API serait consomme pour des variations invisibles.
    """

    def setUp(self):
        self.broker = broker(stop_move_threshold_r=0.10)
        self.btc = Universe().get("BTCUSD")
        self.pos = self.broker.open_position(self.btc, Side.BUY, 0.004, 67900.0, 68500.0)
        self.pos.initial_risk = 100.0      # 1R = 100 USDT de prix

    def test_un_petit_deplacement_met_a_jour_le_niveau_local(self):
        self.broker.modify_position(self.pos.id, stop_loss=67905.0)
        self.assertAlmostEqual(self.broker.positions()[0].stop_loss, 67905.0, places=1)

    def test_un_deplacement_significatif_est_applique(self):
        self.broker.modify_position(self.pos.id, stop_loss=68050.0)
        self.assertAlmostEqual(self.broker.positions()[0].stop_loss, 68050.0, places=1)

    def test_l_objectif_peut_etre_repousse(self):
        self.broker.modify_position(self.pos.id, take_profit=68900.0)
        self.assertAlmostEqual(self.broker.positions()[0].take_profit, 68900.0, places=1)

    def test_position_inconnue(self):
        self.assertFalse(self.broker.modify_position("INEXISTANT", stop_loss=1.0))


class TestFermeture(unittest.TestCase):
    def setUp(self):
        self.broker = broker()
        self.btc = Universe().get("BTCUSD")
        self.pos = self.broker.open_position(self.btc, Side.BUY, 0.010, 67900.0, 68500.0)

    def test_fermeture_totale(self):
        trade = self.broker.close_position(self.pos.id, reason="test")
        self.assertIsNotNone(trade)
        self.assertFalse(trade.partial)
        self.assertEqual(self.broker.positions(), [])

    def test_fermeture_partielle(self):
        trade = self.broker.close_position(self.pos.id, volume=0.004, reason="partielle")
        self.assertTrue(trade.partial)
        self.assertAlmostEqual(self.broker.positions()[0].volume, 0.006, places=6)

    def test_fermeture_d_une_position_absente(self):
        self.assertIsNone(self.broker.close_position("INEXISTANT"))


class TestContraintesDePlateforme(unittest.TestCase):
    def test_l_univers_est_aligne_sur_la_plateforme(self):
        # Le robot declare 0,1 pour SOL ; Binance exige 1. Sans alignement,
        # le dimensionnement produirait une quantite que Binance refuserait.
        b = broker()
        b._regles["SOLUSDT"] = RegleSymbole("SOLUSDT", step_size=1.0, min_qty=1.0,
                                            price_precision=3)
        universe = Universe()
        sol = universe.get("SOLUSD")
        self.assertAlmostEqual(sol.min_lot, 0.1)
        modifies = b.apply_market_rules(universe)
        self.assertAlmostEqual(sol.min_lot, 1.0)
        self.assertTrue(any("SOLUSD" in m for m in modifies))

    def test_un_symbole_hors_plateforme_est_ignore(self):
        b = broker()
        universe = Universe()
        or_ = universe.get("XAUUSD")
        avant = or_.min_lot
        b.apply_market_rules(universe)
        self.assertAlmostEqual(or_.min_lot, avant)


class TestConfiguration(unittest.TestCase):
    def test_le_testnet_est_le_defaut(self):
        # On ne doit jamais partir en argent reel par omission.
        self.assertTrue(BinanceConfig().testnet)

    def test_les_deux_bases_sont_distinctes(self):
        reel = BinanceBroker(BinanceConfig(testnet=False, api_key="x", api_secret="y"))
        essai = BinanceBroker(BinanceConfig(testnet=True, api_key="x", api_secret="y"))
        self.assertNotEqual(reel.base, essai.base)
        self.assertIn("testnet", essai.base)

    def test_le_mode_est_annonce_clairement(self):
        self.assertIn("testnet", BinanceBroker(BinanceConfig(testnet=True)).mode)
        self.assertEqual(BinanceBroker(BinanceConfig(testnet=False)).mode, "REEL")

    def test_sans_cle_la_connexion_echoue(self):
        b = BinanceBroker(BinanceConfig(dry_run=False, api_key="", api_secret=""))
        self.assertFalse(b.connect())
        self.assertFalse(b.healthy())

    def test_la_signature_est_deterministe(self):
        b = BinanceBroker(BinanceConfig(api_key="cle", api_secret="secret"))
        signe = b._signer({"symbol": "BTCUSDT"})
        self.assertIn("signature=", signe)
        self.assertIn("symbol=BTCUSDT", signe)
        self.assertIn("recvWindow=", signe)


if __name__ == "__main__":
    unittest.main(verbosity=2)
