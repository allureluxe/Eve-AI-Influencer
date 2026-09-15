#!/usr/bin/env python3
"""Alluxe -- l'agent qui parle a Luna et agit : script, photo, voix, video.

    python3 alluxe.py "un post Instagram sur son week-end au ski"

Se relance automatiquement sous .venv-luna/bin/python3 s'il existe : c'est
la que vivent les dependances propres a Alluxe (gTTS...), separees du
.venv du robot de trading pour ne jamais y toucher.
"""
from __future__ import annotations

import os
import sys


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
            os.environ.setdefault(cle, valeur.split("  #")[0].strip())


def _relancer_sous_venv_si_besoin(racine: str) -> None:
    venv_python = os.path.join(racine, ".venv-luna", "bin", "python3")
    deja_dedans = os.path.abspath(sys.executable) == os.path.abspath(venv_python)
    if os.path.exists(venv_python) and not deja_dedans:
        os.execv(venv_python, [venv_python] + sys.argv)


if __name__ == "__main__":
    racine = os.path.dirname(os.path.abspath(__file__))
    _relancer_sous_venv_si_besoin(racine)
    sys.path.insert(0, racine)
    _charger_env(os.path.join(racine, ".env"))

    from luna.alluxe import creer

    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(1)
    demande = " ".join(sys.argv[1:])
    resultat = creer(demande)
    print(resultat.resume())
    raise SystemExit(1 if resultat.erreurs else 0)
