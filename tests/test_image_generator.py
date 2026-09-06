from config import IMAGE_NEGATIVE_PROMPT, IMAGE_PROMPTS, IMAGE_SEED
from image_generator import ImageGenerator


def test_default_seed_and_negative_prompt_for_eve():
    assert IMAGE_SEED == 774921
    assert "cgi" in IMAGE_NEGATIVE_PROMPT
    assert "smooth plastic skin" in IMAGE_NEGATIVE_PROMPT


def test_all_default_prompts_push_photorealism():
    assert len(IMAGE_PROMPTS) == 6
    for prompt in IMAGE_PROMPTS:
        assert prompt.startswith("photo,")
        assert "iPhone 15 Pro" in prompt
        assert "visible skin pores" in prompt


def test_stability_body_includes_seed_and_negative_prompt():
    generator = ImageGenerator()
    body = generator._stability_body("photo, test", "cartoon, text")
    assert body["seed"] == 774921
    assert body["height"] == 1024
    assert body["width"] == 1024
    assert {"text": "photo, test", "weight": 1} in body["text_prompts"]
    assert {"text": "cartoon, text", "weight": -1} in body["text_prompts"]


def test_replicate_body_uses_flux_style_controls():
    generator = ImageGenerator()
    body = generator._replicate_body("photo, test", "cartoon")
    assert body["input"]["seed"] == 774921
    assert body["input"]["guidance_scale"] == 3.5
    assert body["input"]["num_inference_steps"] == 36
    assert body["input"]["width"] == 1024
    assert body["input"]["height"] == 1024
    assert body["input"]["negative_prompt"] == "cartoon"
