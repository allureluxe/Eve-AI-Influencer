from datetime import date

import pytest

from eve.content.captions import build_hashtags, caption_for
from eve.content.planner import plan_days, summarize
from eve.content.scripts import build_piece
from eve.persona.persona import load_persona
from eve.safety.policy import check_visual_prompt, review_post


@pytest.fixture(scope="module")
def persona():
    return load_persona()


@pytest.mark.parametrize("pillar",
                         ["journal", "build", "apprendre", "quotidien", "mindset", "qa"])
def test_every_pillar_produces_a_usable_piece(persona, pillar):
    piece = build_piece(persona, day=date(2026, 1, 5), slot="07:00", pillar=pillar)
    assert len(piece.beats) >= 3
    assert 8 <= piece.duration_s <= 90, "une vidéo courte doit rester publiable"
    assert piece.hook and piece.cta
    assert all(b.shot_prompt for b in piece.beats)


def test_generation_is_deterministic(persona):
    a = build_piece(persona, day=date(2026, 1, 5), slot="07:00", pillar="build")
    b = build_piece(persona, day=date(2026, 1, 5), slot="07:00", pillar="build")
    assert a.to_json() == b.to_json()


def test_all_shot_prompts_pass_the_visual_policy(persona):
    for pillar in ["build", "apprendre", "quotidien"]:
        piece = build_piece(persona, day=date(2026, 3, 3), slot="18:00", pillar=pillar)
        for prompt in piece.shot_prompts:
            assert check_visual_prompt(prompt).ok, prompt


def test_identity_lock_present_in_every_shot(persona):
    """Le verrou d'identité garde le même visage d'une vidéo à l'autre.

    Il n'ouvre plus le prompt — le médium passe devant, sans quoi le rendu
    part en illustration — mais il ne peut jamais manquer.
    """
    from eve.persona.persona import PHOTO_STYLE

    piece = build_piece(persona, day=date(2026, 3, 3), slot="18:00", pillar="build")
    for prompt in piece.shot_prompts:
        assert prompt.startswith(PHOTO_STYLE[:30]), "le médium ouvre le prompt"
        assert persona.identity_lock[:60] in prompt


def test_platform_captions_stay_within_limits(persona):
    piece = build_piece(persona, day=date(2026, 3, 3), slot="18:00", pillar="quotidien")
    for platform in ("tiktok", "instagram"):
        caption = caption_for(piece, persona, platform)
        assert len(caption) <= 2200
        _, res = review_post(persona, caption=caption, pillar=piece.pillar)
        assert res.ok, res.report()


def test_hashtags_include_ai_disclosure(persona):
    for platform in ("tiktok", "instagram"):
        tags = build_hashtags(persona, "build", platform)
        assert any(t in persona.disclosure["hashtags"] for t in tags)
        assert len(tags) == len(set(t.lower() for t in tags))


def test_planner_respects_volume_and_avoids_repetition(persona):
    slots = plan_days(persona, date(2026, 1, 1), days=7, posts_per_day=2)
    assert len(slots) == 14
    assert len(summarize(slots)) >= 3, "le calendrier doit rester varié"
    for a, b in zip(slots, slots[1:]):
        if a.day == b.day:
            assert a.pillar != b.pillar or a.time != b.time
