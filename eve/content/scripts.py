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
from eve.content import story
from eve.content import trading
from eve.content.llm import BaseLLM, try_complete
from eve.persona.persona import Persona

# Formules de hook, une par pilier éditorial.
HOOK_TEMPLATES = {
    "journal": [
        "Bon, où j'en suis cette semaine.",
        "Le point sur le compte. Sans filtre.",
        "Alors… je vous dois un bilan.",
    ],
    "build": [
        "{topic}",
        "Alors ça, personne me l'avait dit : {topic}",
        "Bon, {topic}",
    ],
    "apprendre": [
        "{topic}",
        "Si tu retiens qu'un truc de moi, que ce soit ça : {topic}",
        "On me demande souvent : {topic}",
    ],
    "quotidien": [
        "{topic}",
        "En vrai, {topic}",
    ],
    "mindset": [
        "{topic}",
        "Franchement, {topic}",
    ],
    "qa": [
        "Vous êtes plusieurs à demander : {topic}",
        "Question directe : {topic}",
    ],
}

CTA_LIBRARY = [
    "Dis-moi en commentaire si tu veux que je détaille.",
    "Abonne-toi si tu veux voir la suite — bonne ou mauvaise.",
    "Enregistre-le, tu y reviendras.",
    "Si t'as déjà vécu ça, raconte en commentaire.",
    "Je publie le point tous les dimanches.",
]

# Plans « b-roll » sans visage, pour aérer un montage.
BROLL_SCENES = [
    "close-up of hands typing on a laptop keyboard, warm desk lamp light",
    "a paper notebook covered in handwritten notes, pen resting on it",
    "a coffee cup next to a laptop, early morning light on a table",
    "a screen showing lines of code, slightly out of focus",
    "an empty street in the south of France at dawn, pale stone walls",
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


def _phrase(text: str) -> str:
    """Majuscule initiale et point final, sans écraser le reste du texte.

    `str.capitalize()` mettrait tout le reste en minuscules : une note qui
    contient déjà plusieurs phrases s'en trouverait abîmée.
    """
    text = text.strip()
    if not text:
        return text
    text = text[0].upper() + text[1:]
    return text if text[-1] in ".!?…" else text + "."


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
    return rng.choice(lib.PILLAR_SCENES.get(pillar, lib.PILLAR_SCENES["quotidien"]))


def _tenue(pillar: str) -> str:
    return {"quotidien": "quotidien", "journal": "quotidien"}.get(pillar, "quotidien")


def _depuis_banque(persona: Persona, pillar: str, rng: random.Random,
                   sujet: tuple[str, str, list[str]] | None = None
                   ) -> tuple[str, str, list[tuple[str, str, str]]]:
    """Trame commune : hook, phrase d'ouverture, puis les points.

    La tenue est tirée **une seule fois** : dans une même vidéo, Eve ne
    change pas de vêtements entre deux plans.
    """
    topic, ouverture, points = sujet or rng.choice(lib.TOPIC_BANK[pillar])
    hook = rng.choice(HOOK_TEMPLATES[pillar]).format(topic=topic)
    tenue = persona.outfit(_tenue(pillar), rng=rng)

    def plan(scene: str) -> str:
        return persona.image_prompt(scene, outfit=tenue, rng=rng)

    decors = lib.PILLAR_SCENES.get(pillar, []) + BROLL_SCENES
    lignes = [(hook, _screen(topic.upper()), plan(_scene(pillar, rng))),
              (ouverture, _screen(ouverture), plan(_scene(pillar, rng)))]
    for point in points:
        lignes.append((_phrase(point), _screen(f"• {point}"),
                       plan(rng.choice(decors))))
    return topic, hook, lignes


def _journal(persona: Persona, rng: random.Random) -> tuple[str, str, list[tuple[str, str, str]]]:
    """Pilier `journal` : uniquement ce que le fichier réel contient.

    Sans journal, Eve n'a rien à raconter sur le compte : on bascule sur la
    construction. Aucun chiffre n'est écrit ici — ils viennent tous de
    `data/trading/journal.json`.
    """
    journal = story.load_journal()
    if journal is None or journal.solde_actuel is None:
        return _depuis_banque(persona, "build", rng)

    derniere = journal.derniere
    sujet = (
        "Le point sur le compte",
        journal.resume_chiffre(),
        [note for note in [derniere.note if derniere else ""] if note]
        + ["je publie le chiffre chaque semaine, qu'il monte ou qu'il baisse",
           "c'est de l'argent que je peux perdre, et c'est le seul montant que je conseille"],
    )
    topic, hook, lignes = _depuis_banque(persona, "journal", rng, sujet=sujet)

    # Si un relevé de performance formel existe, on le cite tel quel — avec
    # son drawdown, que `trading.py` rend obligatoire.
    resultats = trading.load_results()
    if resultats is not None:
        lignes.append((resultats.ligne_chiffres(),
                       _screen(resultats.ligne_chiffres()),
                       persona.image_prompt(_scene("journal", rng),
                                            outfit=persona.outfit("quotidien", rng=rng), rng=rng)))

    lignes.append((
        "Et je le redis : c'est mon test personnel, pas un conseil en investissement.",
        _screen("Pas un conseil · je peux tout perdre"),
        persona.image_prompt(_scene("journal", rng),
                             outfit=persona.outfit("quotidien", rng=rng), rng=rng)))
    return topic, hook, lignes


GENERATORS = {
    "journal": _journal,
    "build": lambda p, r: _depuis_banque(p, "build", r),
    "apprendre": lambda p, r: _depuis_banque(p, "apprendre", r),
    "quotidien": lambda p, r: _depuis_banque(p, "quotidien", r),
    "mindset": lambda p, r: _depuis_banque(p, "mindset", r),
    "qa": lambda p, r: _depuis_banque(p, "qa", r),
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
    generator = GENERATORS.get(pillar, GENERATORS["build"])
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
        disclaimer=persona.disclaimer if pillar in {"journal", "apprendre"} else "",
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
