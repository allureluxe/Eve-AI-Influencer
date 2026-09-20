import pytest
import unittest

from config import IMAGE_NEGATIVE_PROMPT, IMAGE_PROMPTS, IMAGE_SEED
from image_generator import ImageGenerator


class TestImageGeneratorConfig(unittest.TestCase):
    def test_default_seed_and_negative_prompt_for_eve(self):
        self.assertEqual(IMAGE_SEED, 774921)
        self.assertIn("cgi", IMAGE_NEGATIVE_PROMPT)
        self.assertIn("smooth plastic skin", IMAGE_NEGATIVE_PROMPT)

    def test_all_default_prompts_push_photorealism(self):
        self.assertEqual(len(IMAGE_PROMPTS), 6)
        for prompt in IMAGE_PROMPTS:
            self.assertTrue(prompt.startswith("photo,"))
            self.assertIn("iPhone 15 Pro", prompt)
            self.assertIn("visible skin pores", prompt)

    def test_stability_body_includes_seed_and_negative_prompt(self):
        generator = ImageGenerator()
        body = generator._stability_body("photo, test", "cartoon, text")
        self.assertEqual(body["seed"], 774921)
        self.assertEqual(body["height"], 1024)
        self.assertEqual(body["width"], 1024)
        self.assertIn({"text": "photo, test", "weight": 1}, body["text_prompts"])
        self.assertIn({"text": "cartoon, text", "weight": -1}, body["text_prompts"])

    def test_replicate_body_uses_flux_style_controls(self):
        generator = ImageGenerator()
        body = generator._replicate_body("photo, test", "cartoon")
        self.assertEqual(body["input"]["seed"], 774921)
        self.assertEqual(body["input"]["guidance_scale"], 3.5)
        self.assertEqual(body["input"]["num_inference_steps"], 36)
        self.assertEqual(body["input"]["width"], 1024)
        self.assertEqual(body["input"]["height"], 1024)
        self.assertEqual(body["input"]["negative_prompt"], "cartoon")


class TestLeRepliSExecuteSurTousLesChemins:
    """Une panne d'un fournisseur doit passer au SUIVANT, pas tout casser.

    Le 20 septembre, Cloudflare a rendu « HTTP Error 408: Request
    Timeout » et l'erreur est remontee jusqu'a l'appelant alors que deux
    autres fournisseurs etaient configures a cote. `generer()` n'attrape
    que `ErreurMoteur` ; `_requeter_multipart` -- seule de toutes les
    methodes -- laissait filer l'`HTTPError` brute d'urllib.

    Le repli existait, il etait documente, il etait teste sur le chemin
    JSON. Il ne s'executait pas sur le chemin multipart. C'est le meme
    piege que le pyramidage et la pause du rejeu : un garde-fou se
    verifie sur CHAQUE chemin.
    """

    def test_une_erreur_http_devient_une_erreur_moteur(self, monkeypatch):
        import urllib.error
        from luna.moteurs import ErreurMoteur, GenerateurImages

        def tombe(*a, **k):
            raise urllib.error.HTTPError(
                "https://exemple", 408, "Request Timeout", {}, None)

        monkeypatch.setattr("urllib.request.urlopen", tombe)
        with pytest.raises(ErreurMoteur):
            GenerateurImages._requeter_multipart(
                "https://exemple", "cle", {"prompt": "x"})

    def test_une_panne_reseau_devient_une_erreur_moteur(self, monkeypatch):
        import urllib.error
        from luna.moteurs import ErreurMoteur, GenerateurImages

        def tombe(*a, **k):
            raise urllib.error.URLError("connexion refusee")

        monkeypatch.setattr("urllib.request.urlopen", tombe)
        with pytest.raises(ErreurMoteur):
            GenerateurImages._requeter_multipart(
                "https://exemple", "cle", {"prompt": "x"})
