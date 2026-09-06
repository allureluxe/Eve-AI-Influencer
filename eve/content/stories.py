"""Stories Instagram : le format quotidien, distinct des épisodes.

Une Story dure 24 h, ne porte pas de légende et se regarde sans le son.
Tout le message doit donc tenir **dans l'image**. Elles servent le lien
quotidien entre deux épisodes — pas à raconter l'histoire, à la ponctuer.

Comme le reste, une Story chiffrée ne peut exister que si le journal
contient de vrais chiffres.
"""
from __future__ import annotations

import random
from dataclasses import dataclass

from eve.content import story as story_mod
from eve.persona.persona import Persona


@dataclass(frozen=True)
class Story:
    cle: str
    texte_ecran: str      # ce qui est incrusté : tout le message est là
    scene: str            # décor pour la génération d'image
    besoin_chiffres: bool = False


STORIES = [
    Story("bureau_matin", "6h40.\nOn s'y remet.",
          "a desk at dawn with a laptop just opened, coffee, low warm light"),
    Story("bug", "3 heures sur\nune virgule.",
          "a frustrated young woman rubbing her eyes in front of a laptop, night"),
    Story("carnet", "Toujours écrire\nla règle avant\nde la coder.",
          "a handwritten notebook page full of notes, pen resting on it, close-up"),
    Story("pause", "Quand ça bloque :\nje sors.",
          "walking on an empty street in the south of France, late afternoon light"),
    Story("nuit", "Il tourne.\nMoi je dors pas.",
          "a laptop screen glowing in a dark room, no one in frame"),
    Story("question", "Vous voulez voir\nquoi cette semaine ?",
          "a young woman sitting on the floor against a wall, phone propped up, casual"),
    Story("chiffres", "", "a laptop showing a simple line chart, hand resting beside it",
          besoin_chiffres=True),
]


def disponibles(journal: story_mod.Journal | None) -> list[Story]:
    """Stories publiables : celles qui n'ont pas besoin de chiffres, plus
    celles qui en ont si le journal en contient réellement."""
    a_des_chiffres = journal is not None and journal.solde_actuel is not None
    return [s for s in STORIES if not s.besoin_chiffres or a_des_chiffres]


def texte(story: Story, journal: story_mod.Journal | None) -> str:
    """Texte incrusté. Les chiffres viennent du journal, jamais d'ici."""
    if not story.besoin_chiffres:
        return story.texte_ecran
    if journal is None or journal.solde_actuel is None:
        return ""
    solde = f"{journal.solde_actuel:.2f}".replace(".", ",")
    variation = f"{journal.variation_pct:+.1f}".replace(".", ",")
    return f"Le compte aujourd'hui\n{solde} €\n({variation} %)"


def choisir(persona: Persona, jour: str,
            journal: story_mod.Journal | None = None) -> tuple[Story, str]:
    """Une Story par jour, tirée de façon déterministe : même jour, même Story."""
    journal = journal if journal is not None else story_mod.load_journal()
    options = disponibles(journal)
    rng = random.Random(f"{persona.handle}:{jour}")
    choisie = rng.choice(options)
    return choisie, texte(choisie, journal)


def prompt_image(persona: Persona, story: Story, rng: random.Random | None = None) -> str:
    return persona.image_prompt(story.scene, outfit=persona.outfit("quotidien", rng=rng),
                                rng=rng)
