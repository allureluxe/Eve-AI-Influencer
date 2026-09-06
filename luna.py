#!/usr/bin/env python3
"""Point d'entree de Luna.

    python3 luna.py app      messages, appel et visio dans le navigateur
    python3 luna.py chat     la meme conversation, dans le terminal
    python3 luna.py aide     toutes les commandes
"""
from __future__ import annotations

import os
import sys

# `.env` est lu sans dependance : python-dotenv est pratique, mais Luna doit
# demarrer sur une machine nue.
def _charger_env(chemin: str = ".env") -> None:
    if not os.path.exists(chemin):
        return
    with open(chemin, "r", encoding="utf-8") as f:
        for ligne in f:
            ligne = ligne.strip()
            if not ligne or ligne.startswith("#") or "=" not in ligne:
                continue
            cle, _, valeur = ligne.partition("=")
            cle, valeur = cle.strip(), valeur.strip().strip('"').strip("'")
            # Les variables deja definies dans l'environnement gagnent.
            os.environ.setdefault(cle, valeur.split("  #")[0].strip())


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    _charger_env(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
    from luna.cli import main
    sys.exit(main())
