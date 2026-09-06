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
                    "oscillateur", "volume", "vwap", "structure", "contexte",
                    "balayage", "carnet"}
        self.assertEqual(noms, attendus)

    def test_le_carnet_echoue_faute_de_donnees(self):
        """Une taille de carnet absente ne doit jamais valoir confirmation.

        Sans tick, la source ne dit rien sur la pression au meilleur prix.
        Compter ce silence comme favorable donnerait une confirmation
        gratuite a chaque instrument dont la source est muette.
        """
        ev = self.evaluate(self.strategy(), pullback_setup_indicators(1))
        carnet = next(c for c in ev.confirmations if c.name == "carnet")
        self.assertFalse(carnet.passed)
        self.assertIn("indisponibles", carnet.detail)

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


class TestPlancherDeCout(unittest.TestCase):
    """Le stop ne doit jamais etre si serre que le spread en mange l'essentiel.

    Formule exacte : cout / risque = (spread x valeur) / (stop x valeur),
    soit spread / stop. Ni le capital ni le volume n'y entrent. Pour tenir
    sous X %, il suffit d'un stop d'au moins spread / X.
    """

    def setUp(self):
        from gold_bot.trade_manager import TradeManagerConfig
        self.universe = Universe()
        self.strict = TradeManager(TradeManagerConfig(
            max_cost_ratio_pct=15.0, max_stop_atr_for_cost=4.0))
        self.sans = TradeManager(TradeManagerConfig(max_cost_ratio_pct=0.0))

    def _ratio(self, manager, price, atr, spread, digits):
        sl, _ = manager.initial_levels(Side.BUY, price, atr, spread=spread, digits=digits)
        return spread / (price - sl) * 100.0

    def test_le_plancher_ramene_le_forex_sous_le_seuil(self):
        # EURUSD en M1 : 19 % sans plancher, sous 15 % avec.
        sans = self._ratio(self.sans, 1.085, 0.000195, 0.00008, 5)
        avec = self._ratio(self.strict, 1.085, 0.000195, 0.00008, 5)
        self.assertGreater(sans, 15.0)
        self.assertLessEqual(avec, 15.0)

    def test_le_plancher_laisse_intact_ce_qui_va_deja_bien(self):
        # BTCUSD est deja a 7 % : le stop ne doit pas etre elargi pour rien.
        sans = self.sans.initial_levels(Side.BUY, 68000.0, 61.2, spread=8.0, digits=2)[0]
        avec = self.strict.initial_levels(Side.BUY, 68000.0, 61.2, spread=8.0, digits=2)[0]
        self.assertAlmostEqual(sans, avec, places=2)

    def test_le_plancher_est_borne(self):
        # Un spread absurde ne doit pas produire un stop absurde : au-dela de
        # max_stop_atr_for_cost, c'est l'unite de temps qui est en cause.
        atr = 0.000118
        sl, _ = self.strict.initial_levels(Side.BUY, 0.655, atr, spread=0.00012, digits=5)
        self.assertLessEqual((0.655 - sl) / atr, 4.0 + 1e-6)

    def test_marge_contre_l_arrondi_au_tick(self):
        # Regression : viser exactement le plafond donnait un stop qui, une
        # fois arrondi au tick, repassait juste au-dessus — et TOUT le forex
        # etait refuse alors qu'il n'en manquait presque rien.
        for price, atr, spread, digits in ((1.085, 0.000195, 0.00008, 5),
                                           (1.270, 0.000229, 0.00012, 5),
                                           (152.0, 0.0274, 0.010, 3),
                                           (2650.0, 0.9275, 0.30, 2)):
            ratio = self._ratio(self.strict, price, atr, spread, digits)
            self.assertLessEqual(ratio, 15.0,
                                 f"arrondi au tick : {ratio:.3f} % depasse le plafond")

    def test_le_ratio_annonce_correspond_au_stop_reel(self):
        estime = self.strict.cost_ratio(0.000195, 0.00008)
        reel = self._ratio(self.strict, 1.085, 0.000195, 0.00008, 5)
        self.assertAlmostEqual(estime, reel, delta=0.5)


class TestUniteDeTempsAdaptative(unittest.TestCase):
    """Le robot retient l'unite la plus fine dont le cout reste tenable."""

    def _indicateurs(self, price: float, atr_par_tf: dict[str, float]):
        from gold_bot.core import Candle
        from gold_bot.indicators import IndicatorSet
        out = {}
        for tf, atr in atr_par_tf.items():
            ind = IndicatorSet()
            p = price
            for i in range(120):
                o = p
                p = p + (atr * 0.3 if i % 2 else -atr * 0.25)
                ind.update(Candle(i * 60, o, max(o, p) + atr * 0.5, min(o, p) - atr * 0.5, p, 100))
            out[tf] = ind
        return out

    def _strategie(self):
        from gold_bot.trade_manager import TradeManagerConfig
        cfg = StrategyConfig(adaptive_timeframe=True, timeframe_ladder=["M1", "M5", "M15"],
                             max_cost_ratio_pct=15.0)
        return Strategy(cfg, TradeManager(TradeManagerConfig(
            max_cost_ratio_pct=15.0, max_stop_atr_for_cost=4.0)), macro=None)

    def test_la_crypto_reste_en_m1(self):
        u = Universe()
        inds = self._indicateurs(68000.0, {"M1": 61.2, "M5": 204.0, "M15": 374.0})
        tf, motif = self._strategie().pick_timeframe(u.get("BTCUSD"), inds, 8.0)
        self.assertEqual(tf, "M1", motif)

    def test_une_paire_a_spread_large_descend_en_m5(self):
        # AUDUSD : 20 % en M1 meme avec le plancher, 12 % en M5.
        u = Universe()
        inds = self._indicateurs(0.655, {"M1": 0.000118, "M5": 0.000393, "M15": 0.000721})
        tf, motif = self._strategie().pick_timeframe(u.get("AUDUSD"), inds, 0.00012)
        self.assertEqual(tf, "M5", motif)
        self.assertIn("M1", motif)

    def test_le_mode_fixe_ne_change_rien(self):
        u = Universe()
        strategy = Strategy(StrategyConfig(adaptive_timeframe=False, entry_tf="M5"),
                            TradeManager(), macro=None)
        inds = self._indicateurs(0.655, {"M1": 0.000118, "M5": 0.000393})
        tf, motif = strategy.pick_timeframe(u.get("AUDUSD"), inds, 0.00012)
        self.assertEqual(tf, "M5")
        self.assertEqual(motif, "unite de temps fixe")

    def test_les_donnees_de_toute_l_echelle_sont_chargees(self):
        strategy = self._strategie()
        for tf in ("M1", "M5", "M15"):
            self.assertIn(tf, strategy.timeframes)

    def test_l_unite_retenue_apparait_dans_le_verdict(self):
        u = Universe()
        strategy = self._strategie()
        strategy.config.mode = "quorum"
        ind = pullback_setup_indicators(-1)
        inds = {tf: ind for tf in ("M1", "M5", "M15", "H1")}
        p = ind.last.close
        ev = strategy.evaluate(u.get("XAUUSD"), inds,
                               Tick(mardi_14h(), p - 0.15, p + 0.15),
                               now=mardi_14h(), entry_tf="M5")
        self.assertEqual(ev.timeframe, "M5")


class TestScoreEnQuorum(BaseQuorum):
    """Le score doit etre une barriere, pas une decoration.

    Il avait ete rendu purement indicatif en mode quorum, le seuil force a
    zero. Observe en production le 28 aout : un achat XRP REEL ouvert sur un
    score de 0,24 — tendance +0,01, momentum +0,18, bougies +0,14 — alors
    que la configuration portait min_score a 0,55. Le reglage existait,
    s'affichait dans le journal, et ne servait a rien.

    Un compte de confirmations ne dit pas la meme chose qu'une force de
    signal : cinq confirmations faibles restent cinq confirmations.
    """

    def test_le_seuil_configure_est_bien_applique(self):
        ev = self.evaluate(self.strategy(min_confirmations=3, min_score=0.35),
                           pullback_setup_indicators(-1))
        self.assertAlmostEqual(ev.threshold, 0.35, places=4)

    def test_un_score_trop_faible_refuse_le_trade(self):
        """Le cas XRP : assez de confirmations, mais un signal trop mou."""
        ind = pullback_setup_indicators(-1)
        # Seuil hors d'atteinte : seul le score peut faire echouer ce trade.
        ev = self.evaluate(self.strategy(min_confirmations=3, min_score=9.0), ind)
        self.assertFalse(ev.valid, ev.explain())
        self.assertGreaterEqual(ev.confirmed, 3,
                                "le quorum etait atteint : c'est bien le score qui refuse")
        recalees = [g.name for g in ev.failed_gates()]
        self.assertIn("score", recalees)

    def test_un_score_suffisant_laisse_passer(self):
        ev = self.evaluate(self.strategy(min_confirmations=3, min_score=0.0),
                           pullback_setup_indicators(-1))
        self.assertTrue(ev.valid, ev.explain())

    def test_le_score_reste_lisible_dans_le_journal(self):
        ev = self.evaluate(self.strategy(min_confirmations=3, min_score=9.0),
                           pullback_setup_indicators(-1))
        self.assertIn("score", ev.explain())

    def test_le_retard_sur_objectif_ne_penalise_pas_deux_fois(self):
        """Le bonus d'objectif releve deja le quorum : pas aussi le score.

        Le compter des deux cotes punirait deux fois la meme situation, et
        le robot cesserait d'entrer exactement quand il doit se refaire.
        """
        ind = pullback_setup_indicators(-1)
        sans = self.evaluate(self.strategy(min_confirmations=3, min_score=0.35), ind)
        strat = self.strategy(min_confirmations=3, min_score=0.35)
        inds = {tf: ind for tf in ("M1", "M5", "M15", "H1")}
        p = ind.last.close
        avec = strat.evaluate(self.gold, inds,
                              Tick(self.now, p - 0.15, p + 0.15),
                              now=self.now, score_bonus=0.10)
        self.assertAlmostEqual(sans.threshold, avec.threshold, places=4)
        self.assertGreater(avec.required, sans.required,
                           "le retard doit exiger plus de confirmations")
