#!/usr/bin/env python3
"""Enregistre GITHUB_ACTIONS_READ_TOKEN dans .env, sans jamais l'afficher.

    python3 mettre_a_jour_jeton_github.py <jeton>

Jeton "fine-grained" en LECTURE SEULE (Actions: Read-only) sur ce seul
depot -- sert uniquement a lire les journaux de construction GitHub
Actions depuis le VPS (l'API les refuse sans authentification, meme
sur un depot public). Sauvegarde .env avant toute modification, meme
principe que mettre_a_jour_jeton_supabase.py.
"""
from __future__ import annotations

import shutil
import sys
from datetime import datetime


def main() -> int:
    if len(sys.argv) != 2:
        print("usage : python3 mettre_a_jour_jeton_github.py <jeton>")
        return 1
    nouveau = sys.argv[1].strip()

    horodatage = datetime.now().strftime("%Hh%M-%d-%m")
    sauvegarde = f".env.avant-jeton-github-{horodatage}"
    shutil.copyfile(".env", sauvegarde)

    with open(".env", "r", encoding="utf-8") as f:
        lignes = f.readlines()

    trouve = False
    for i, ligne in enumerate(lignes):
        if ligne.strip().startswith("GITHUB_ACTIONS_READ_TOKEN="):
            lignes[i] = f"GITHUB_ACTIONS_READ_TOKEN={nouveau}\n"
            trouve = True
            break
    if not trouve:
        lignes.append(f"GITHUB_ACTIONS_READ_TOKEN={nouveau}\n")

    with open(".env", "w", encoding="utf-8") as f:
        f.writelines(lignes)

    print(f"jeton {'mis a jour' if trouve else 'ajoute'} (sauvegarde : {sauvegarde})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
