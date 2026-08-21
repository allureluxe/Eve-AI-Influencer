"""Tests du mode quorum et du filtre cout/risque.

Ces deux mecanismes vont ensemble : le quorum ouvre la porte a beaucoup plus
de trades, le filtre cout/risque empeche que cette frequence detruise le
compte en frais.
"""
from __future__ import annotations

import time
import unittest

from helpers import flat_indicators, pullback_setup_indicators, trending_indicators

from gold_bot.core import Side, Tick
from gold_bot.risk import RiskConfig, RiskManager
from gold_bot.strategy import Strategy, StrategyConfig
from gold_bot.trade_manager import TradeManager, TradeManagerConfig
from gold_bot.universe import Universe


def mardi_14h() -> float:
    return time.mktime(time.strptime("2026-08-18 14:00:00", "%Y-%m-%d %H:%M:%S"))


class BaseQuorum(unittest.TestCase):
    def setUp(self):
        self.universe = Universe()
        self.gold = self.universe.get("XAUUSD")
        self.now = mardi_14h()

    def strategy(self, **kw) -> Strategy:
        cfg = StrategyConfig(mode="quorum", **kw)
        return Strategy(cfg, TradeManager(TradeManagerConfig()), macro=None)

    def evaluate(self, strategy, ind, spread=0.30):
        inds = {tf: ind for tf in ("M1", "M5", "M15", "H1")}
        p = ind.last.close
        return strategy.evaluate(self.gold, inds,
                                 Tick(self.now, p - spread / 2, p + spread / 2), now=self.now)


class TestQuorum(BaseQuorum):
    def test_trois_confirmations_suffisent(self):
        ev = self.evaluate(self.strategy(min_confirmations=3), pullback_setup_indicators(-1))
        self.assertTrue(ev.valid, ev.explain())
        self.assertGreaterEqual(ev.confirmed, 3)
        self.assertEqual(ev.mode, "quorum")

    def test_l_unanimite_n_est_pas_exigee(self):
        # Le point de tout le mode : des confirmations manquantes n'empechent
        # pas le trade, du moment que le quorum est atteint.
        ev = self.evaluate(self.strategy(min_confirmations=3), pullback_setup_indicators(-1))
        self.assertTrue(ev.valid)
        self.assertTrue(any(not c.passed for c in ev.confirmations),
                        "le cas de test devrait avoir des confirmations manquantes")

    def test_un_quorum_eleve_refuse_le_meme_signal(self):
        ind = pullback_setup_indicators(-1)
        souple = self.evaluate(self.strategy(min_confirmations=3), ind)
        strict = self.evaluate(self.strategy(min_confirmations=9), ind)
        self.assertTrue(souple.valid)
        self.assertFalse(strict.valid)

    def test_les_confirmations_sont_toutes_evaluees(self):
        ev = self.evaluate(self.strategy(), pullback_setup_indicators(1))
        noms = {c.name for c in ev.confirmations}
        attendus = {"bougies", "tendance", "momentum", "supertrend",
                    "oscillateur", "volume", "vwap", "structure", "contexte"}
        self.assertEqual(noms, attendus)

    def test_marche_indecis_refuse(self):
        # Sans avance nette d'un sens sur l'autre, aucun trade.
        ev = self.evaluate(self.strategy(min_confirmations=2), flat_indicators())
        self.assertFalse(ev.valid)

    def test_bougies_obligatoires(self):
        strategy = self.strategy(min_confirmations=1, require_candle_confirmation=True)
        ev = self.evaluate(strategy, trending_indicators(1))
        bougies = next((c for c in ev.confirmations if c.name == "bougies"), None)
        if bougies is not None and not bougies.passed:
            self.assertFalse(ev.valid, "sans lecture des bougies, le trade doit etre refuse")
            gate = next(g for g in ev.gates if g.name == "bougies_obligatoires")
            self.assertFalse(gate.passed)

    def test_un_verdict_valide_garde_stop_et_objectif(self):
        ev = self.evaluate(self.strategy(), pullback_setup_indicators(-1))
        self.assertTrue(ev.valid)
        self.assertGreater(ev.stop_loss, ev.entry)
        self.assertLess(ev.take_profit, ev.entry)
        self.assertGreaterEqual(ev.rr, 1.5)

    def test_le_retard_sur_objectif_releve_le_quorum(self):
        ind = pullback_setup_indicators(-1)
        strategy = self.strategy(min_confirmations=3)
        inds = {tf: ind for tf in ("M1", "M5", "M15", "H1")}
        p = ind.last.close
        tick = Tick(self.now, p - 0.15, p + 0.15)
        normal = strategy.evaluate(self.gold, inds, tick, now=self.now)
        durci = strategy.evaluate(self.gold, inds, tick, score_bonus=0.10, now=self.now)
        self.assertEqual(normal.required, 3)
        self.assertEqual(durci.required, 4, "en retard, on exige une preuve de plus")

    def test_le_mode_confluence_reste_intact(self):
        confluence = Strategy(StrategyConfig(mode="confluence"),
                              TradeManager(TradeManagerConfig()), macro=None)
        ev = self.evaluate(confluence, pullback_setup_indicators(-1))
        self.assertEqual(ev.mode, "confluence")
        self.assertEqual(ev.setup, "tendance_repli")
        self.assertGreater(ev.threshold, 0.0)


class TestFiltreCout(unittest.TestCase):
    """Le rapport cout/risque decide de la survie d'un petit compte."""

    def setUp(self):
        self.universe = Universe()
        self.rm = RiskManager(RiskConfig(base_risk_pct=1.0, max_cost_ratio_pct=15.0, min_rr=1.3))
        self.rm.sync_account(equity=50.0, balance=50.0)

    def _size(self, symbol, price, atr, rr=1.6):
        inst = self.universe.get(symbol)
        stop = 1.6 * atr + 2.0 * inst.typical_spread
        return self.rm.size_position(inst, Side.BUY, price, price - stop,
                                     price + stop * rr, universe_lookup=self.universe.get)

    def test_le_forex_en_m1_est_refuse_pour_cause_de_cout(self):
        # Stop tres serre : le spread devient une part enorme du risque.
        d = self._size("EURUSD", 1.085, 0.000195)
        self.assertFalse(d.allowed)
        self.assertIn("cout d'execution", d.reason)
        self.assertGreater(d.cost_ratio_pct, 15.0)

    def test_la_crypto_en_m1_passe(self):
        d = self._size("BTCUSD", 68000.0, 61.2)
        self.assertTrue(d.allowed, d.reason)
        self.assertLessEqual(d.cost_ratio_pct, 15.0)

    def test_un_stop_plus_large_rend_l_instrument_viable(self):
        # Meme instrument, unite de temps superieure : le cout devient
        # negligeable face au risque. C'est le vrai remede.
        # On prend un capital ou le lot minimum tient, pour isoler l'effet
        # du cout de celui du lot minimum.
        self.rm.sync_account(equity=250.0, balance=250.0)
        serre = self._size("EURUSD", 1.085, 0.000195)      # stop M1
        large = self._size("EURUSD", 1.085, 0.000651)      # stop M5
        self.assertFalse(serre.allowed)
        self.assertIn("cout d'execution", serre.reason)
        self.assertTrue(large.allowed, large.reason)
        self.assertLess(large.cost_ratio_pct, serre.cost_ratio_pct)

    def test_les_deux_plafonds_sont_distincts(self):
        # Deux refus differents, deux causes differentes : le lot minimum
        # depend du capital, le cout d'execution n'en depend pas. Le message
        # doit dire lequel bloque.
        self.rm.sync_account(equity=50.0, balance=50.0)
        lot = self._size("EURUSD", 1.085, 0.000651)        # stop M5, capital trop petit
        self.assertFalse(lot.allowed)
        self.assertIn("lot minimum", lot.reason)

        cout = self._size("EURUSD", 1.085, 0.000195)       # stop M1, cout trop lourd
        self.assertFalse(cout.allowed)
        self.assertIn("cout d'execution", cout.reason)

    def test_le_ratio_ne_depend_pas_du_capital(self):
        # Le cout est une propriete de l'instrument et de l'unite de temps,
        # pas de la taille du compte : doubler le capital double aussi le
        # volume, donc le rapport reste identique.
        petit = self._size("BTCUSD", 68000.0, 61.2)
        self.rm.sync_account(equity=500.0, balance=500.0)
        gros = self._size("BTCUSD", 68000.0, 61.2)
        self.assertAlmostEqual(petit.cost_ratio_pct, gros.cost_ratio_pct, delta=1.0)

    def test_le_filtre_peut_etre_desactive(self):
        rm = RiskManager(RiskConfig(base_risk_pct=1.0, max_cost_ratio_pct=0.0, min_rr=1.3))
        rm.sync_account(equity=50.0, balance=50.0)
        inst = self.universe.get("EURUSD")
        stop = 1.6 * 0.000195 + 2.0 * inst.typical_spread
        d = rm.size_position(inst, Side.BUY, 1.085, 1.085 - stop, 1.085 + stop * 1.6,
                             universe_lookup=self.universe.get)
        self.assertTrue(d.allowed)

    def test_le_cout_est_rapporte_dans_la_decision(self):
        d = self._size("BTCUSD", 68000.0, 61.2)
        self.assertGreater(d.cost, 0.0)
        self.assertTrue(any("cout" in f for f in d.factors))


class TestMiseEnSommeil(unittest.TestCase):
    """Un instrument structurellement inexploitable est mis de cote."""

    def _scanner(self):
        from gold_bot.datasources import build_registry
        from gold_bot.news import NewsFilter, RecurringCalendar
        from gold_bot.scanner import Scanner
        strategy = Strategy(StrategyConfig(), TradeManager(TradeManagerConfig()), macro=None)
        return Scanner(build_registry(offline=True), Universe(), strategy,
                       NewsFilter(sources=[RecurringCalendar()]))

    def test_mise_en_sommeil_et_reveil(self):
        sc = self._scanner()
        sc.sleep_symbol("XAUUSD", 3600.0, "lot minimum trop lourd")
        endormi, motif = sc.is_dormant("XAUUSD")
        self.assertTrue(endormi)
        self.assertIn("lot minimum", motif)
        sc.wake_symbol("XAUUSD")
        self.assertFalse(sc.is_dormant("XAUUSD")[0])

    def test_le_sommeil_expire(self):
        sc = self._scanner()
        sc.sleep_symbol("XAUUSD", 60.0, "test")
        self.assertFalse(sc.is_dormant("XAUUSD", now=time.time() + 120)[0])

    def test_un_instrument_endormi_n_est_pas_scanne(self):
        sc = self._scanner()
        sc.universe.enable_only(["BTCUSD", "ETHUSD"])
        sc.sleep_symbol("BTCUSD", 3600.0, "cout trop lourd")
        result = sc.scan()
        self.assertNotIn("BTCUSD", [e.symbol for e in result.evaluations])
        self.assertIn("BTCUSD", result.errors)


if __name__ == "__main__":
    unittest.main(verbosity=2)
