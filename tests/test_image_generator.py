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
