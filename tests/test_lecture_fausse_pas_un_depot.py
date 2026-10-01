"""Une lecture d'equite fausse suivie de son retour n'est pas un depot.

Le 1er oct. 2026 a 23h41, serveur sature : l'equite du compte reel est
lue a ~85 EUR au lieu de ~580, puis revient. Le rebond de +495 EUR a ete
pris pour un apport et la reference est montee de 1 330 a 1 825 EUR,
bridant toutes les positions. Ces tests verrouillent la correction, et
verifient qu'un VRAI depot reste reconnu.
"""
from __future__ import annotations

import unittest

from helpers import *  # noqa: F401,F403 - insere le chemin du projet

from gold_bot.risk import RiskConfig, RiskManager

T0 = 1_790_000_000.0


class TestLectureFausse(unittest.TestCase):
    def setUp(self):
        self.rm = RiskManager(RiskConfig())
        self.rm.sync_account(580.0, 85.0, ts=T0)
        self.ref = self.rm.account.reference_equity

    def test_le_rebond_apres_une_chute_ne_touche_pas_la_reference(self):
        self.rm.sync_account(85.0, 85.0, ts=T0 + 10)
        self.rm.sync_account(580.0, 85.0, ts=T0 + 20)
        self.assertEqual(self.rm.account.reference_equity, self.ref)
        self.assertEqual(self.rm.dernier_apport, 0.0)

    def test_un_vrai_depot_reste_reconnu(self):
        self.rm.sync_account(700.0, 205.0, ts=T0 + 10)
        self.assertAlmostEqual(self.rm.account.reference_equity, self.ref + 120.0)

    def test_un_depot_apres_une_chute_ne_compte_que_le_depassement(self):
        self.rm.sync_account(85.0, 85.0, ts=T0 + 10)
        self.rm.sync_account(700.0, 205.0, ts=T0 + 20)
        self.assertAlmostEqual(self.rm.account.reference_equity, self.ref + 120.0)

    def test_une_vraie_perte_ancienne_n_empeche_plus_un_depot(self):
        self.rm.sync_account(500.0, 85.0, ts=T0 + 10)
        self.rm.sync_account(620.0, 205.0, ts=T0 + 10 + 7200)
        self.assertAlmostEqual(self.rm.account.reference_equity, self.ref + 120.0)

    def test_un_retrait_confirme_efface_la_chute(self):
        self.rm.sync_account(480.0, 85.0, ts=T0 + 10)
        self.rm.absorber_retrait(100.0)
        self.rm.sync_account(600.0, 205.0, ts=T0 + 20)
        self.assertAlmostEqual(self.rm.account.reference_equity,
                               self.ref - 100.0 + 120.0)


if __name__ == "__main__":
    unittest.main()
