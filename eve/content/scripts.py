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
from eve.content.llm import BaseLLM, try_complete
from eve.persona.persona import Persona

# Formules de hook qui marchent sur des vidéos courtes fitness.
HOOK_TEMPLATES = {
    "form_check": [
        "Tu fais {exo} comme ça ? Arrête deux secondes.",
        "L'erreur n°1 sur {exo}, et elle est partout en salle.",
        "Personne ne t'a jamais expliqué {exo} correctement.",
        "3 détails qui changent tout sur {exo}.",
    ],
    "quick_workout": [
        "{minutes} minutes, zéro matériel, on commence maintenant.",
        "Si tu n'as que {minutes} minutes aujourd'hui, fais exactement ça.",
        "Séance {focus} en {minutes} minutes — suis-moi.",
        "Enregistre ça : {minutes} minutes pour les jours sans temps.",
    ],
    "nutrition": [
        "{topic} — la réponse courte.",
        "Arrête de compliquer : {topic}.",
        "On m'a posé la question 40 fois cette semaine : {topic}",
    ],
    "motivation": [
        "{topic}. Écoute ça avant d'abandonner.",
        "La seule règle que je n'ai jamais cassée : {topic}",
        "Si tu recommences pour la cinquième fois, c'est pour toi.",
    ],
    "lifestyle": [
        "{topic}",
        "Ce que je fais vraiment tous les jours : {topic}",
    ],
    "qa": [
        "Question du jour : {topic}",
        "Vous êtes nombreuses à demander : {topic}",
    ],
}

CTA_LIBRARY = [
    "Enregistre ce post pour ta prochaine séance.",
    "Dis-moi en commentaire où tu bloques, je réponds à tout.",
    "Partage-le à celle qui commence lundi (encore).",
    "Programme complet en bio si tu veux la version 4 semaines.",
    "Abonne-toi, une séance courte chaque matin.",
]

# Plans "b-roll" génériques réutilisables.
BROLL_SCENES = [
    "tying her sneakers before a workout, close-up hands, morning light",
    "filling a water bottle in a bright kitchen, natural light",
    "checking her smartwatch after a set, slightly out of breath, smiling",
    "walking on the boardwalk with a gym bag over the shoulder, golden hour",
    "rolling out a yoga mat in a bright home studio",
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
def _form_check(persona: Persona, rng: random.Random) -> tuple[str, str, list[tuple[str, str, str]]]:
    exo = rng.choice(lib.EXERCISES)
    hook = rng.choice(HOOK_TEMPLATES["form_check"]).format(exo=exo.name_fr.lower())
    lines = [(hook, exo.name_fr.upper(), persona.image_prompt(
        "talking directly to the camera in a gym, confident and friendly, medium shot", rng=rng))]
    mistake = rng.choice(exo.mistakes)
    lines.append((f"L'erreur : {mistake}.", f"❌ {mistake}",
                  persona.image_prompt(exo.scene, rng=rng)))
    for cue in exo.cues[:3]:
        lines.append((cue.capitalize() + ".", f"✅ {cue}",
                      persona.image_prompt(exo.scene, rng=rng)))
    lines.append((f"Refais une série en pensant à ça. {exo.target.capitalize()}, tu vas les sentir.",
                  "À TOI 💪", persona.image_prompt(
                      "smiling at the camera after a set, thumbs up, gym background", rng=rng)))
    return f"Technique : {exo.name_fr}", hook, lines


def _quick_workout(persona: Persona, rng: random.Random) -> tuple[str, str, list[tuple[str, str, str]]]:
    wo = rng.choice(lib.WORKOUTS)
    hook = rng.choice(HOOK_TEMPLATES["quick_workout"]).format(
        minutes=wo.duration_min, focus=wo.focus)
    lines = [(hook, f"{wo.duration_min} MIN · {wo.focus.upper()}", persona.image_prompt(
        "talking to the camera before starting a workout, hands on hips, energetic", rng=rng))]
    for key, fmt in wo.blocks:
        exo = lib.EXERCISES_BY_KEY[key]
        lines.append((f"{exo.name_fr}, {fmt}.", f"{exo.name_fr} — {fmt}",
                      persona.image_prompt(exo.scene, rng=rng)))
    lines.append(("Deux tours si tu as le temps. Sinon un seul, ça compte quand même.",
                  "1 à 2 TOURS", persona.image_prompt(
                      "wiping her forehead with a towel after a workout, satisfied smile", rng=rng)))
    return wo.title_fr, hook, lines


def _from_topic_bank(persona: Persona, pillar: str, rng: random.Random) -> tuple[str, str, list[tuple[str, str, str]]]:
    topic, answer, points = rng.choice(lib.TOPIC_BANK[pillar])
    hook = rng.choice(HOOK_TEMPLATES[pillar]).format(topic=topic)
    scene_pool = {
        "nutrition": "preparing a simple high-protein meal in a bright kitchen, natural light",
        "motivation": "sitting on a gym bench talking to the camera, calm and sincere",
        "lifestyle": rng.choice(BROLL_SCENES),
        "qa": "talking to the camera in a home studio, relaxed posture",
    }[pillar]
    lines = [(hook, _screen(topic.upper()), persona.image_prompt(scene_pool, rng=rng)),
             (answer, _screen(answer), persona.image_prompt(scene_pool, rng=rng))]
    for point in points:
        lines.append((point.capitalize() + ".", _screen(f"• {point}"),
                      persona.image_prompt(rng.choice(BROLL_SCENES), rng=rng)))
    return topic, hook, lines


GENERATORS = {
    "form_check": _form_check,
    "quick_workout": _quick_workout,
    "nutrition": lambda p, r: _from_topic_bank(p, "nutrition", r),
    "motivation": lambda p, r: _from_topic_bank(p, "motivation", r),
    "lifestyle": lambda p, r: _from_topic_bank(p, "lifestyle", r),
    "qa": lambda p, r: _from_topic_bank(p, "qa", r),
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
    generator = GENERATORS.get(pillar, GENERATORS["motivation"])
    title, hook, lines = generator(persona, rng)

    beats = _pace(lines)
    cta = rng.choice(CTA_LIBRARY)
    caption = _build_caption(persona, title, hook, beats, cta, llm)

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
        disclaimer=persona.disclaimer if pillar in {"nutrition", "form_check", "quick_workout"} else "",
    )


def _build_caption(
    persona: Persona,
    title: str,
    hook: str,
    beats: list[Beat],
    cta: str,
    llm: BaseLLM | None,
) -> str:
    bullets = "\n".join(f"• {b.voiceover}" for b in beats[1:-1][:4])
    fallback = f"{title}\n\n{bullets}\n\n{cta}"
    if llm is None:
        return fallback
    prompt = (
        f"Écris la légende Instagram/TikTok de cette vidéo.\n"
        f"Titre : {title}\nHook : {hook}\n"
        f"Contenu : {' '.join(b.voiceover for b in beats)}\n"
        f"Appel à l'action à conserver : {cta}\n\n"
        "Contraintes : français, 60 à 110 mots, 2 à 4 phrases courtes puis une liste à puces, "
        "un seul emoji maximum par ligne, aucun hashtag (ils sont ajoutés ailleurs), "
        "aucune promesse de résultat."
    )
    out = try_complete(llm, persona.system_prompt(), prompt, max_tokens=400)
    return (out or fallback).strip()
