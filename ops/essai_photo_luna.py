#!/usr/bin/env python3
"""Une seule photo de Luna, pour juger. Rien n'est publie, rien n'est mis en file.

POURQUOI UN SCRIPT A PART, ET PAS LA FILE D'ATTENTE

Le pipeline complet — file Supabase, worker, stockage, publication — a
beaucoup de pieces. Quand la photo qui en sort ne ressemble pas a Luna,
on ne sait pas laquelle est en cause : le prompt, l'ancre, le modele, la
reference, le format. Ce script ne fait qu'UNE chose, la plus courte
possible :

    ancre + scene  ->  OpenAI  ->  un fichier sur le disque

Aucune ligne en base, aucun appel a Instagram, aucun cron. On regarde
l'image, et on sait.

    python3 ops/essai_photo_luna.py
    python3 ops/essai_photo_luna.py --scene "sur les quais de Saone a Lyon"
    python3 ops/essai_photo_luna.py --format portrait_9_16 --sortie /tmp/x.png

LE PLAFOND S'APPLIQUE. Ce script depense de l'argent reel comme le
reste ; `luna/budget.py` le compte et refuse quand la journee est
pleine. Il affiche ce qu'il reste avant et apres, pour qu'on sache ou on
en est sans aller lire un fichier.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from gold_bot.env import charger_env  # noqa: E402

charger_env()

from luna.budget import Depenses  # noqa: E402
from luna.moteurs import ErreurMoteur, GenerateurImages  # noqa: E402
from luna.persona import LUNA  # noqa: E402

#: La scene par defaut : Lyon, ses racines. Decor reel, tenue d'etudiante,
#: lumiere de fin de journee — les trois choses qui font qu'une photo
#: passe pour vraie.
SCENE_DEFAUT = (
    "walking along the Saone riverbank in Vieux Lyon at golden hour, "
    "turning back toward the camera over her shoulder with a small closed "
    "smile, wearing an oversized black sweatshirt, light blue jeans and "
    "white sneakers, a cream canvas tote bag on her shoulder, the "
    "Renaissance facades of Vieux Lyon and Fourviere hill behind her, a "
    "few blurred passers-by further away, candid photo taken by a friend "
    "on a phone, visible skin texture, slightly imperfect, no plastic or "
    "airbrushed look"
)


def main() -> int:
    a = argparse.ArgumentParser(description=__doc__)
    a.add_argument("--scene", default=SCENE_DEFAUT,
                   help="la scene, en anglais (le modele y repond mieux)")
    a.add_argument("--format", default="portrait_3_4",
                   help="portrait_3_4 (defaut), portrait_9_16, carre, paysage")
    a.add_argument("--sortie", default="data/luna-profil/essai.png")
    a.add_argument("--qualite", default="finale", choices=["finale", "brouillon"])
    args = a.parse_args()

    depenses = Depenses()
    print(f"budget du jour : {depenses.total_du_jour():.2f} EUR depenses, "
          f"{depenses.reste():.2f} EUR restants sur {depenses.plafond:.2f}")

    reference = Path(os.getenv("LUNA_IMAGE_REFERENCE", "docs/luna/reference.jpg"))
    if reference.is_file():
        print(f"reference  : {reference} ({reference.stat().st_size // 1024} Ko)")
    else:
        # ON PREVIENT FORT. Sans reference, le modele invente une femme
        # qui ressemble a la description — et ce ne sera pas Luna. Juger
        # la ressemblance sur une image produite sans elle n'aurait
        # aucun sens.
        print(f"ATTENTION  : {reference} introuvable. Le visage ne sera PAS "
              "tenu, et cet essai ne dira rien sur la ressemblance.")

    generateur = GenerateurImages()
    noms = [c["nom"] for c in generateur._candidats]
    print(f"moteurs    : {' -> '.join(noms) if noms else 'AUCUN'}")
    if not noms:
        print("\nAucun generateur configure. Ajouter dans .env :\n"
              "    OPENAI_API_KEY=sk-...")
        return 1
    if noms[0] != "openai":
        print("\nNote : OpenAI n'est pas en tete. Sans lui, le visage de "
              "Luna derivera d'une photo a l'autre — c'est le seul de la "
              "chaine qui sache partir d'une reference.")

    prompt = f"{LUNA.apparence.ancre}, {args.scene}"
    print(f"prompt     : {len(prompt)} caracteres")

    try:
        octets = generateur.generer(prompt, format=args.format,
                                    qualite=args.qualite)
    except ErreurMoteur as e:
        print(f"\nECHEC : {e}")
        return 1

    cible = Path(args.sortie)
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.write_bytes(octets)
    print(f"\nECRIT      : {cible} ({len(octets) // 1024} Ko)")
    print(f"budget     : {Depenses().reste():.2f} EUR restants aujourd'hui")
    print("\nRegarder, dans cet ordre : le VISAGE (est-ce elle ?), les "
          "racines foncees, UN SEUL grain de beaute, le grain de peau.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
