#!/usr/bin/env python3
"""Branche Supabase sur le robot, sans toucher au reste de .env.

    python3 configurer_supabase.py

Meme principe que configurer_telegram.py : ne reecrit QUE les lignes
Supabase, laisse tout le reste octet pour octet, sauvegarde avant
d'ecrire, et n'affiche jamais une valeur secrete.
"""
from __future__ import annotations

import os
import shutil
from getpass import getpass

RACINE = os.path.dirname(os.path.abspath(__file__))
ENV = os.path.join(RACINE, ".env")

VERT, ROUGE, JAUNE, GRIS, GRAS, FIN = (
    "\033[32m", "\033[31m", "\033[33m", "\033[90m", "\033[1m", "\033[0m")


def _ecrire(valeurs: dict[str, str]) -> str:
    with open(ENV, "r", encoding="utf-8") as f:
        lignes = f.readlines()

    copie = ENV + ".avant-supabase"
    shutil.copy2(ENV, copie)

    restantes = dict(valeurs)
    sorties = []
    for ligne in lignes:
        nom = ligne.split("=", 1)[0].strip()
        if nom in restantes:
            sorties.append(f"{nom}={restantes.pop(nom)}\n")
        else:
            sorties.append(ligne)
    if sorties and not sorties[-1].endswith("\n"):
        sorties[-1] += "\n"
    for nom, valeur in restantes.items():
        sorties.append(f"{nom}={valeur}\n")

    with open(ENV, "w", encoding="utf-8") as f:
        f.writelines(sorties)
    os.chmod(ENV, 0o600)
    return copie


def main() -> int:
    if not os.path.exists(ENV):
        print(f"{ROUGE}Fichier .env introuvable dans {RACINE}{FIN}")
        return 1

    url = os.environ.get("SUPABASE_URL_A_ECRIRE", "").strip()
    cle = os.environ.get("SUPABASE_SERVICE_KEY_A_ECRIRE", "").strip()

    if not url:
        url = input("URL du projet Supabase : ").strip()
    if not cle:
        try:
            cle = getpass("Cle service_role (rien ne s'affiche) : ").strip()
        except Exception:                                      # noqa: BLE001
            cle = input("Cle service_role : ").strip()

    if not url or not cle:
        print(f"{JAUNE}Rien saisi — aucune modification.{FIN}")
        return 1

    copie = _ecrire({"SUPABASE_URL": url, "SUPABASE_SERVICE_KEY": cle})
    print(f"{VERT}.env mis a jour{FIN} {GRIS}(copie de securite : "
          f"{os.path.basename(copie)}){FIN}")
    print(f"""
{GRAS}Derniere etape{FIN} — le robot lit .env au demarrage :

  {GRAS}sudo systemctl restart robot-dual-live{FIN}
""")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
