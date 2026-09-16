#!/usr/bin/env python3
"""Enregistre PICOVOICE_ACCESS_KEY dans .env, sans jamais l'afficher.

    python3 mettre_a_jour_jeton_picovoice.py <cle_d_acces>

La cle vient de https://console.picovoice.ai (compte gratuit, page
"AccessKey"). Sauvegarde .env avant toute modification, meme principe
que mettre_a_jour_jeton_supabase.py.
"""
from __future__ import annotations

import shutil
import sys
from datetime import datetime


def main() -> int:
    if len(sys.argv) != 2:
        print("usage : python3 mettre_a_jour_jeton_picovoice.py <cle_d_acces>")
        return 1
    nouvelle = sys.argv[1].strip()

    horodatage = datetime.now().strftime("%Hh%M-%d-%m")
    sauvegarde = f".env.avant-jeton-picovoice-{horodatage}"
    shutil.copyfile(".env", sauvegarde)

    with open(".env", "r", encoding="utf-8") as f:
        lignes = f.readlines()

    trouve = False
    for i, ligne in enumerate(lignes):
        if ligne.strip().startswith("PICOVOICE_ACCESS_KEY="):
            lignes[i] = f"PICOVOICE_ACCESS_KEY={nouvelle}\n"
            trouve = True
            break
    if not trouve:
        lignes.append(f"PICOVOICE_ACCESS_KEY={nouvelle}\n")

    with open(".env", "w", encoding="utf-8") as f:
        f.writelines(lignes)

    print(f"cle {'mise a jour' if trouve else 'ajoutee'} (sauvegarde : {sauvegarde})")
    print("Reste a faire : ajouter le meme secret PICOVOICE_ACCESS_KEY dans "
          "GitHub (Settings > Secrets and variables > Actions) pour que le "
          "build en ligne l'utilise aussi -- .env ne sert qu'en local.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
