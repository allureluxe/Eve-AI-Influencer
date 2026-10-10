"""La file de publication vers l'application ne doit plus jamais se figer.

10 oct. 2026 : 38 publications coincees depuis le 1er octobre derriere une
ouverture refusee en doublon (409). `rejouer` s'arretait sur elle a chaque
cycle : des clotures reelles (KAIA +1,13 EUR...) jamais affichees. Et ZK :
sa cloture ecrite sur une ligne du 2 oct., la vraie restee « ouverte ».
"""
from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from helpers import *  # noqa: F401,F403

from gold_bot.signal_publisher import (SignalPublie, SignalPublisher,
                                       SupabaseIndisponible, SupabaseRefus)


class Client:
    def __init__(self):
        self.refuser = set()     # references refusees par principe
        self.panne = False
        self.inserts, self.patchs = [], []
        self.actives: dict[tuple, list] = {}

    def inserer(self, table, ligne):
        if self.panne:
            raise SupabaseIndisponible("panne")
        if ligne.get("reference") in self.refuser:
            raise SupabaseRefus("HTTP 409 : doublon")
        self.inserts.append(ligne)

    def modifier(self, table, filtre, champs):
        if self.panne:
            raise SupabaseIndisponible("panne")
        self.patchs.append((filtre, champs))

    def existe(self, table, filtre):
        return True

    def lignes_actives(self, table, base, etage, est_demo):
        return list(self.actives.get((base, etage), []))


def _sig(ref):
    return SignalPublie(reference=ref, pair="ZK/EUR", side="buy",
                        entry_price=1.0, stop_loss=0.9)


class TestLaFileNeSeFigePlus(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.f = Path(self.tmp.name) / "file.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def test_une_tache_refusee_ne_bloque_plus_celles_qui_suivent(self):
        c = Client(); c.panne = True
        pub = SignalPublisher(client=c, fichier_file=self.f)
        pub.publier_ouverture(_sig("TUSD:1"))
        pub.publier_ouverture(_sig("KAIAUSD~5:1"))
        c.panne = False
        c.refuser.add("TUSD:1")
        self.assertEqual(pub.rejouer(), 2)
        self.assertEqual([l["reference"] for l in c.inserts], ["KAIAUSD~5:1"])
        self.assertEqual(pub.rejouer(), 0, "la tache refusee est restee en file")

    def test_un_refus_immediat_n_entre_pas_en_file(self):
        c = Client(); c.refuser.add("ZKUSD:1")
        pub = SignalPublisher(client=c, fichier_file=self.f)
        self.assertFalse(pub.publier_ouverture(_sig("ZKUSD:1")))
        self.assertFalse(self.f.exists() and self.f.read_text().strip())

    def test_une_panne_reste_en_file(self):
        c = Client(); c.panne = True
        pub = SignalPublisher(client=c, fichier_file=self.f)
        pub.publier_ouverture(_sig("A:1"))
        self.assertEqual(pub.rejouer(), 0)
        c.panne = False
        self.assertEqual(pub.rejouer(), 1)


class TestLaClotureTrouveLaLigneVraimentActive(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.f = Path(self.tmp.name) / "file.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def test_ancien_format_demande_nouveau_format_en_base(self):
        """ZK, 10 oct. : le moteur ferme « ZKUSD:1 », la ligne active est
        « ZKUSD~1791562517:1 »."""
        c = Client(); c.actives[("ZKUSD", "1")] = ["ZKUSD~1791562517:1"]
        pub = SignalPublisher(client=c, fichier_file=self.f)
        pub.publier_cloture("ZKUSD:1", "closed_sl", 1.0, -6.5, profit_eur=-2.79)
        self.assertEqual(c.patchs[-1][0], "reference=eq.ZKUSD~1791562517:1")
        self.assertEqual(c.patchs[-1][1]["profit_eur"], -2.79)

    def test_nouveau_format_demande_ancien_format_en_base(self):
        """WLFI : publiee « WLFIUSD:1 » avant la bascule, fermee en « ~ »."""
        c = Client(); c.actives[("WLFIUSD", "1")] = ["WLFIUSD:1"]
        pub = SignalPublisher(client=c, fichier_file=self.f)
        pub.publier_suivi("WLFIUSD~1791582738:1", 0.05)
        self.assertEqual(c.patchs[-1][0], "reference=eq.WLFIUSD:1")

    def test_les_fantomes_du_meme_etage_sont_annules_sans_resultat(self):
        c = Client(); c.actives[("ZKUSD", "1")] = ["ZKUSD~9:1", "ZKUSD:1"]
        pub = SignalPublisher(client=c, fichier_file=self.f)
        pub.publier_cloture("ZKUSD~9:1", "closed_sl", 1.0, -6.5, profit_eur=-2.79)
        par_ligne = {f: ch for f, ch in c.patchs}
        self.assertEqual(par_ligne["reference=eq.ZKUSD~9:1"]["profit_eur"], -2.79)
        self.assertEqual(par_ligne["reference=eq.ZKUSD:1"]["status"], "cancelled")
        self.assertEqual(par_ligne["reference=eq.ZKUSD:1"]["profit_eur"], 0.0,
                         "le benefice serait compte deux fois")

    def test_aucune_ligne_active_garde_la_reference_demandee(self):
        c = Client()
        pub = SignalPublisher(client=c, fichier_file=self.f)
        pub.publier_cloture("XUSD~3:1", "closed_tp", 1.0, 2.0)
        self.assertEqual(c.patchs[-1][0], "reference=eq.XUSD~3:1")
