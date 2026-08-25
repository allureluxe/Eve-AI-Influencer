"""Tests du defi hebdomadaire : paliers, plafonnement, modulation du risque.

Le point le plus important verifie ici : un retard sur l'objectif ne doit
JAMAIS faire monter le risque. C'est la garantie qui empeche le systeme de
se transformer en martingale.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timezone

from helpers import *  # noqa: F401,F403

from gold_bot.objectives import ObjectiveConfig, ObjectiveTracker, week_key


def tracker(**kw) -> ObjectiveTracker:
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    os.unlink(path)
    return ObjectiveTracker(ObjectiveConfig(**kw), state_file=path)


class TestPaliers(unittest.TestCase):
    def test_progression_geometrique(self):
        t = tracker(base_target=100.0, escalation=1.5, max_weekly_target_pct=0.0)
        self.assertEqual(t.raw_target(1), 100.0)
        self.assertEqual(t.raw_target(2), 150.0)
        self.assertEqual(t.raw_target(3), 225.0)

    def test_progression_lineaire(self):
        t = tracker(base_target=100.0, escalation_mode="linear", max_weekly_target_pct=0.0)
        self.assertEqual(t.raw_target(1), 100.0)
        self.assertEqual(t.raw_target(3), 300.0)

    def test_l_objectif_est_plafonne_par_le_capital(self):
        # 100 EUR sur un compte de 500 EUR = 20 % par semaine : intenable.
        t = tracker(base_target=100.0, max_weekly_target_pct=8.0)
        self.assertEqual(t.target_for_level(1, equity=500.0), 40.0)
        self.assertTrue(t.is_capped(500.0))

    def test_le_capital_requis_est_annonce(self):
        t = tracker(base_target=100.0, max_weekly_target_pct=8.0)
        self.assertEqual(t.equity_needed(1), 1250.0)     # 100 / 8 %

    def test_plus_de_plafond_quand_le_capital_suffit(self):
        t = tracker(base_target=100.0, max_weekly_target_pct=8.0)
        self.assertEqual(t.target_for_level(1, equity=5000.0), 100.0)
        self.assertFalse(t.is_capped(5000.0))


class TestCycleHebdomadaire(unittest.TestCase):
    def test_le_palier_monte_apres_un_objectif_atteint(self):
        t = tracker(base_target=100.0, max_weekly_target_pct=0.0)
        t.state.week_start_equity = 5000.0
        t.record_trade(120.0)
        t.state.current_week = "2000-W01"          # force un changement de semaine
        t.sync(5120.0)
        self.assertEqual(t.state.level, 2)

    def test_le_palier_est_maintenu_si_l_objectif_est_manque(self):
        t = tracker(base_target=100.0, max_weekly_target_pct=0.0)
        t.state.week_start_equity = 5000.0
        t.record_trade(40.0)
        t.state.current_week = "2000-W01"
        t.sync(5040.0)
        self.assertEqual(t.state.level, 1)

    def test_retrogradation_apres_une_semaine_perdante(self):
        t = tracker(base_target=100.0, max_weekly_target_pct=0.0)
        t.state.level = 3
        t.state.week_start_equity = 5000.0
        t.record_trade(-80.0)
        t.state.current_week = "2000-W01"
        t.sync(4920.0)
        self.assertEqual(t.state.level, 2)

    def test_les_compteurs_sont_remis_a_zero(self):
        t = tracker(base_target=100.0, max_weekly_target_pct=0.0)
        t.state.week_start_equity = 5000.0
        t.record_trade(50.0)
        t.state.current_week = "2000-W01"
        t.sync(5050.0)
        self.assertEqual(t.state.realized_this_week, 0.0)
        self.assertEqual(t.state.trades_this_week, 0)
        self.assertEqual(len(t.state.history), 1)

    def test_l_historique_conserve_le_resultat(self):
        t = tracker(base_target=100.0, max_weekly_target_pct=0.0)
        t.state.week_start_equity = 5000.0
        t.record_trade(130.0)
        t.state.current_week = "2000-W01"
        t.sync(5130.0)
        rec = t.state.history[-1]
        self.assertEqual(rec["realized"], 130.0)
        self.assertTrue(rec["achieved"])


class TestModulationDuRisque(unittest.TestCase):
    """La regle qui protege le compte."""

    def test_le_retard_ne_monte_jamais_le_risque(self):
        t = tracker(base_target=100.0, max_weekly_target_pct=0.0)
        t.state.week_start_equity = 5000.0
        # Vendredi : la cadence attendue est proche de 100 %, rien de realise.
        vendredi = datetime(2026, 8, 21, 12, tzinfo=timezone.utc).timestamp()
        mult, why = t.risk_multiplier(vendredi)
        self.assertLessEqual(mult, 1.0, f"le risque a augmente pour rattraper : {why}")
        self.assertIn("selectivite", why)

    def test_le_retard_durcit_le_seuil_de_validation(self):
        t = tracker(base_target=100.0, max_weekly_target_pct=0.0)
        t.state.week_start_equity = 5000.0
        vendredi = datetime(2026, 8, 21, 12, tzinfo=timezone.utc).timestamp()
        self.assertGreater(t.score_threshold_bonus(vendredi), 0.0)

    def test_une_semaine_negative_reduit_le_risque(self):
        t = tracker(base_target=100.0, max_weekly_target_pct=0.0)
        t.state.week_start_equity = 5000.0
        t.record_trade(-60.0)
        mult, why = t.risk_multiplier()
        self.assertLess(mult, 1.0)
        self.assertIn("negative", why)

    def test_objectif_atteint_declenche_la_preservation(self):
        t = tracker(base_target=100.0, max_weekly_target_pct=0.0, protect_multiplier=0.4)
        t.state.week_start_equity = 5000.0
        t.record_trade(110.0)
        mult, why = t.risk_multiplier()
        self.assertAlmostEqual(mult, 0.4)
        self.assertIn("preservation", why)
        self.assertGreater(t.score_threshold_bonus(), 0.1)

    def test_arret_quand_l_objectif_est_largement_depasse(self):
        t = tracker(base_target=100.0, max_weekly_target_pct=0.0)
        t.state.week_start_equity = 5000.0
        t.record_trade(200.0)                     # 200 % de l'objectif
        stop, why = t.should_stop_trading()
        self.assertTrue(stop)
        self.assertIn("depasse", why)

    def test_le_multiplicateur_reste_dans_sa_bande(self):
        t = tracker(base_target=100.0, max_weekly_target_pct=0.0,
                    min_multiplier=0.4, max_multiplier=1.3)
        t.state.week_start_equity = 5000.0
        for profit in (-500.0, -100.0, -10.0, 0.0, 10.0, 100.0, 1000.0):
            t.state.realized_this_week = profit
            t.state.achieved_this_week = profit >= t.target
            mult, _ = t.risk_multiplier()
            self.assertGreaterEqual(mult, 0.4)
            self.assertLessEqual(mult, 1.3)


class TestPersistance(unittest.TestCase):
    def test_l_etat_survit_a_un_redemarrage(self):
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        try:
            t1 = ObjectiveTracker(ObjectiveConfig(base_target=100.0), state_file=path)
            t1.state.level = 4
            t1.state.week_start_equity = 5000.0
            t1.record_trade(75.0)

            t2 = ObjectiveTracker(ObjectiveConfig(base_target=100.0), state_file=path)
            self.assertEqual(t2.state.level, 4)
            self.assertEqual(t2.state.realized_this_week, 75.0)
        finally:
            os.path.exists(path) and os.unlink(path)


class TestSemaineIso(unittest.TestCase):
    def test_format_de_la_cle(self):
        ts = datetime(2026, 8, 21, 12, tzinfo=timezone.utc).timestamp()
        self.assertEqual(week_key(ts), "2026-W34")

    def test_deux_jours_de_la_meme_semaine(self):
        lundi = datetime(2026, 8, 17, 8, tzinfo=timezone.utc).timestamp()
        vendredi = datetime(2026, 8, 21, 20, tzinfo=timezone.utc).timestamp()
        self.assertEqual(week_key(lundi), week_key(vendredi))


if __name__ == "__main__":
    unittest.main(verbosity=2)
