#!/usr/bin/env python3
"""Enregistre EXPO_TOKEN dans .env, sans jamais l'afficher.

    python3 mettre_a_jour_jeton_expo.py <cle_d_acces>

Le jeton vient de https://expo.dev/settings/access-tokens (bouton
"Create token"). Il sert aux mises a jour OTA d Alluxe Bot. Sauvegarde .env avant toute modification, meme principe
que mettre_a_jour_jeton_supabase.py.
"""
from __future__ import annotations

import shutil
import sys
from datetime import datetime


def main() -> int:
    if len(sys.argv) != 2:
        print("usage : python3 mettre_a_jour_jeton_expo.py <cle_d_acces>")
        return 1
    nouvelle = sys.argv[1].strip()

    horodatage = datetime.now().strftime("%Hh%M-%d-%m")
    sauvegarde = f".env.avant-jeton-expo-{horodatage}"
    shutil.copyfile(".env", sauvegarde)

    with open(".env", "r", encoding="utf-8") as f:
        lignes = f.readlines()

    trouve = False
    for i, ligne in enumerate(lignes):
        if ligne.strip().startswith("EXPO_TOKEN="):
            lignes[i] = f"EXPO_TOKEN={nouvelle}\n"
            trouve = True
            break
    if not trouve:
        lignes.append(f"EXPO_TOKEN={nouvelle}\n")

    with open(".env", "w", encoding="utf-8") as f:
        f.writelines(lignes)

    print(f"cle {'mise a jour' if trouve else 'ajoutee'} (sauvegarde : {sauvegarde})")
    print("Reste a faire : ajouter le meme secret EXPO_TOKEN dans "
          "GitHub (Settings > Secrets and variables > Actions) pour que le "
          "build en ligne l'utilise aussi -- .env ne sert qu'en local.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
