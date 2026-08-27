"""Assemblage du prompt systeme.

Ordre volontaire : identite, cadre permanent, registre, moment, memoire.
Le cadre arrive tot et les consignes de jeu apres — un modele suit mieux
une regle posee avant le decor qu'une regle ajoutee en note de bas de page.
"""
from __future__ import annotations

from datetime import datetime

from .limites import CONSIGNES_REGISTRE, REGLES_BASE, Signal
from .memoire import Memoire
from .moments import Moment
from .persona import Persona


def construire(persona: Persona, moment: Moment, memoire: Memoire,
               registre: str, signaux: list[Signal] | None = None,
               canal: str = "app", quand: datetime | None = None) -> str:
    quand = quand or datetime.now()
    blocs = [
        persona.presentation(),
        "CARACTERE :\n" + "\n".join(f"- {t}" for t in persona.caractere),
        "PASSIONS :\n" + ", ".join(persona.passions) + ".",
        "FACON D'ECRIRE :\n" + "\n".join(f"- {t}" for t in persona.tics) + (
            "\n- Tu ecris en francais, comme dans un vrai fil de messages : "
            "phrases courtes, ponctuation vivante, pas de paragraphe de "
            "roman, jamais de liste a puces."
            "\n- Tu ne decris pas tes actions entre asterisques sauf si "
            "l'utilisateur le fait en premier."),
        "EXEMPLES DE TON :\n" + "\n".join(
            f"- ({cle}) {texte}" for cle, texte in persona.exemples),
        REGLES_BASE,
        CONSIGNES_REGISTRE.get(registre, CONSIGNES_REGISTRE["tendre"]),
        moment.consigne(),
        f"Nous sommes le {quand.strftime('%A %d %B %Y')}, il est "
        f"{quand.strftime('%H:%M')}. Canal : {canal}.",
        "CE QUE TU SAIS DE LUI :\n" + memoire.resume(),
    ]
    for s in (signaux or []):
        blocs.append(s.consigne)
    return "\n\n".join(blocs)
