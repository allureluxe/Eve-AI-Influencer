"""Tests des indicateurs : on verifie les valeurs, pas seulement l'absence d'erreur."""
from __future__ import annotations

import unittest

from helpers import trending_indicators, zigzag_indicators

from gold_bot.core import Candle
from gold_bot.datasources.base import resample
from gold_bot.indicators import (
    ADX, ATR, EMA, MACD, RSI, SMA, Bollinger, Donchian, HurstRegime,
    IndicatorSet, StdDev, Supertrend, SwingDetector, correlation,
)


class TestMoyennes(unittest.TestCase):
    def test_sma_valeur_exacte(self):
        sma = SMA(3)
        for x in (1, 2, 3):
            sma.update(x)
        self.assertAlmostEqual(sma.value, 2.0)
        sma.update(6)                     # fenetre = 2,3,6
        self.assertAlmostEqual(sma.value, 11 / 3)

    def test_sma_pas_prete_avant_la_periode(self):
        sma = SMA(5)
        for x in range(4):
            self.assertIsNone(sma.update(x))

    def test_ema_amorcee_par_une_sma(self):
        ema = EMA(3)
        for x in (1, 2, 3):
            ema.update(x)
        self.assertAlmostEqual(ema.value, 2.0)     # amorce = SMA(3)
        ema.update(4)
        self.assertAlmostEqual(ema.value, 2.0 + 0.5 * (4 - 2.0))   # k = 2/(3+1)

    def test_ecart_type_de_population(self):
        sd = StdDev(4)
        for x in (2, 4, 4, 6):
            sd.update(x)
        self.assertAlmostEqual(sd.mean, 4.0)
        self.assertAlmostEqual(sd.value, (((2 - 4) ** 2 + 0 + 0 + (6 - 4) ** 2) / 4) ** 0.5)


class TestOscillateurs(unittest.TestCase):
    def test_rsi_vaut_100_en_hausse_continue(self):
        rsi = RSI(14)
        for i in range(40):
            rsi.update(100 + i)
        self.assertAlmostEqual(rsi.value, 100.0, places=6)

    def test_rsi_proche_de_zero_en_baisse_continue(self):
        rsi = RSI(14)
        for i in range(40):
            rsi.update(100 - i)
        self.assertLess(rsi.value, 1.0)

    def test_rsi_autour_de_50_en_oscillation(self):
        rsi = RSI(14)
        for i in range(80):
            rsi.update(100 + (1 if i % 2 else -1))
        self.assertTrue(40 <= rsi.value <= 60, f"RSI={rsi.value}")


class TestVolatilite(unittest.TestCase):
    def test_atr_sur_amplitude_constante(self):
        atr = ATR(3)
        for i in range(10):
            atr.update(Candle(i, 100, 102, 98, 100, 0))   # amplitude 4, sans gap
        self.assertAlmostEqual(atr.value, 4.0, places=6)

    def test_atr_prend_en_compte_les_gaps(self):
        atr = ATR(2)
        atr.update(Candle(0, 100, 101, 99, 100, 0))
        atr.update(Candle(1, 110, 111, 109, 110, 0))      # gap de 9 par rapport a 100
        self.assertGreater(atr.value, 2.0)

    def test_bandes_de_bollinger_encadrent_la_moyenne(self):
        bb = Bollinger(5, 2.0)
        for x in (10, 11, 12, 11, 10, 12, 13):
            bb.update(x)
        self.assertLess(bb.lower, bb.middle)
        self.assertLess(bb.middle, bb.upper)
        self.assertGreater(bb.width, 0)


class TestTendance(unittest.TestCase):
    def test_adx_eleve_en_tendance_franche(self):
        adx = ADX(14)
        for i in range(60):
            adx.update(Candle(i, 100 + i, 101 + i, 99.5 + i, 100.8 + i, 0))
        self.assertGreater(adx.value, 25.0)
        self.assertGreater(adx.plus_di, adx.minus_di)

    def test_supertrend_suit_la_direction(self):
        st = Supertrend(10, 3.0)
        for i in range(80):
            st.update(Candle(i, 100 + i, 101 + i, 99 + i, 100.5 + i, 0))
        self.assertEqual(st.direction, 1)

    def test_donchian_exclut_la_bougie_courante(self):
        d = Donchian(5)
        for i, high in enumerate((10, 12, 11, 13, 9, 20)):
            d.update(Candle(i, 10, high, 5, 10, 0))
        upper, _ = d.exclude_last()
        self.assertEqual(d.upper, 20)          # avec la derniere
        self.assertEqual(upper, 13)            # sans la derniere


class TestStructure(unittest.TestCase):
    def test_detection_des_swings(self):
        sw = SwingDetector(left=2, right=2)
        highs = [10, 11, 15, 11, 10, 9, 8, 12, 8, 7]
        for i, h in enumerate(highs):
            sw.update(Candle(i, h, h, h - 2, h, 0))
        self.assertIn(15, sw.swing_highs)

    def test_structure_haussiere(self):
        # Sommets et creux ascendants : structure haussiere au sens de Dow.
        ind = zigzag_indicators(1)
        self.assertEqual(ind.swings.structure(), "bullish")
        self.assertEqual(ind.trend_bias(), "bullish")

    def test_structure_baissiere(self):
        ind = zigzag_indicators(-1)
        self.assertEqual(ind.swings.structure(), "bearish")
        self.assertEqual(ind.trend_bias(), "bearish")

    def test_une_droite_parfaite_n_a_pas_de_structure(self):
        # Sans repli, aucun pivot n'existe : le detecteur doit repondre
        # "range" plutot que d'inventer des swings.
        ind = trending_indicators(1)
        self.assertEqual(ind.swings.structure(), "range")


class TestRegime(unittest.TestCase):
    def test_hurst_detecte_des_rendements_persistants(self):
        # L'exposant de Hurst mesure la PERSISTANCE DES RENDEMENTS, pas la
        # pente du prix : une droite bruitee a des rendements independants
        # une fois la derive retiree, donc H proche de 0.5. On simule ici un
        # vrai processus persistant (chaque variation prolonge la precedente).
        import random
        rng = random.Random(11)
        h = HurstRegime(96)
        price, ret = 100.0, 0.0
        for _ in range(300):
            ret = 0.75 * ret + rng.gauss(0, 0.3)
            price += ret
            h.update(price)
        self.assertIsNotNone(h.value)
        self.assertGreater(h.value, 0.55)
        self.assertEqual(h.regime, "trend")

    def test_hurst_neutre_sur_une_derive_reguliere(self):
        # Cas important a connaitre : une hausse reguliere n'est PAS
        # "persistante" au sens de Hurst. Le filtre de regime ne doit donc
        # jamais servir seul a valider une tendance.
        import random
        rng = random.Random(5)
        h = HurstRegime(96)
        for i in range(300):
            h.update(100 + i * 0.5 + rng.gauss(0, 0.3))
        self.assertNotEqual(h.regime, "trend")

    def test_serie_sans_variance_reste_indeterminee(self):
        # Increments strictement constants : le rapport R/S n'est pas
        # calculable. Mieux vaut "unknown" qu'un regime invente.
        h = HurstRegime(96)
        for i in range(120):
            h.update(100 + i * 0.5)
        self.assertEqual(h.regime, "unknown")

    def test_hurst_detecte_le_retour_a_la_moyenne(self):
        h = HurstRegime(96)
        for i in range(200):
            h.update(100 + (2 if i % 2 else -2))
        self.assertEqual(h.regime, "mean_revert")


class TestCorrelation(unittest.TestCase):
    def test_correlation_parfaite(self):
        a = [1, 2, 3, 4, 5]
        self.assertAlmostEqual(correlation(a, [2, 4, 6, 8, 10]), 1.0, places=6)

    def test_correlation_inverse(self):
        self.assertAlmostEqual(correlation([1, 2, 3, 4], [4, 3, 2, 1]), -1.0, places=6)

    def test_serie_constante_donne_zero(self):
        self.assertEqual(correlation([1, 2, 3], [5, 5, 5]), 0.0)


class TestAgregation(unittest.TestCase):
    def test_agregation_m1_vers_m5(self):
        cs = [Candle(i * 60, 100 + i, 105 + i, 95 + i, 101 + i, 10) for i in range(10)]
        out = resample(cs, "M1", "M5")
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0].open, 100)         # ouverture de la premiere
        self.assertEqual(out[0].close, 105)        # cloture de la cinquieme
        self.assertEqual(out[0].high, 109)         # plus haut du groupe
        self.assertEqual(out[0].low, 95)           # plus bas du groupe
        self.assertEqual(out[0].volume, 50)

    def test_agregation_impossible_vers_le_bas(self):
        with self.assertRaises(ValueError):
            resample([], "M5", "M1")


class TestJeuComplet(unittest.TestCase):
    def test_tous_les_indicateurs_prets_apres_amorcage(self):
        ind = trending_indicators(1, bars=200)
        self.assertTrue(ind.ready)
        for name in ("stoch", "cci", "willr", "mfi", "keltner", "supertrend", "ichimoku"):
            self.assertTrue(getattr(ind, name).ready, f"{name} non pret")

    def test_le_percentile_atr_reste_borne(self):
        ind = trending_indicators(1, bars=200)
        self.assertTrue(0.0 <= ind.atr_percentile() <= 1.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
