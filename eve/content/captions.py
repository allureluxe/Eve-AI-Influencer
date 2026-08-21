"""Hashtags et mise en forme des légendes par plateforme."""
from __future__ import annotations

import random

from eve.content.scripts import ContentPiece
from eve.persona.persona import Persona

# Un mélange 3 couches : niche (peu de volume, forte conversion),
# moyen (découverte) et large (portée). Le tout reste crédible.
HASHTAGS = {
    "niche": {
        "form_check": ["#techniquemusculation", "#formcheck", "#debutantemusculation", "#salledesport"],
        "quick_workout": ["#seanceexpress", "#workoutmaison", "#homeworkout", "#15minworkout"],
        "nutrition": ["#nutritionsimple", "#proteines", "#mealprepfacile", "#assietteequilibree"],
        "motivation": ["#motivationsport", "#disciplinesport", "#routinesportive"],
        "lifestyle": ["#morningroutine", "#floridalife", "#gymgirl"],
        "qa": ["#questionsport", "#coachsportif", "#conseilsport"],
    },
    "medium": ["#fitnessfeminin", "#musculationfemme", "#remiseenforme", "#sportsante",
               "#fitgirlfrance", "#objectifforme", "#fitnessmotivationfr"],
    "broad": ["#fitness", "#workout", "#gym", "#fitgirl", "#health", "#training"],
}

MAX_IG = 15
MAX_TIKTOK = 6


def build_hashtags(persona: Persona, pillar: str, platform: str = "instagram",
                   rng: random.Random | None = None) -> list[str]:
    rng = rng or random
    niche = HASHTAGS["niche"].get(pillar, HASHTAGS["niche"]["motivation"])
    disclosure = persona.disclosure["hashtags"]

    if platform == "tiktok":
        tags = disclosure[:1] + rng.sample(niche, min(2, len(niche))) + rng.sample(HASHTAGS["broad"], 2)
        return _dedupe(tags)[:MAX_TIKTOK]

    tags = (disclosure
            + rng.sample(niche, min(3, len(niche)))
            + rng.sample(HASHTAGS["medium"], 5)
            + rng.sample(HASHTAGS["broad"], 4))
    return _dedupe(tags)[:MAX_IG]


def _dedupe(tags: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for t in tags:
        k = t.lower()
        if k not in seen:
            seen.add(k)
            out.append(t)
    return out


def caption_for(piece: ContentPiece, persona: Persona, platform: str,
                monetization_line: str = "") -> str:
    """Légende finale, adaptée à la plateforme.

    TikTok : court, le hook est déjà dans la vidéo.
    Instagram : version longue, valeur ajoutée dans la légende elle-même.
    """
    rng = random.Random(f"{piece.id}:{platform}")
    tags = build_hashtags(persona, piece.pillar, platform, rng)

    if platform == "tiktok":
        body = piece.hook if len(piece.hook) < 120 else piece.title
        blocks = [body, piece.cta]
    else:
        blocks = [piece.caption.strip(), piece.cta]

    if monetization_line:
        blocks.append(monetization_line)
    if piece.disclaimer:
        blocks.append(f"⚠️ {piece.disclaimer}")

    blocks.append(persona.disclosure["caption_tag"])
    blocks.append(" ".join(tags))

    caption = "\n\n".join(b.strip() for b in blocks if b and b.strip())
    return caption[:2200]
