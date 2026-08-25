"""Tests de la lecture des bougies japonaises et de l'analyse graphique."""
from __future__ import annotations

import unittest

from helpers import pullback_setup_indicators, trending_indicators

from gold_bot import candles as K
from gold_bot.chart import (
    Level, cluster_levels, fibonacci_levels, find_divergences, find_fair_value_gaps,
    headroom, pivot_points, read_chart, round_numbers,
)
from gold_bot.core import Candle, Side

ATR = 2.0


def c(o, h, l, close, ts=0):
    return Candle(ts, o, h, l, close, 100)


class TestGeometrie(unittest.TestCase):
    def test_mesures_de_base(self):
        b = c(100, 106, 98, 104)
        self.assertEqual(b.body, 4)
        self.assertEqual(b.range, 8)
        self.assertEqual(b.upper_wick, 2)
        self.assertEqual(b.lower_wick, 2)
        self.assertTrue(b.bullish)
        self.assertAlmostEqual(b.body_ratio, 0.5)
        self.assertAlmostEqual(b.close_position, 0.75)


class TestPatternsUneBougie(unittest.TestCase):
    def test_pin_bar_haussier(self):
        hit = K.detect_pin_bar(c(100, 100.4, 96, 100.1), ATR)
        self.assertIsNotNone(hit)
        self.assertTrue(hit.bullish)

    def test_pin_bar_baissier(self):
        hit = K.detect_pin_bar(c(100, 104, 99.6, 99.9), ATR)
        self.assertIsNotNone(hit)
        self.assertFalse(hit.bullish)

    def test_bougie_trop_petite_ignoree(self):
        # Un rejet minuscule face a la volatilite du moment n'a pas de sens.
        self.assertIsNone(K.detect_pin_bar(c(100, 100.05, 99.6, 100.01), ATR))

    def test_marubozu(self):
        hit = K.detect_marubozu(c(100, 103.1, 99.95, 103), ATR)
        self.assertIsNotNone(hit)
        self.assertGreater(hit.score, 0)

    def test_doji(self):
        self.assertIsNotNone(K.detect_doji(c(100, 101, 99, 100.02), ATR))


class TestPatternsDeuxBougies(unittest.TestCase):
    def test_avalement_haussier(self):
        hit = K.detect_engulfing(c(100, 100.5, 98.5, 99), c(98.8, 101.5, 98.6, 101), ATR)
        self.assertIsNotNone(hit)
        self.assertTrue(hit.bullish)

    def test_avalement_baissier(self):
        hit = K.detect_engulfing(c(100, 101.5, 99.5, 101), c(101.2, 101.4, 98.5, 99), ATR)
        self.assertIsNotNone(hit)
        self.assertFalse(hit.bullish)

    def test_pas_d_avalement_si_le_corps_est_plus_petit(self):
        self.assertIsNone(K.detect_engulfing(c(100, 103, 97, 103), c(101, 102, 100.5, 101.5), ATR))

    def test_penetrante(self):
        hit = K.detect_piercing(c(102, 102.2, 99.5, 100), c(99.8, 101.6, 99.7, 101.4), ATR)
        self.assertIsNotNone(hit)
        self.assertTrue(hit.bullish)

    def test_inside_bar(self):
        self.assertIsNotNone(K.detect_inside_bar(c(100, 103, 98, 102), c(101, 102, 100, 101), ATR))


class TestPatternsTroisBougies(unittest.TestCase):
    def test_etoile_du_matin(self):
        hit = K.detect_star(c(103, 103.2, 100.5, 101), c(100.9, 101.2, 100.6, 101.0),
                            c(101.1, 103.5, 101, 103), ATR)
        self.assertIsNotNone(hit)
        self.assertTrue(hit.bullish)

    def test_trois_soldats_blancs(self):
        hit = K.detect_three_soldiers(c(100, 101.2, 99.9, 101), c(101, 102.2, 100.9, 102),
                                      c(102, 103.2, 101.9, 103), ATR)
        self.assertIsNotNone(hit)
        self.assertTrue(hit.bullish)


class TestAgregationPatterns(unittest.TestCase):
    def test_le_score_reste_borne(self):
        hits = K.scan([c(100, 100.5, 98.5, 99), c(98.8, 101.5, 98.6, 101)], ATR)
        self.assertLessEqual(abs(K.pattern_score(hits)), 1.0)

    def test_un_signal_franc_annule_le_blocage(self):
        # Une pin bar a petit corps est un rejet, pas une indecision : elle
        # ne doit pas etre neutralisee par la detection de doji.
        hits = K.scan([c(100, 100.4, 96, 100.1)], ATR)
        self.assertFalse(K.has_blocker(hits))

    def test_un_doji_seul_bloque(self):
        self.assertTrue(K.has_blocker(K.scan([c(100, 101, 99, 100.02)], ATR)))

    def test_retournement_contraire_detecte(self):
        hits = K.scan([c(100, 101.5, 99.5, 101), c(101.2, 101.4, 98.5, 99)], ATR)
        self.assertTrue(K.opposing_reversal(hits, bullish_position=True))
        self.assertFalse(K.opposing_reversal(hits, bullish_position=False))


class TestNiveaux(unittest.TestCase):
    def test_regroupement_des_niveaux_proches(self):
        clusters = cluster_levels([100.0, 100.2, 100.1, 105.0], tolerance=0.5)
        self.assertEqual(len(clusters), 2)
        self.assertEqual(clusters[0][1], 3)          # trois contacts

    def test_points_pivots(self):
        piv = pivot_points(110.0, 90.0, 100.0)
        self.assertAlmostEqual(piv["PP"], 100.0)
        self.assertAlmostEqual(piv["R1"], 110.0)
        self.assertAlmostEqual(piv["S1"], 90.0)

    def test_retracements_de_fibonacci(self):
        f = fibonacci_levels(100.0, 200.0, uptrend=True)
        self.assertAlmostEqual(f["retr_0.5"], 150.0)
        self.assertAlmostEqual(f["retr_0.618"], 138.2, places=1)
        self.assertAlmostEqual(f["ext_1.618"], 261.8, places=1)

    def test_chiffres_ronds(self):
        rn = round_numbers(2653.0, step=10.0, count=1)
        self.assertIn(2650.0, rn)
        self.assertIn(2660.0, rn)

    def test_un_chiffre_rond_n_est_pas_un_obstacle(self):
        # Force 0.25 : sous le seuil d'obstacle serieux.
        levels = [Level(2660.0, "resistance", 1, "round"),
                  Level(2680.0, "resistance", 3, "swing")]
        self.assertAlmostEqual(headroom(levels, 2650.0, Side.BUY), 30.0)
        self.assertAlmostEqual(headroom(levels, 2650.0, Side.BUY, min_strength=0.0), 10.0)


class TestDivergences(unittest.TestCase):
    def test_divergence_haussiere_reguliere(self):
        # Le prix fait un creux plus bas, l'oscillateur un creux plus haut.
        prix = [c(0, 0, lo, 0, i) for i, lo in enumerate(
            [10, 8, 6, 8, 10, 12, 10, 8, 4, 6, 9, 11, 12, 13])]
        osc = [50, 40, 25, 35, 45, 55, 45, 38, 32, 40, 50, 55, 58, 60]
        divs = find_divergences(prix, osc, "RSI")
        self.assertTrue(any(d.kind == "regular_bull" for d in divs), divs)

    def test_pas_de_divergence_sur_serie_courte(self):
        self.assertEqual(find_divergences([c(0, 0, 1, 0)], [50]), [])


class TestZones(unittest.TestCase):
    def test_fair_value_gap_haussier(self):
        # Bougie 3 dont le bas depasse le haut de la bougie 1.
        cs = [c(100, 101, 99, 100.5, 0), c(100.5, 105, 100.4, 104.8, 1), c(105, 106, 102, 105.5, 2)]
        zones = find_fair_value_gaps(cs, ATR)
        self.assertEqual(len(zones), 1)
        self.assertTrue(zones[0].bullish)
        self.assertTrue(zones[0].contains(101.5))


class TestLectureComplete(unittest.TestCase):
    def test_lecture_sur_un_marche_construit(self):
        ind = pullback_setup_indicators(1)
        read = read_chart(ind, round_step=10.0)
        self.assertGreater(len(read.levels), 0)
        self.assertIsNotNone(read.profile)
        self.assertLessEqual(abs(read.divergence_score()), 1.0)
        self.assertLessEqual(abs(read.pattern_score()), 1.0)

    def test_lecture_sur_historique_vide(self):
        from gold_bot.indicators import IndicatorSet
        read = read_chart(IndicatorSet(), round_step=10.0)
        self.assertEqual(read.levels, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
