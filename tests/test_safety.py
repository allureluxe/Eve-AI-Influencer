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


def test_normal_lifestyle_prompt_passes(persona):
    prompt = persona.image_prompt("having morning coffee on a sunlit terrace")
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


def test_lifestyle_never_attributed_to_trading(persona):
    for texte in [
        "Nouvelle voiture, tout ça grâce à mon robot de trading",
        "Mon système m'a payé ce voyage",
        "Je gagne 8000 par mois",
        "Ma vie a changé grâce à ce système",
        "Thanks to my bot I could afford this",
    ]:
        _, res = review_post(persona, caption=texte)
        assert not res.ok, texte


def test_financial_solicitation_is_blocked(persona):
    for texte in [
        "Rejoins mon canal Telegram privé",
        "DM pour recevoir le robot",
        "Places limitées, capital garanti",
        "Copie mes trades en direct",
    ]:
        _, res = review_post(persona, caption=texte)
        assert not res.ok, texte


def test_performance_figures_need_risk_and_framing(persona):
    _, nu = review_post(persona, caption="+12,4 % de rendement ce semestre 🚀")
    assert not nu.ok

    _, encadre = review_post(
        persona,
        caption="+12,4 % sur la période, drawdown maximal 8,1 %. "
                "Résultats passés, ce n'est pas un conseil en investissement.")
    assert encadre.ok, encadre.report()


def test_ordinary_lifestyle_caption_passes(persona):
    _, res = review_post(persona, caption="Comment reconnaître un bon vêtement en trente secondes 🤍",
                         pillar="fashion")
    assert res.ok, res.report()
