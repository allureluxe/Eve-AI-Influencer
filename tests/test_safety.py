"""Le module de conformité est le dernier rempart : il est testé en premier."""
import pytest

from eve.persona.persona import load_persona
from eve.safety.policy import (
    PolicyError, check_persona, check_visual_prompt, ensure_disclosure, enforce, review_post,
)


@pytest.fixture(scope="module")
def persona():
    return load_persona()


def test_persona_is_adult_and_declared_ai(persona):
    assert persona.age >= 18
    assert check_persona(persona).ok


def test_sexualised_prompt_is_blocked(persona):
    for bad in ["woman in lingerie posing", "suggestive pose on a bed", "topless at the beach"]:
        assert not check_visual_prompt(bad).ok


def test_minor_coded_prompt_is_blocked():
    assert not check_visual_prompt("cute teen girl in a gym").ok


def test_normal_fitness_prompt_passes(persona):
    prompt = persona.image_prompt("demonstrating a squat with good form in a gym")
    assert check_visual_prompt(prompt).ok


def test_medical_claims_are_blocked(persona):
    _, res = review_post(persona, caption="Ce programme soigne le diabète et fait un detox complet.")
    assert not res.ok


def test_guaranteed_results_are_blocked(persona):
    _, res = review_post(persona, caption="Perdez 10 kg en 7 jours, résultats garantis !")
    assert not res.ok


def test_disclosure_is_added_automatically(persona):
    caption, fixed = ensure_disclosure("Séance du matin 💪", persona)
    assert persona.disclosure["caption_tag"] in caption
    assert fixed


def test_caption_without_disclosure_is_blocked(persona):
    _, res = review_post(persona, caption="Séance du matin 💪", autofix=False)
    assert not res.ok
    assert any("ivulgation" in b for b in res.blocking)


def test_enforce_raises_on_blocking(persona):
    _, res = review_post(persona, caption="résultats garantis en 7 jours")
    with pytest.raises(PolicyError):
        enforce(res)


def test_caption_length_limit(persona):
    _, res = review_post(persona, caption="a" * 2300)
    assert not res.ok
