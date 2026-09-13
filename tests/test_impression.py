"""L'impression est un confort. Elle ne doit JAMAIS bloquer le rapport.

C'est la seule chose qui compte vraiment ici : une imprimante eteinte,
un reseau capricieux, une adresse mal saisie ou une configuration
absente ne doivent pas empecher le rapport d'arriver sur Telegram.

Le reste — la conversion en PDF, l'envoi — se verifie a la main avec
une vraie imprimante. Ces tests verrouillent le comportement en cas
d'echec, parce que c'est celui qu'on ne pense jamais a essayer.
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from gold_bot.impression import (ImpressionIndisponible, envoyer_a_l_imprimante,
                                 imprimer, nettoyer)


class TestRienNEstConfigure(unittest.TestCase):

    def test_sans_adresse_d_imprimante_on_se_tait(self):
        # Ni erreur, ni message : la plupart des utilisateurs n'ont pas
        # d'imprimante branchee, et un avertissement a chaque rapport
        # serait du bruit.
        with mock.patch.dict(os.environ, {"IMPRIMANTE_EMAIL": ""}, clear=False):
            ok, message = imprimer(Path("/inexistant.html"))
        self.assertFalse(ok)
        self.assertEqual(message, "")

    def test_adresse_sans_identifiants_smtp_est_refusee_proprement(self):
        with mock.patch.dict(os.environ, {
                "IMPRIMANTE_EMAIL": "truc@print.epsonconnect.com",
                "SMTP_UTILISATEUR": "", "SMTP_MOTDEPASSE": ""}, clear=False):
            with self.assertRaises(ImpressionIndisponible) as ctx:
                envoyer_a_l_imprimante(Path("/inexistant.pdf"))
        self.assertIn("SMTP", str(ctx.exception))


class TestUnEchecNeRemonteJamais(unittest.TestCase):
    """Le point le plus important du module."""

    def test_un_pdf_impossible_rend_un_message_pas_une_exception(self):
        with mock.patch.dict(os.environ, {
                "IMPRIMANTE_EMAIL": "truc@print.epsonconnect.com"}, clear=False):
            # Fichier HTML inexistant : Chromium echouera.
            ok, message = imprimer(Path("/absolument/inexistant.html"))
        self.assertFalse(ok)
        self.assertIn("Impression impossible", message)

    def test_une_erreur_inattendue_est_avalee(self):
        # Une panne qu'on n'a pas prevue ne doit pas remonter jusqu'au
        # code qui envoie le rapport Telegram.
        with mock.patch.dict(os.environ, {
                "IMPRIMANTE_EMAIL": "truc@print.epsonconnect.com"}, clear=False):
            with mock.patch("gold_bot.impression.vers_pdf",
                            side_effect=RuntimeError("panne imprevue")):
                ok, message = imprimer(Path("/peu/importe.html"))
        self.assertFalse(ok)
        self.assertIn("Impression impossible", message)

    def test_un_envoi_refuse_rend_un_message_pas_une_exception(self):
        with mock.patch.dict(os.environ, {
                "IMPRIMANTE_EMAIL": "truc@print.epsonconnect.com",
                "SMTP_UTILISATEUR": "moi@exemple.fr",
                "SMTP_MOTDEPASSE": "secret"}, clear=False):
            with mock.patch("gold_bot.impression.vers_pdf",
                            return_value=Path("/faux.pdf")), \
                 mock.patch("gold_bot.impression.envoyer_a_l_imprimante",
                            side_effect=ImpressionIndisponible("hors ligne")):
                ok, message = imprimer(Path("/peu/importe.html"))
        self.assertFalse(ok)
        self.assertIn("hors ligne", message)


class TestLeMenage(unittest.TestCase):

    def test_les_vieux_pdf_sont_effaces(self):
        # Sans menage, le disque du VPS se remplit en silence : un
        # rapport pese ~400 Ko et l'operateur en demande plusieurs par
        # jour.
        import time
        with TemporaryDirectory() as tmp:
            dossier = Path(tmp)
            vieux = dossier / "rapport-20250101-000000.pdf"
            recent = dossier / "rapport-20260913-000000.pdf"
            vieux.write_bytes(b"x")
            recent.write_bytes(b"x")
            os.utime(vieux, (time.time() - 60 * 86400,) * 2)

            with mock.patch("gold_bot.impression.DOSSIER", dossier):
                self.assertEqual(nettoyer(jours=30), 1)
            self.assertFalse(vieux.exists())
            self.assertTrue(recent.exists(), "un PDF recent a ete efface")

    def test_un_dossier_absent_ne_casse_rien(self):
        with mock.patch("gold_bot.impression.DOSSIER",
                        Path("/inexistant/nulle/part")):
            self.assertEqual(nettoyer(), 0)


if __name__ == "__main__":
    unittest.main()
