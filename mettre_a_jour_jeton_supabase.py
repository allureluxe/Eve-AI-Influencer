#!/usr/bin/env python3
"""Remplace SUPABASE_ACCESS_TOKEN dans .env, sans jamais l'afficher.

    python3 mettre_a_jour_jeton_supabase.py <nouveau_jeton>

Sauvegarde .env avant toute modification, comme les autres scripts de
configuration ponctuels du depot (configurer_luna_ia.py).
"""
from __future__ import annotations

import shutil
import sys
from datetime import datetime


def main() -> int:
    if len(sys.argv) != 2:
        print("usage : python3 mettre_a_jour_jeton_supabase.py <nouveau_jeton>")
        return 1
    nouveau = sys.argv[1].strip()

    horodatage = datetime.now().strftime("%Hh%M-%d-%m")
    sauvegarde = f".env.avant-jeton-supabase-{horodatage}"
    shutil.copyfile(".env", sauvegarde)

    with open(".env", "r", encoding="utf-8") as f:
        lignes = f.readlines()

    trouve = False
    for i, ligne in enumerate(lignes):
        if ligne.strip().startswith("SUPABASE_ACCESS_TOKEN="):
            lignes[i] = f"SUPABASE_ACCESS_TOKEN={nouveau}\n"
            trouve = True
            break
    if not trouve:
        lignes.append(f"SUPABASE_ACCESS_TOKEN={nouveau}\n")

    with open(".env", "w", encoding="utf-8") as f:
        f.writelines(lignes)

    print(f"jeton {'mis a jour' if trouve else 'ajoute'} (sauvegarde : {sauvegarde})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
