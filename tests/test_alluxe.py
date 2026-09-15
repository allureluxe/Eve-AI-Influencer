"""Tests de l'agent Alluxe : script -> photo -> voix -> video.

Aucun de ces tests ne touche le reseau ni ffmpeg : moteur et generateur
d'images sont factices, et l'assemblage video est verifie separement
(commande construite) sans executer le vrai binaire.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from luna.alluxe import Resultat, creer
from luna.moteurs import ErreurMoteur, Moteur


class MoteurFactice(Moteur):
    nom = "factice"
    disponible = True

    def __init__(self, reponse: str = "LEGENDE: Coucou 😊\nSCENE: a woman smiling"):
        self.reponse = reponse

    def repondre(self, systeme: str, tours: list[dict]) -> str:
        return self.reponse


class GenerateurImagesFactice:
    disponible = True

    def __init__(self, echoue: bool = False):
        self.echoue = echoue
        self.appels: list[str] = []

    def generer(self, prompt: str, negatif: str = "", graine: int = 0,
                format: str = "portrait") -> bytes:
        self.appels.append(prompt)
        if self.echoue:
            raise ErreurMoteur("panne factice")
        return b"\x89PNG\r\n\x1a\nfausse-image"


class TestAlluxe(unittest.TestCase):
    def setUp(self):
        self.dossier = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dossier, ignore_errors=True)

    def test_script_photo_et_voix_bout_en_bout_sans_ffmpeg(self):
        with patch("luna.alluxe._generer_voix") as voix_factice:
            def _ecrire(texte, chemin):
                with open(chemin, "wb") as f:
                    f.write(b"fausse-voix")
            voix_factice.side_effect = _ecrire
            with patch("luna.alluxe._assembler_video") as video_factice:
                def _assembler(image, audio, video):
                    with open(video, "wb") as f:
                        f.write(b"fausse-video")
                video_factice.side_effect = _assembler

                resultat = creer("un post sur son week-end au ski",
                                  dossier_racine=self.dossier,
                                  moteur=MoteurFactice(),
                                  images=GenerateurImagesFactice())

        self.assertIsInstance(resultat, Resultat)
        self.assertEqual(resultat.erreurs, {})
        self.assertEqual(resultat.legende, "Coucou 😊")
        self.assertEqual(resultat.scene_prompt, "a woman smiling")
        self.assertTrue(os.path.exists(resultat.chemin_script))
        self.assertTrue(os.path.exists(resultat.chemin_image))
        self.assertTrue(os.path.exists(resultat.chemin_voix))
        self.assertTrue(os.path.exists(resultat.chemin_video))
        with open(os.path.join(resultat.dossier, "resultat.json")) as f:
            donnees = json.load(f)
        self.assertEqual(donnees["legende"], "Coucou 😊")

    def test_une_reponse_du_moteur_sans_le_bon_format_est_signalee(self):
        resultat = creer("un post quelconque", dossier_racine=self.dossier,
                          moteur=MoteurFactice(reponse="n'importe quoi"),
                          images=GenerateurImagesFactice())
        self.assertIn("script", resultat.erreurs)
        self.assertFalse(resultat.chemin_image)

    def test_une_panne_du_moteur_arrete_tout_le_reste(self):
        moteur = MoteurFactice()
        moteur.repondre = lambda systeme, tours: (_ for _ in ()).throw(
            ErreurMoteur("hors ligne"))
        resultat = creer("un post", dossier_racine=self.dossier,
                          moteur=moteur, images=GenerateurImagesFactice())
        self.assertEqual(resultat.erreurs, {"script": "hors ligne"})
        self.assertFalse(resultat.chemin_image)
        self.assertFalse(resultat.chemin_voix)

    def test_une_panne_de_generateur_d_images_n_empeche_pas_la_voix(self):
        with patch("luna.alluxe._generer_voix") as voix_factice:
            def _ecrire(texte, chemin):
                with open(chemin, "wb") as f:
                    f.write(b"fausse-voix")
            voix_factice.side_effect = _ecrire

            resultat = creer("un post", dossier_racine=self.dossier,
                              moteur=MoteurFactice(),
                              images=GenerateurImagesFactice(echoue=True))

        self.assertIn("photo", resultat.erreurs)
        self.assertFalse(resultat.chemin_image)
        self.assertTrue(os.path.exists(resultat.chemin_voix))
        # Pas de video sans image, meme si la voix a marche.
        self.assertFalse(resultat.chemin_video)

    def test_le_prompt_image_porte_l_ancre_et_la_scene(self):
        images = GenerateurImagesFactice()
        with patch("luna.alluxe._generer_voix"), patch("luna.alluxe._assembler_video"):
            creer("un post", dossier_racine=self.dossier,
                  moteur=MoteurFactice(), images=images)
        from luna.persona import LUNA
        self.assertEqual(len(images.appels), 1)
        self.assertIn(LUNA.apparence.ancre, images.appels[0])
        self.assertIn("a woman smiling", images.appels[0])


if __name__ == "__main__":
    unittest.main()
