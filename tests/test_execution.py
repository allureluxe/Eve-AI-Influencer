"""Tests d'execution : simulateur, persistance et boucle du moteur."""
from __future__ import annotations

import os
import tempfile
import time
import unittest

from helpers import pullback_setup_indicators  # noqa: F401 - insere le chemin

from gold_bot.brokers.base import BrokerError
from gold_bot.brokers.paper import PaperBroker, PaperConfig
from gold_bot.core import Candle, Position, Side, Tick
from gold_bot.state import StateStore, TradeJournal
from gold_bot.universe import Universe


class BaseBroker(unittest.TestCase):
    def setUp(self):
        self.universe = Universe()
        self.gold = self.universe.get("XAUUSD")
        self.broker = PaperBroker(PaperConfig(start_balance=10000.0, commission_pct=0.0,
                                              slippage_atr=0.0))
        self.broker.connect()
        self.broker.register_instrument(self.gold)
        self.broker.set_price("XAUUSD", Tick(0, 2649.85, 2650.15), atr=2.0)


class TestSimulateur(BaseBroker):
    def test_ouverture_sans_stop_refusee(self):
        with self.assertRaises(BrokerError):
            self.broker.open_position(self.gold, Side.BUY, 0.1, 0.0, 2660.0)

    def test_le_spread_est_paye_a_l_entree(self):
        pos = self.broker.open_position(self.gold, Side.BUY, 0.1, 2645.0, 2660.0)
        self.assertAlmostEqual(pos.entry_price, 2650.15)      # on achete au ask
        vente = self.broker.open_position(self.gold, Side.SELL, 0.1, 2655.0, 2640.0)
        self.assertAlmostEqual(vente.entry_price, 2649.85)    # on vend au bid

    def test_objectif_atteint_sur_la_meche(self):
        self.broker.open_position(self.gold, Side.BUY, 0.1, 2645.0, 2660.0)
        trades = self.broker.process_candle("XAUUSD", Candle(60, 2650, 2661, 2649, 2655, 100))
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0].reason, "objectif atteint")
        self.assertGreater(trades[0].profit, 0)

    def test_le_stop_prime_sur_l_objectif_dans_la_meme_bougie(self):
        # Hypothese prudente : quand une bougie touche les deux, on compte
        # la perte. Sinon un backtest surestime systematiquement les gains.
        self.broker.open_position(self.gold, Side.BUY, 0.1, 2645.0, 2660.0)
        trades = self.broker.process_candle("XAUUSD", Candle(60, 2650, 2661, 2644, 2655, 100))
        self.assertEqual(trades[0].reason, "stop-loss touche")
        self.assertLess(trades[0].profit, 0)

    def test_fermeture_partielle(self):
        pos = self.broker.open_position(self.gold, Side.BUY, 0.10, 2645.0, 2660.0)
        self.broker.set_price("XAUUSD", Tick(60, 2654.85, 2655.15), atr=2.0)
        trade = self.broker.close_position(pos.id, volume=0.04, reason="prise partielle")
        self.assertTrue(trade.partial)
        self.assertAlmostEqual(self.broker.positions()[0].volume, 0.06, places=6)

    def test_la_fermeture_finale_n_est_pas_partielle(self):
        pos = self.broker.open_position(self.gold, Side.BUY, 0.10, 2645.0, 2660.0)
        trade = self.broker.close_position(pos.id, reason="sortie")
        self.assertFalse(trade.partial)
        self.assertEqual(self.broker.positions(), [])

    def test_marge_insuffisante_refusee(self):
        petit = PaperBroker(PaperConfig(start_balance=100.0, leverage=10.0))
        petit.connect()
        petit.register_instrument(self.gold)
        petit.set_price("XAUUSD", Tick(0, 2649.85, 2650.15), atr=2.0)
        with self.assertRaises(BrokerError):
            petit.open_position(self.gold, Side.BUY, 5.0, 2645.0, 2660.0)

    def test_le_capital_flottant_suit_le_prix(self):
        self.broker.open_position(self.gold, Side.BUY, 0.10, 2645.0, 2670.0)
        depart = self.broker.account().equity
        self.broker.set_price("XAUUSD", Tick(60, 2659.85, 2660.15), atr=2.0)
        self.assertGreater(self.broker.account().equity, depart)


# La classe TestMoonX a ete retiree avec le broker qu'elle couvrait : le
# module moonx ne fournit plus que l'aide HTTP des notifications.

class TestPersistance(unittest.TestCase):
    def test_l_etat_de_gestion_survit_au_redemarrage(self):
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        try:
            store = StateStore(path)
            pos = Position(id="P1", symbol="XAUUSD", side=Side.BUY, volume=0.1,
                           entry_price=2650.0, stop_loss=2645.0, take_profit=2660.0,
                           opened_at=1000.0)
            pos.tp_extensions = 2
            pos.breakeven_done = True
            pos.max_favorable = 2658.0
            store.remember_position(pos)
            store.save()

            # Redemarrage : le broker rend la position, sans l'etat de gestion.
            store2 = StateStore(path)
            reprise = Position(id="P1", symbol="XAUUSD", side=Side.BUY, volume=0.1,
                               entry_price=2650.0, stop_loss=2656.0, take_profit=2668.0,
                               opened_at=1000.0)
            self.assertTrue(store2.restore_position(reprise))
            self.assertEqual(reprise.tp_extensions, 2)
            self.assertTrue(reprise.breakeven_done)
            self.assertAlmostEqual(reprise.initial_risk, 5.0)
            self.assertAlmostEqual(reprise.max_favorable, 2658.0)
        finally:
            os.path.exists(path) and os.unlink(path)

    def test_position_inconnue_signalee(self):
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        try:
            store = StateStore(path)
            pos = Position(id="INCONNU", symbol="XAUUSD", side=Side.BUY, volume=0.1,
                           entry_price=2650.0, stop_loss=2645.0, take_profit=2660.0,
                           opened_at=0.0)
            self.assertFalse(store.restore_position(pos))
        finally:
            os.path.exists(path) and os.unlink(path)


class TestJournal(unittest.TestCase):
    def test_les_partielles_ne_gonflent_pas_le_taux_de_reussite(self):
        from gold_bot.core import ClosedTrade
        fd, path = tempfile.mkstemp(suffix=".jsonl")
        os.close(fd)
        os.unlink(path)
        try:
            journal = TradeJournal(path)
            base = dict(symbol="XAUUSD", side=Side.BUY, volume=0.1, entry_price=2650.0,
                        exit_price=2655.0, opened_at=0.0, reason="test")
            journal.append(ClosedTrade(position_id="1", closed_at=1, profit=10.0,
                                       r_multiple=1.0, partial=True, **base))
            journal.append(ClosedTrade(position_id="1", closed_at=2, profit=-20.0,
                                       r_multiple=-1.0, partial=False, **base))
            stats = journal.stats()
            self.assertEqual(stats["trades"], 1)             # une seule vraie sortie
            self.assertEqual(stats["prises_partielles"], 1)
            self.assertEqual(stats["taux_reussite_pct"], 0.0)
            self.assertEqual(stats["profit_net"], -10.0)     # le flux reel compte tout
        finally:
            os.path.exists(path) and os.unlink(path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
