#!/usr/bin/env python3
"""Enregistre GITHUB_ACTIONS_WRITE_TOKEN dans .env, sans jamais l'afficher.

    python3 mettre_a_jour_jeton_github_ecriture.py <jeton>

Jeton "fine-grained" avec la permission Secrets: Read and write sur ce
seul depot -- sert a corriger un secret GitHub Actions directement
(sans jamais l'afficher dans une conversation), via
corriger_secret_github.py. Distinct de GITHUB_ACTIONS_READ_TOKEN
(Actions: Read-only, pour lire les journaux de build).
"""
from __future__ import annotations

import shutil
import sys
from datetime import datetime


def main() -> int:
    if len(sys.argv) != 2:
        print("usage : python3 mettre_a_jour_jeton_github_ecriture.py <jeton>")
        return 1
    nouveau = sys.argv[1].strip()

    horodatage = datetime.now().strftime("%Hh%M-%d-%m")
    sauvegarde = f".env.avant-jeton-github-ecriture-{horodatage}"
    shutil.copyfile(".env", sauvegarde)

    with open(".env", "r", encoding="utf-8") as f:
        lignes = f.readlines()

    trouve = False
    for i, ligne in enumerate(lignes):
        if ligne.strip().startswith("GITHUB_ACTIONS_WRITE_TOKEN="):
            lignes[i] = f"GITHUB_ACTIONS_WRITE_TOKEN={nouveau}\n"
            trouve = True
            break
    if not trouve:
        lignes.append(f"GITHUB_ACTIONS_WRITE_TOKEN={nouveau}\n")

    with open(".env", "w", encoding="utf-8") as f:
        f.writelines(lignes)

    print(f"jeton {'mis a jour' if trouve else 'ajoute'} (sauvegarde : {sauvegarde})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
