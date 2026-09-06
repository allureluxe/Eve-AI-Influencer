"""Fabrique de contenu : d'un pilier éditorial vers un script vidéo complet.

Sortie : un `ContentPiece` autosuffisant (hook, beats minutés, textes à
l'écran, prompts image par plan, légende, hashtags). Fonctionne sans LLM ;
si un LLM est configuré, il ne fait qu'améliorer le hook et la légende.
"""
from __future__ import annotations

import hashlib
import json
import random
from dataclasses import asdict, dataclass, field
from datetime import date as Date

from eve.content import library as lib
from eve.content import trading
from eve.content.llm import BaseLLM, try_complete
from eve.persona.persona import Persona

# Formules de hook, une par pilier éditorial.
HOOK_TEMPLATES = {
    "lifestyle": [
        "{topic}.",
        "On me demande souvent : {topic}",
        "Personne ne montre ça, alors : {topic}",
    ],
    "fashion": [
        "{topic} — en une minute.",
        "La question qui revient le plus : {topic}",
        "Si tu ne retiens qu'une chose sur le style : {topic}",
    ],
    "travel": [
        "{topic}",
        "Avant de réserver quoi que ce soit : {topic}",
    ],
    "work": [
        "{topic}",
        "La partie de mon travail que je montre le moins : {topic}",
        "Sans filtre : {topic}",
    ],
    "mindset": [
        "{topic}",
        "Ce que j'aurais aimé qu'on me dise : {topic}",
    ],
    "qa": [
        "Vous êtes nombreux à demander : {topic}",
        "Question directe : {topic}",
    ],
}

CTA_LIBRARY = [
    "Enregistre si tu veux t'en souvenir au moment d'acheter.",
    "Dis-moi en commentaire ce que tu ferais différemment.",
    "Abonne-toi, je publie ce genre de chose chaque matin.",
    "Tu veux la version détaillée ? Demande en commentaire.",
    "Partage-le à la personne qui hésite depuis trois semaines.",
]

# Plans « b-roll » sans visage, utiles pour aérer un montage.
BROLL_SCENES = [
    "close-up of hands pouring coffee into a ceramic cup, morning light",
    "walking away from camera down a sunlit street, tote bag over the shoulder",
    "a notebook and a pen on a marble table, handwriting visible",
    "a city skyline at golden hour seen from a terrace, no people in frame",
    "folded clothes stacked on a bed, soft natural light",
]


@dataclass
class Beat:
    index: int
    start_s: float
    end_s: float
    voiceover: str
    on_screen: str
    shot_prompt: str

    @property
    def duration(self) -> float:
        return round(self.end_s - self.start_s, 2)


@dataclass
class ContentPiece:
    id: str
    date: str
    slot: str
    pillar: str
    fmt: str                        # reel | photo | carousel
    title: str
    hook: str
    beats: list[Beat]
    cta: str
    caption: str
    hashtags: list[str] = field(default_factory=list)
    disclaimer: str = ""
    monetization: dict = field(default_factory=dict)
    platforms: list[str] = field(default_factory=lambda: ["tiktok", "instagram"])
    status: str = "draft"
    assets: dict = field(default_factory=dict)

    @property
    def duration_s(self) -> float:
        return round(self.beats[-1].end_s, 2) if self.beats else 0.0

    @property
    def voiceover_text(self) -> str:
        return " ".join(b.voiceover for b in self.beats)

    @property
    def shot_prompts(self) -> list[str]:
        return [b.shot_prompt for b in self.beats]

    def full_caption(self) -> str:
        parts = [self.caption.strip()]
        if self.disclaimer:
            parts.append(f"⚠️ {self.disclaimer}")
        if self.hashtags:
            parts.append(" ".join(self.hashtags))
        return "\n\n".join(p for p in parts if p)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["duration_s"] = self.duration_s
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


def _screen(text: str, limit: int = 42) -> str:
    """Texte à l'écran : court, sinon il déborde du cadre en 9:16."""
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return f"{cut}…"


def _rng_for(piece_id: str) -> random.Random:
    """RNG déterministe : même id ⇒ même contenu (rejouable, testable)."""
    h = hashlib.sha256(piece_id.encode()).hexdigest()[:12]
    return random.Random(int(h, 16))


def _piece_id(day: Date, slot: str, pillar: str) -> str:
    return f"{day.isoformat()}_{slot.replace(':', '')}_{pillar}"


def _pace(lines: list[tuple[str, str, str]], start: float = 0.0) -> list[Beat]:
    """Convertit (voix, texte écran, prompt) en beats minutés.

    Cadence ≈ 2.7 mots/seconde (débit naturel d'une vidéo courte), bornée
    entre 1,8 s et 6 s par plan.
    """
    beats: list[Beat] = []
    t = start
    for i, (vo, screen, shot) in enumerate(lines):
        words = max(1, len(vo.split()))
        dur = min(6.0, max(1.8, round(words / 2.7 + 0.6, 1)))
        beats.append(Beat(i, round(t, 2), round(t + dur, 2), vo, screen, shot))
        t += dur
    return beats


# --------------------------------------------------------------- générateurs
def _scene(pillar: str, rng: random.Random) -> str:
    return rng.choice(lib.PILLAR_SCENES.get(pillar, lib.PILLAR_SCENES["lifestyle"]))


def _tenue(pillar: str) -> str:
    """Registre vestimentaire cohérent avec le sujet."""
    return {"travel": "resort", "work": "work", "lifestyle": "day",
            "fashion": "day", "mindset": "day", "qa": "day"}.get(pillar, "day")


def _depuis_banque(persona: Persona, pillar: str, rng: random.Random,
                   sujet: tuple[str, str, list[str]] | None = None
                   ) -> tuple[str, str, list[tuple[str, str, str]]]:
    """Trame commune : un hook, une réponse courte, puis les points."""
    topic, reponse, points = sujet or rng.choice(lib.TOPIC_BANK[pillar])
    hook = rng.choice(HOOK_TEMPLATES[pillar]).format(topic=topic)
    categorie = _tenue(pillar)

    def plan(scene: str) -> str:
        return persona.image_prompt(scene, outfit=persona.outfit(categorie, rng=rng), rng=rng)

    lignes = [(hook, _screen(topic.upper()), plan(_scene(pillar, rng))),
              (reponse, _screen(reponse), plan(_scene(pillar, rng)))]
    for point in points:
        lignes.append((point.capitalize() + ".", _screen(f"• {point}"),
                       plan(rng.choice(lib.PILLAR_SCENES.get(pillar, []) + BROLL_SCENES))))
    return topic, hook, lignes


def _travail(persona: Persona, rng: random.Random) -> tuple[str, str, list[tuple[str, str, str]]]:
    """Pilier `work` : chiffres réels si le fichier existe, méthode sinon.

    Aucun nombre n'est écrit ici : ils viennent tous de
    `data/trading/results.json` via `eve/content/trading.py`.
    """
    resultats = trading.load_results()
    sujet = trading.build_work_content(resultats, rng)
    topic, hook, lignes = _depuis_banque(persona, "work", rng, sujet=sujet)
    if resultats is not None and topic.startswith("Les chiffres"):
        # Un post chiffré se termine toujours sur le risque, jamais sur le gain.
        lignes.append(("Résultats passés, sur un système personnel. "
                       "Rien de tout ça n'est un conseil en investissement.",
                       _screen("Résultats passés · pas un conseil"),
                       persona.image_prompt(_scene("work", rng),
                                            outfit=persona.outfit("work", rng=rng), rng=rng)))
    return topic, hook, lignes


GENERATORS = {
    "lifestyle": lambda p, r: _depuis_banque(p, "lifestyle", r),
    "fashion": lambda p, r: _depuis_banque(p, "fashion", r),
    "travel": lambda p, r: _depuis_banque(p, "travel", r),
    "mindset": lambda p, r: _depuis_banque(p, "mindset", r),
    "qa": lambda p, r: _depuis_banque(p, "qa", r),
    "work": _travail,
}


def build_piece(
    persona: Persona,
    *,
    day: Date,
    slot: str,
    pillar: str,
    llm: BaseLLM | None = None,
    hashtags: list[str] | None = None,
) -> ContentPiece:
    piece_id = _piece_id(day, slot, pillar)
    rng = _rng_for(piece_id)
    generator = GENERATORS.get(pillar, GENERATORS["lifestyle"])
    title, hook, lines = generator(persona, rng)

    beats = _pace(lines)
    cta = rng.choice(CTA_LIBRARY)
    caption = _build_caption(persona, title, hook, beats, llm)

    return ContentPiece(
        id=piece_id,
        date=day.isoformat(),
        slot=slot,
        pillar=pillar,
        fmt="reel",
        title=title,
        hook=hook,
        beats=beats,
        cta=cta,
        caption=caption,
        hashtags=hashtags or [],
        disclaimer=persona.disclaimer if pillar == "work" else "",
    )


def _build_caption(
    persona: Persona,
    title: str,
    hook: str,
    beats: list[Beat],
    llm: BaseLLM | None,
) -> str:
    """Corps de la légende, sans appel à l'action, sans hashtag, sans mention.

    Tout ce qui est ajouté par plateforme (CTA, offre, divulgation, hashtags)
    est assemblé dans `captions.caption_for` — un seul endroit, pas deux.
    """
    bullets = "\n".join(f"• {b.voiceover}" for b in beats[1:-1][:4])
    fallback = f"{title}\n\n{bullets}"
    if llm is None:
        return fallback
    prompt = (
        f"Écris la légende Instagram/TikTok de cette vidéo.\n"
        f"Titre : {title}\nHook : {hook}\n"
        f"Contenu : {' '.join(b.voiceover for b in beats)}\n\n"
        "Contraintes : français, 60 à 110 mots, 2 à 4 phrases courtes puis une liste à puces, "
        "un seul emoji maximum par ligne, aucun hashtag et aucun appel à l'action "
        "(ils sont ajoutés ailleurs), aucune promesse de gain, aucun chiffre inventé."
    )
    out = try_complete(llm, persona.system_prompt(), prompt, max_tokens=400)
    return (out or fallback).strip()
