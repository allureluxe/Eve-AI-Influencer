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

from luna.alluxe_v2 import Resultat, creer
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


class TestVoixAvecRepli(unittest.TestCase):
    """15 sept. : meme discipline de repli que pour les images et le texte."""

    def test_bascule_sur_gtts_si_edge_tts_echoue(self):
        from luna.alluxe_v2 import _generer_voix
        with patch("luna.alluxe_v2._voix_edge", side_effect=RuntimeError("reseau")):
            with patch("luna.alluxe_v2._voix_gtts") as gtts_factice:
                def _ecrire(texte, chemin):
                    with open(chemin, "wb") as f:
                        f.write(b"voix-gtts")
                gtts_factice.side_effect = _ecrire
                chemin = tempfile.mktemp(suffix=".mp3")
                self.addCleanup(lambda: os.path.exists(chemin) and os.remove(chemin))
                _generer_voix("Coucou 😊", chemin)
        with open(chemin, "rb") as f:
            self.assertEqual(f.read(), b"voix-gtts")

    def test_leve_une_erreur_si_les_deux_echouent(self):
        from luna.alluxe_v2 import _generer_voix
        with patch("luna.alluxe_v2._voix_edge", side_effect=RuntimeError("reseau")):
            with patch("luna.alluxe_v2._voix_gtts", side_effect=RuntimeError("aussi en panne")):
                with self.assertRaises(RuntimeError):
                    _generer_voix("Coucou 😊", tempfile.mktemp(suffix=".mp3"))


class TestAlluxe(unittest.TestCase):
    def setUp(self):
        self.dossier = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dossier, ignore_errors=True)

    def test_script_photo_et_voix_bout_en_bout_sans_ffmpeg(self):
        with patch("luna.alluxe_v2._generer_voix") as voix_factice:
            def _ecrire(texte, chemin):
                with open(chemin, "wb") as f:
                    f.write(b"fausse-voix")
            voix_factice.side_effect = _ecrire
            with patch("luna.alluxe_v2._assembler_video") as video_factice:
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
        with patch("luna.alluxe_v2._generer_voix") as voix_factice:
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

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),
                         "ffmpeg/ffprobe non installes sur cette machine")
    def test_la_video_dure_aussi_longtemps_que_l_audio_et_zoome_vraiment(self):
        """15 sept. : zoompan avec d=1 et -shortest ne bougeait pas a
        l'oeil -- verifie ici que la video assemblee dure bien la longueur
        de l'audio (pas 1 frame figee) et que l'image change entre le debut
        et la fin (le zoom progresse reellement)."""
        import subprocess
        from luna.alluxe_v2 import _assembler_video, _duree_audio

        image = os.path.join(self.dossier, "photo.png")
        audio = os.path.join(self.dossier, "voix.mp3")
        video = os.path.join(self.dossier, "video.mp4")
        # Image de test generee localement (pas de reseau) : un mire ffmpeg.
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc=size=640x960:rate=1",
                         "-frames:v", "1", image], check=True, capture_output=True)
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
                         "-t", "3", audio], check=True, capture_output=True)

        _assembler_video(image, audio, video)
        self.assertTrue(os.path.exists(video))

        duree_video = float(subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", video],
            capture_output=True, text=True, check=True).stdout.strip())
        self.assertAlmostEqual(duree_video, _duree_audio(audio), delta=0.3)

        debut = os.path.join(self.dossier, "debut.jpg")
        fin = os.path.join(self.dossier, "fin.jpg")
        subprocess.run(["ffmpeg", "-y", "-ss", "0.1", "-i", video, "-frames:v", "1", debut],
                       check=True, capture_output=True)
        subprocess.run(["ffmpeg", "-y", "-ss", "2.5", "-i", video, "-frames:v", "1", fin],
                       check=True, capture_output=True)
        # Le zoom progresse : les octets de la 1ere et de la derniere image
        # ne peuvent pas etre identiques si le cadrage a vraiment change.
        with open(debut, "rb") as f1, open(fin, "rb") as f2:
            self.assertNotEqual(f1.read(), f2.read())

    def test_le_prompt_image_porte_l_ancre_et_la_scene(self):
        images = GenerateurImagesFactice()
        with patch("luna.alluxe_v2._generer_voix"), patch("luna.alluxe_v2._assembler_video"):
            creer("un post", dossier_racine=self.dossier,
                  moteur=MoteurFactice(), images=images)
        from luna.persona import LUNA
        self.assertEqual(len(images.appels), 1)
        self.assertIn(LUNA.apparence.ancre, images.appels[0])
        self.assertIn("a woman smiling", images.appels[0])


if __name__ == "__main__":
    unittest.main()
