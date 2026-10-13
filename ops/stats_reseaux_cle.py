#!/usr/bin/env python3
"""Enregistre WINDSOR_API_KEY dans .env, sans jamais l'afficher.

    python3 ops/stats_reseaux_cle.py <cle>

La clé vient de onboard.windsor.ai (menu « API key »). Sauvegarde .env
avant toute modification, même principe que mettre_a_jour_jeton_picovoice.py.
"""
from __future__ import annotations

import os
import shutil
import sys
from datetime import datetime

ENV = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")


def main() -> int:
    if len(sys.argv) != 2:
        print("usage : python3 ops/stats_reseaux_cle.py <cle>")
        return 1
    nouvelle = sys.argv[1].strip()
    shutil.copyfile(ENV, f"{ENV}.avant-windsor-{datetime.now().strftime('%Hh%M-%d-%m')}")
    with open(ENV, encoding="utf-8") as f:
        lignes = [l for l in f.readlines() if not l.strip().startswith("WINDSOR_API_KEY=")]
    lignes.append(f"WINDSOR_API_KEY={nouvelle}\n")
    with open(ENV, "w", encoding="utf-8") as f:
        f.writelines(lignes)
    print("WINDSOR_API_KEY enregistrée.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
