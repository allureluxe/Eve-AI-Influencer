"""Tests du moteur de decision : les filtres eliminatoires doivent ecarter."""
from __future__ import annotations

import time
import unittest

from helpers import (flat_indicators, pullback_setup_indicators,
                     trending_indicators, zigzag_indicators)

from gold_bot.core import Side, Tick
from gold_bot.news import EconomicEvent, NewsWindow
from gold_bot.strategy import Evaluation, Strategy, StrategyConfig
from gold_bot.trade_manager import TradeManager, TradeManagerConfig
from gold_bot.universe import Instrument, Universe


def mardi_14h() -> float:
    """Un mardi 14h UTC : plein chevauchement Londres / New York."""
    return time.mktime(time.strptime("2026-08-18 14:00:00", "%Y-%m-%d %H:%M:%S"))


class Base(unittest.TestCase):
    def setUp(self):
        self.universe = Universe()
        self.gold = self.universe.get("XAUUSD")
        self.strategy = Strategy(StrategyConfig(), TradeManager(TradeManagerConfig()), macro=None)
        self.now = mardi_14h()

    def indicators(self, direction: int = 1):
        """Cas d'ecole : tendance etablie + repli + bougie de reprise."""
        ind = pullback_setup_indicators(direction)
        return {"M1": ind, "M5": ind, "M15": ind, "H1": ind}

    def evaluate(self, indicators=None, tick=None, news=None, instrument=None):
        inds = indicators or self.indicators()
        if tick is None:
            price = inds["M5"].last.close
            tick = Tick(self.now, price - 0.15, price + 0.15)
        t = tick
        return self.strategy.evaluate(instrument or self.gold, inds, t,
                                      news=news, now=self.now)

    def gate(self, ev: Evaluation, name: str):
        return next((g for g in ev.gates if g.name == name), None)


class TestFiltresEliminatoires(Base):
    def test_historique_insuffisant_ecarte(self):
        from gold_bot.indicators import IndicatorSet
        vide = IndicatorSet()
        ev = self.evaluate(indicators={"M1": vide, "M5": vide, "M15": vide, "H1": vide},
                           tick=Tick(self.now, 2649.9, 2650.1))
        self.assertFalse(ev.valid)
        self.assertFalse(self.gate(ev, "donnees").passed)

    def test_spread_anormal_ecarte(self):
        inds = self.indicators()
        price = inds["M5"].last.close
        ev = self.evaluate(indicators=inds, tick=Tick(self.now, price - 1.5, price + 1.5))
        self.assertFalse(ev.valid)
        self.assertFalse(self.gate(ev, "spread").passed)

    def test_marche_ferme_ecarte(self):
        # Samedi : l'or ne cote pas.
        samedi = time.mktime(time.strptime("2026-08-22 14:00:00", "%Y-%m-%d %H:%M:%S"))
        inds = self.indicators()
        price = inds["M5"].last.close
        ev = self.strategy.evaluate(self.gold, inds, Tick(samedi, price - 0.15, price + 0.15),
                                    now=samedi)
        self.assertFalse(ev.valid)
        self.assertFalse(self.gate(ev, "marche_ouvert").passed)

    def test_annonce_imminente_ecarte(self):
        window = NewsWindow(blocked=True, reason="NFP dans 10 min",
                            event=EconomicEvent(self.now + 600, "NFP", "USD", "high"))
        ev = self.evaluate(news=window)
        self.assertFalse(ev.valid)
        self.assertFalse(self.gate(ev, "calendrier").passed)

    def test_marche_sans_configuration_ecarte(self):
        plat = flat_indicators()
        ev = self.evaluate(indicators={"M1": plat, "M5": plat, "M15": plat, "H1": plat})
        self.assertFalse(ev.valid)
        self.assertIsNone(ev.side)

    def test_l_ordre_des_filtres_evite_le_travail_inutile(self):
        # Un filtre precoce en echec doit arreter l'evaluation : pas de
        # score calcule, pas de niveaux, pas d'appel macro.
        inds = self.indicators()
        price = inds["M5"].last.close
        ev = self.evaluate(indicators=inds, tick=Tick(self.now, price - 1.5, price + 1.5))
        self.assertEqual(ev.components, [])
        self.assertEqual(ev.stop_loss, 0.0)


class TestCoherenceDuVerdict(Base):
    def test_un_verdict_valide_a_toujours_un_stop_et_un_objectif(self):
        for direction in (1, -1):
            ev = self.evaluate(indicators=self.indicators(direction))
            if ev.valid:
                self.assertGreater(ev.stop_loss, 0)
                self.assertGreater(ev.take_profit, 0)
                self.assertGreaterEqual(ev.rr, self.strategy.config.min_rr)
                if ev.side is Side.BUY:
                    self.assertLess(ev.stop_loss, ev.entry)
                    self.assertGreater(ev.take_profit, ev.entry)
                else:
                    self.assertGreater(ev.stop_loss, ev.entry)
                    self.assertLess(ev.take_profit, ev.entry)

    def test_un_verdict_valide_a_tous_ses_filtres_passes(self):
        ev = self.evaluate()
        if ev.valid:
            self.assertTrue(all(g.passed for g in ev.gates))
            self.assertGreaterEqual(ev.score, ev.threshold)

    def test_le_seuil_monte_avec_le_bonus(self):
        inds = self.indicators()
        price = inds["M5"].last.close
        tick = Tick(self.now, price - 0.15, price + 0.15)
        base = self.strategy.evaluate(self.gold, inds, tick, now=self.now)
        dur = self.strategy.evaluate(self.gold, inds, tick, score_bonus=0.2, now=self.now)
        if base.side is not None:
            self.assertAlmostEqual(dur.threshold - base.threshold, 0.2, places=6)

    def test_l_explication_est_toujours_lisible(self):
        for inds in (self.indicators(1), self.indicators(-1),
                     {k: flat_indicators() for k in ("M1", "M5", "M15", "H1")}):
            ev = self.evaluate(indicators=inds)
            texte = ev.explain()
            self.assertTrue(texte.startswith(self.gold.symbol))
            self.assertGreater(len(texte), 20)


class TestCheminNominal(Base):
    """Une configuration de manuel doit etre acceptee et produire un ordre complet."""

    def test_une_vente_sur_repli_est_validee(self):
        ev = self.evaluate(indicators=self.indicators(-1))
        self.assertTrue(ev.valid, ev.explain())
        self.assertIs(ev.side, Side.SELL)
        self.assertEqual(ev.setup, "tendance_repli")
        self.assertGreater(ev.stop_loss, ev.entry)
        self.assertLess(ev.take_profit, ev.entry)
        self.assertGreaterEqual(ev.rr, 1.5)

    def test_tous_les_filtres_sont_franchis(self):
        ev = self.evaluate(indicators=self.indicators(-1))
        self.assertTrue(ev.valid)
        attendus = {"donnees", "marche_ouvert", "spread", "volatilite", "calendrier",
                    "configuration", "regime", "alignement_mtf", "marge_structurelle",
                    "ratio_rr", "macro", "score"}
        self.assertTrue(attendus.issubset({g.name for g in ev.gates}),
                        attendus - {g.name for g in ev.gates})

    def test_une_annonce_annule_meme_une_bonne_configuration(self):
        # Verification que le filtre calendrier prime sur la qualite du signal.
        bonne = self.evaluate(indicators=self.indicators(-1))
        self.assertTrue(bonne.valid)
        bloquee = self.evaluate(
            indicators=self.indicators(-1),
            news=NewsWindow(blocked=True, reason="FOMC dans 12 min",
                            event=EconomicEvent(self.now + 720, "FOMC", "USD", "high")))
        self.assertFalse(bloquee.valid)

    def test_un_chiffre_rond_ne_bloque_pas_un_trade(self):
        # Regression : les paliers psychologiques (tous les 10 $ sur l'or)
        # etaient traites comme des resistances majeures et rejetaient la
        # quasi-totalite des configurations valables.
        ev = self.evaluate(indicators=self.indicators(-1))
        marge = self.gate(ev, "marge_structurelle")
        self.assertTrue(marge.passed, marge.detail)


class TestScore(Base):
    def test_les_composantes_sont_bornees(self):
        ev = self.evaluate()
        if ev.components:
            poids = {
                "tendance": self.strategy.config.w_trend,
                "momentum": self.strategy.config.w_momentum,
                "bougies": self.strategy.config.w_candles,
                "figures": self.strategy.config.w_chart,
                "divergences": self.strategy.config.w_divergence,
                "zones": self.strategy.config.w_zones,
                "volume": self.strategy.config.w_volume,
                "macro": self.strategy.config.w_macro,
                "news": self.strategy.config.w_news,
            }
            for c in ev.components:
                limite = poids.get(c.name, 1.0)
                self.assertLessEqual(abs(c.value), limite + 1e-9,
                                     f"{c.name} depasse son poids ({c.value} > {limite})")

    def test_le_score_total_ne_peut_pas_depasser_la_somme_des_poids(self):
        cfg = self.strategy.config
        total = (cfg.w_trend + cfg.w_momentum + cfg.w_candles + cfg.w_chart
                 + cfg.w_divergence + cfg.w_zones + cfg.w_volume + cfg.w_macro + cfg.w_news)
        ev = self.evaluate()
        self.assertLessEqual(abs(ev.score), total + 1e-9)
        # Le seuil doit rester atteignable, sinon aucun trade ne passe jamais.
        self.assertLess(cfg.min_score, total)


class TestMultiActifs(Base):
    def test_chaque_instrument_est_evalue_independamment(self):
        inds = self.indicators()
        price = inds["M5"].last.close
        for symbol in ("XAUUSD", "EURUSD", "BTCUSD"):
            inst = self.universe.get(symbol)
            # Le spread typique de l'instrument sert d'echelle realiste.
            tick = Tick(self.now, price - inst.typical_spread / 2, price + inst.typical_spread / 2)
            ev = self.strategy.evaluate(inst, inds, tick, now=self.now)
            self.assertEqual(ev.symbol, symbol)
            self.assertEqual(ev.asset_class, inst.asset_class)

    def test_la_crypto_reste_ouverte_le_week_end(self):
        samedi = time.mktime(time.strptime("2026-08-22 14:00:00", "%Y-%m-%d %H:%M:%S"))
        btc = self.universe.get("BTCUSD")
        inds = self.indicators()
        price = inds["M5"].last.close
        ev = self.strategy.evaluate(btc, inds, Tick(samedi, price - 4, price + 4), now=samedi)
        self.assertTrue(self.gate(ev, "marche_ouvert").passed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
