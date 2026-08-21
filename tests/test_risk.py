"""Tests du money management : dimensionnement, echelle adaptative, coupe-circuits."""
from __future__ import annotations

import time
import unittest

from helpers import *  # noqa: F401,F403 - insere le chemin du projet

from gold_bot.core import ClosedTrade, Position, Side
from gold_bot.risk import EquityLadder, LadderStep, RiskConfig, RiskManager
from gold_bot.universe import Universe


class Base(unittest.TestCase):
    def setUp(self):
        self.universe = Universe()
        self.gold = self.universe.get("XAUUSD")
        self.rm = RiskManager(RiskConfig(base_risk_pct=1.0, max_risk_pct=2.0, min_risk_pct=0.2))
        self.rm.sync_account(equity=10000.0, balance=10000.0, currency="EUR")


class TestDimensionnement(Base):
    def test_le_volume_respecte_le_risque_demande(self):
        # 1 % de 10 000 = 100 EUR ; stop a 5 $ ; 1 lot d'or = 100 oz
        # -> 100 / (5 x 100) = 0.20 lot
        d = self.rm.size_position(self.gold, Side.BUY, 2650.0, 2645.0, 2665.0,
                                  universe_lookup=self.universe.get)
        self.assertTrue(d.allowed, d.reason)
        self.assertAlmostEqual(d.lots, 0.20, places=2)
        self.assertAlmostEqual(d.risk_amount, 100.0, delta=1.0)

    def test_un_stop_plus_large_reduit_le_volume(self):
        serre = self.rm.size_position(self.gold, Side.BUY, 2650.0, 2645.0, 2665.0,
                                      universe_lookup=self.universe.get)
        large = self.rm.size_position(self.gold, Side.BUY, 2650.0, 2635.0, 2695.0,
                                      universe_lookup=self.universe.get)
        self.assertLess(large.lots, serre.lots)
        # Le risque vise est le meme (1 % = 100 EUR). Le pas de lot empeche
        # de tomber pile dessus : on exige que le risque reel ne DEPASSE
        # jamais la cible, et reste a moins d'un pas de lot en dessous.
        for d in (serre, large):
            self.assertLessEqual(d.risk_amount, 100.0 + 1e-6, d.factors)
            pas_de_lot = self.gold.lot_step * self.gold.contract_size * d.stop_distance
            self.assertGreater(d.risk_amount, 100.0 - pas_de_lot)

    def test_l_arrondi_du_lot_ne_depasse_jamais_le_risque_vise(self):
        # Regression : un arrondi au plus proche gonflait le risque a chaque
        # trade (0.065 -> 0.07 lot = +8 % de risque, silencieusement).
        for stop in (2645.0, 2643.3, 2641.7, 2638.5):
            d = self.rm.size_position(self.gold, Side.BUY, 2650.0, stop, 2680.0,
                                      universe_lookup=self.universe.get)
            if d.allowed:
                self.assertLessEqual(d.risk_pct, 1.0 + 1e-9,
                                     f"risque depasse avec un stop a {stop}")

    def test_stop_nul_refuse(self):
        d = self.rm.size_position(self.gold, Side.BUY, 2650.0, 2650.0, 2665.0,
                                  universe_lookup=self.universe.get)
        self.assertFalse(d.allowed)
        self.assertIn("stop-loss", d.reason)

    def test_ratio_insuffisant_refuse(self):
        d = self.rm.size_position(self.gold, Side.BUY, 2650.0, 2645.0, 2651.0,
                                  universe_lookup=self.universe.get)
        self.assertFalse(d.allowed)
        self.assertIn("rendement/risque", d.reason)

    def test_petit_capital_refuse_plutot_que_sur_risquer(self):
        # 200 EUR de capital : le lot minimum (0.01) sur un stop de 5 $
        # represente 5 EUR, soit 2.5 % — au-dessus du plafond.
        rm = RiskManager(RiskConfig(base_risk_pct=1.0, max_risk_pct=1.5))
        rm.sync_account(equity=200.0, balance=200.0)
        d = rm.size_position(self.gold, Side.BUY, 2650.0, 2645.0, 2665.0,
                             universe_lookup=self.universe.get)
        self.assertFalse(d.allowed)
        self.assertIn("plafond", d.reason)

    def test_le_levier_plafonne_le_volume(self):
        rm = RiskManager(RiskConfig(base_risk_pct=2.0, max_risk_pct=2.0, max_leverage=5.0))
        rm.sync_account(equity=10000.0, balance=10000.0)
        # Stop tres serre : sans plafond de levier le volume exploserait.
        d = rm.size_position(self.gold, Side.BUY, 2650.0, 2649.5, 2655.0,
                             universe_lookup=self.universe.get)
        notional = d.lots * 2650.0 * self.gold.contract_size
        self.assertLessEqual(notional, 10000.0 * 5.0 + 1.0)


class TestEchelleAdaptative(unittest.TestCase):
    """La taille monte avec les gains et descend avec les pertes."""

    def setUp(self):
        self.ladder = EquityLadder()

    def test_taille_neutre_a_la_reference(self):
        mult, _ = self.ladder.multiplier(1000.0, 1000.0)
        self.assertAlmostEqual(mult, 1.0)

    def test_la_taille_monte_avec_les_gains(self):
        m10, _ = self.ladder.multiplier(1100.0, 1000.0)
        m25, _ = self.ladder.multiplier(1250.0, 1000.0)
        m50, _ = self.ladder.multiplier(1500.0, 1000.0)
        self.assertGreater(m10, 1.0)
        self.assertGreater(m25, m10)
        self.assertGreater(m50, m25)

    def test_la_taille_descend_avec_les_pertes(self):
        m8, _ = self.ladder.multiplier(920.0, 1000.0)
        m15, _ = self.ladder.multiplier(850.0, 1000.0)
        m25, _ = self.ladder.multiplier(750.0, 1000.0)
        self.assertLess(m8, 1.0)
        self.assertLess(m15, m8)
        self.assertLess(m25, m15)

    def test_les_multiplicateurs_restent_bornes(self):
        haut, _ = self.ladder.multiplier(1_000_000.0, 1000.0)
        bas, _ = self.ladder.multiplier(1.0, 1000.0)
        self.assertLessEqual(haut, self.ladder.ceiling)
        self.assertGreaterEqual(bas, self.ladder.floor)

    def test_effet_sur_le_risque_reel(self):
        rm = RiskManager(RiskConfig(base_risk_pct=1.0, max_risk_pct=2.0))
        rm.sync_account(equity=12500.0, balance=12500.0)
        rm.account.reference_equity = 10000.0        # +25 %
        risk, factors = rm.effective_risk_pct()
        self.assertGreater(risk, 1.0)
        self.assertTrue(any("x1.45" in f for f in factors), factors)

    def test_le_plafond_dur_n_est_jamais_franchi(self):
        rm = RiskManager(RiskConfig(base_risk_pct=1.5, max_risk_pct=2.0))
        rm.sync_account(equity=100000.0, balance=100000.0)
        rm.account.reference_equity = 10000.0        # +900 %
        risk, _ = rm.effective_risk_pct(extra_multiplier=3.0)
        self.assertLessEqual(risk, 2.0)


class TestCoupeCircuits(Base):
    def test_limite_de_perte_journaliere(self):
        self.rm.account.day_start_equity = 10000.0
        self.rm.sync_account(equity=9500.0, balance=9500.0)   # -5 %
        ok, why = self.rm.can_trade([])
        self.assertFalse(ok)
        self.assertIn("journaliere", why)

    def test_arret_sur_drawdown_maximal(self):
        self.rm.account.peak_equity = 10000.0
        self.rm.sync_account(equity=7500.0, balance=7500.0)   # -25 %
        ok, why = self.rm.can_trade([])
        self.assertFalse(ok)
        self.assertTrue(self.rm.account.halted)

    def test_pause_apres_pertes_consecutives(self):
        for i in range(4):
            self.rm.record_close(ClosedTrade(
                position_id=str(i), symbol="XAUUSD", side=Side.BUY, volume=0.1,
                entry_price=2650, exit_price=2645, opened_at=0, closed_at=time.time(),
                profit=-50.0, r_multiple=-1.0, reason="stop"))
        ok, why = self.rm.can_trade([])
        self.assertFalse(ok)
        self.assertIn("pause", why)

    def test_le_risque_diminue_apres_des_pertes(self):
        normal, _ = self.rm.effective_risk_pct()
        for i in range(3):
            self.rm.record_close(ClosedTrade(
                position_id=str(i), symbol="XAUUSD", side=Side.BUY, volume=0.1,
                entry_price=2650, exit_price=2645, opened_at=0, closed_at=time.time(),
                profit=-50.0, r_multiple=-1.0, reason="stop"))
        apres, factors = self.rm.effective_risk_pct()
        self.assertLess(apres, normal)
        self.assertTrue(any("pertes d'affilee" in f for f in factors))

    def test_gain_journalier_protege_la_journee(self):
        self.rm.account.day_start_equity = 10000.0
        self.rm.sync_account(equity=10700.0, balance=10700.0)   # +7 %
        ok, why = self.rm.can_trade([])
        self.assertFalse(ok)
        self.assertIn("journalier", why)


class TestExposition(Base):
    def _pos(self, symbol: str) -> Position:
        return Position(id=symbol, symbol=symbol, side=Side.BUY, volume=0.1,
                        entry_price=100.0, stop_loss=99.0, take_profit=103.0, opened_at=0.0)

    def test_pas_deux_positions_sur_le_meme_instrument(self):
        ok, why = self.rm.check_exposure(self.gold, Side.BUY, [self._pos("XAUUSD")],
                                         self.universe.get)
        self.assertFalse(ok)
        self.assertIn("deja ouverte", why)

    def test_pas_deux_positions_sur_un_groupe_correle(self):
        # XAUUSD et XAGUSD partagent le groupe "metals".
        ok, why = self.rm.check_exposure(self.gold, Side.BUY, [self._pos("XAGUSD")],
                                         self.universe.get)
        self.assertFalse(ok)
        self.assertIn("correle", why)

    def test_groupes_differents_autorises(self):
        ok, _ = self.rm.check_exposure(self.gold, Side.BUY, [self._pos("BTCUSD")],
                                       self.universe.get)
        self.assertTrue(ok)

    def test_le_risque_ouvert_est_compte(self):
        pos = Position(id="1", symbol="XAUUSD", side=Side.BUY, volume=0.20,
                       entry_price=2650.0, stop_loss=2645.0, take_profit=2665.0, opened_at=0.0)
        pct = self.rm.open_risk_pct([pos], self.universe.get)
        self.assertAlmostEqual(pct, 1.0, delta=0.05)     # 100 EUR sur 10 000

    def test_un_stop_en_profit_ne_compte_plus_comme_risque(self):
        pos = Position(id="1", symbol="XAUUSD", side=Side.BUY, volume=0.20,
                       entry_price=2650.0, stop_loss=2655.0, take_profit=2670.0, opened_at=0.0)
        self.assertEqual(self.rm.open_risk_pct([pos], self.universe.get), 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
