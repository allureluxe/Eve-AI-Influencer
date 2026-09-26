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
import random
import sys
from pathlib import Path

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from gold_bot.env import charger_env  # noqa: E402

charger_env()

from luna.budget import Depenses  # noqa: E402
from luna.moteurs import ErreurMoteur, GenerateurImages  # noqa: E402
from luna.persona import LUNA  # noqa: E402
from luna.photos import (  # noqa: E402
    CADRAGES_DEDANS, CADRAGES_DEHORS, COIFFURES, DEFAUTS, GARDE_ROBE,
    LIEUX_BANALS, LUMIERES, PEAU_REELLE, POSES_INTERDITES,
)

#: La scene par defaut : Lyon, ses racines. Decor reel, lumiere de fin de
#: journee. LA TENUE N'EST PAS ECRITE ICI — elle est tiree de la
#: garde-robe, sinon Luna porte le meme sweat noir sur toutes ses photos.
#: Remarque de l'operateur le 26 septembre, et il avait raison : la
#: premiere image produite par ce script portait exactement la tenue de
#: la photo de Metz de la veille.
#: VIDE PAR DEFAUT — et c'est le changement du 26 septembre.
#:
#: La scene etait « quai de Saone a l'heure doree, Fourviere derriere ».
#: Une belle image, et l'operateur a tranche : « c'est pas reel du
#: tout ». Le decor de carte postale trahissait la generation plus
#: surement qu'un defaut de rendu.
#:
#: Sans `--scene`, le script tire maintenant un lieu BANAL, une lumiere
#: INGRATE et des defauts de photo. On peut toujours imposer une belle
#: scene avec `--scene`, mais il faut le vouloir.
SCENE_DEFAUT = ""


def main() -> int:
    a = argparse.ArgumentParser(description=__doc__)
    a.add_argument("--scene", default=SCENE_DEFAUT,
                   help="la scene, en anglais (le modele y repond mieux)")
    a.add_argument("--format", default="portrait_3_4",
                   help="portrait_3_4 (defaut), portrait_9_16, carre, paysage")
    a.add_argument("--sortie", default="data/luna-profil/essai.png")
    a.add_argument("--qualite", default="finale", choices=["finale", "brouillon"])
    a.add_argument("--tenue", default="",
                   help="une tenue precise ; sinon tiree de la garde-robe")
    a.add_argument("--coiffure", default="",
                   help="une coiffure precise ; sinon tiree au sort")
    a.add_argument("--cadrage", default="",
                   help="qui tient le telephone ; sinon tire au sort")
    a.add_argument("--dedans", action="store_true",
                   help="scene en interieur : autorise la selfie-miroir, "
                        "impossible sur un quai")
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

    # LA TENUE ET LA COIFFURE SE TIRENT, ELLES NE SE FIGENT PAS.
    #
    # Ce sont les deux seules choses qui doivent changer d'une photo a
    # l'autre : le visage, lui, est tenu par l'ancre et par la
    # reference. Une femme qui porte le meme sweat sur quarante photos
    # n'existe pas ; une femme qui change de visage non plus.
    tenue = args.tenue or random.choice(GARDE_ROBE)
    coiffure = args.coiffure or random.choice(COIFFURES)

    # QUI TIENT LE TELEPHONE ? C'est la question que mes deux premiers
    # essais ne posaient pas, et c'est elle qui decide si l'image passe
    # pour vraie. Luna n'a pas de photographe : toute image qui ne rentre
    # pas dans l'un de ces cadrages est impossible, et une image
    # impossible trahit un compte artificiel plus surement qu'un mauvais
    # rendu.
    cadrages = CADRAGES_DEDANS if args.dedans else CADRAGES_DEHORS
    cadrage = args.cadrage or random.choice(cadrages)

    # LE CONTEXTE INGRAT EST LE DEFAUT, PAS L'EXCEPTION. Une photo prise
    # au flash dans un couloir blanc passe pour vraie ; la meme femme
    # devant un monument a l'heure doree passe pour une publicite.
    if args.scene:
        scene = args.scene
    else:
        scene = (f"an ordinary unremarkable phone snapshot in "
                 f"{random.choice(LIEUX_BANALS)}, "
                 f"{random.choice(LUMIERES)}, {PEAU_REELLE}, "
                 f"{random.choice(DEFAUTS)}")

    print(f"tenue      : {tenue[:66]}...")
    print(f"coiffure   : {coiffure[:66]}...")
    print(f"cadrage    : {cadrage[:66]}...")
    print(f"scene      : {scene[:66]}...")

    prompt = (f"{LUNA.apparence.ancre}, {coiffure}, wearing {tenue}, "
              f"{scene}, {cadrage}, {POSES_INTERDITES}")
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
