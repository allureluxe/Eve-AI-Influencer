"""Le robot REEL doit se publier comme « reel », pas comme « demo ».

L'INCIDENT, 29 septembre 2026. L'operateur envoie une capture de
l'onglet Direct :

    Capital reel · 2 400,00 EUR de depart
    2 400,00 EUR
    0,00 EUR encaisses    0,00 EUR en cours
    2 400,00 EUR restants a investir

Au meme moment, chez Bitvavo : 1 012,68 EUR de liquidites et **six
positions valant 1 382 EUR** — AAVE, CRV, HBAR, LINK, MON, XLM.

LA CAUSE. L'application distingue les comptes par DEUX colonnes a la
fois, `is_demo` ET `compte`, et les demande toujours ensemble :

    .eq("is_demo", false).eq("compte", "reel")

Mais les deux colonnes ne venaient pas de la meme verite. `is_demo`
suivait le lieu d'execution (`broker == "paper"`). `compte`, lui, lisait
`GB_COMPTE_DEMO` — une variable que seules les simulations definissent.
Le robot reel retombait donc sur le defaut, « demo », et `Signal.
vers_supabase` n'envoyait meme pas la colonne « pour ne pas repeter la
valeur par defaut ».

Resultat : des lignes `is_demo = false` portant `compte = demo`. Elles
n'apparaissaient ni dans l'onglet reel (mauvais `compte`) ni dans
l'onglet demo (mauvais `is_demo`). Invisibles des deux cotes.

C'est la meme famille que la cinquieme fuite du 18 septembre : deux
champs censes dire la meme chose, poses par deux chemins differents.
"""
from __future__ import annotations

import unittest
from unittest import mock

from gold_bot.signal_publisher import SignalPublie, nom_de_compte


class TestNomDeCompte(unittest.TestCase):

    def test_le_reel_s_appelle_reel(self):
        """Meme si GB_COMPTE_DEMO traine dans l'environnement."""
        with mock.patch.dict("os.environ", {"GB_COMPTE_DEMO": "demo2"}):
            self.assertEqual(nom_de_compte(est_demo=False), "reel")

    def test_la_simulation_garde_son_nom(self):
        with mock.patch.dict("os.environ", {"GB_COMPTE_DEMO": "demo2"}):
            self.assertEqual(nom_de_compte(est_demo=True), "demo2")

    def test_une_simulation_sans_nom_s_appelle_demo(self):
        with mock.patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("GB_COMPTE_DEMO", None)
            self.assertEqual(nom_de_compte(est_demo=True), "demo")


class TestLaColonneCompteEstToujoursEnvoyee(unittest.TestCase):
    """Omettre la colonne laissait le defaut de la base decider."""

    def _signal(self, compte: str) -> dict:
        return SignalPublie(
            reference="pos-1", pair="AAVE/EUR", side="buy",
            entry_price=147.46, stop_loss=140.0, compte=compte,
        ).vers_supabase(publier=True)

    def test_le_compte_reel_part_dans_la_ligne(self):
        self.assertEqual(self._signal("reel").get("compte"), "reel")

    def test_le_compte_demo_part_AUSSI(self):
        """C'etait l'omission : « demo » etait sous-entendu, donc muet."""
        self.assertEqual(self._signal("demo").get("compte"), "demo")

    def test_demo2_part(self):
        self.assertEqual(self._signal("demo2").get("compte"), "demo2")


class TestLesDeuxColonnesSAccordent(unittest.TestCase):
    """Le verrou de fond : `is_demo` et `compte` ne doivent plus diverger."""

    def test_reel_implique_compte_reel(self):
        for est_demo, attendu in ((False, "reel"), (True, "demo")):
            with mock.patch.dict("os.environ", {}, clear=False):
                import os
                os.environ.pop("GB_COMPTE_DEMO", None)
                nom = nom_de_compte(est_demo)
            self.assertEqual(nom, attendu)
            # Un compte nomme « reel » ne doit jamais etre une simulation,
            # et reciproquement.
            self.assertEqual(nom == "reel", not est_demo)


if __name__ == "__main__":
    unittest.main()
