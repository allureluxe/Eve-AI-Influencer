#!/usr/bin/env python3
"""Enregistre une cle de moteur de conversation pour Luna, sans l'afficher.

Meme principe que configurer_telegram.py / configurer_supabase.py : ne
reecrit QUE les lignes concernees, sauvegarde avant d'ecrire, n'affiche
jamais une valeur secrete.

    GEMINI_API_KEY_A_ECRIRE=xxx python3 configurer_luna_ia.py
    GROQ_API_KEY_A_ECRIRE=xxx python3 configurer_luna_ia.py
    HUGGINGFACE_API_KEY_A_ECRIRE=xxx python3 configurer_luna_ia.py

Stocke la cle Gemini sous GEMINI_API_KEY (reference, pas branchee dans
LUNA_API_* : generativelanguage.googleapis.com refuse les requetes
depuis ce serveur -- voir memoire operateur du 15 sept.).

Groq, lui, repond depuis ce serveur (verifie le 15 sept., HTTP 200 sur
/v1/models). GROQ_API_KEY_A_ECRIRE branche donc directement
LUNA_API_URL/LUNA_API_KEY/LUNA_API_MODELE, qui font passer Luna en
mode connecte des le prochain demarrage.

HUGGINGFACE_API_KEY_A_ECRIRE stocke la cle sous HUGGINGFACE_API_KEY,
lue directement par `luna.moteurs.GenerateurImages` (gratuit, verifie
fonctionnel le 15 sept. avec stable-diffusion-3-medium-diffusers).
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

    copie = ENV + ".avant-luna-ia"
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

    gemini = os.environ.get("GEMINI_API_KEY_A_ECRIRE", "").strip()
    groq = os.environ.get("GROQ_API_KEY_A_ECRIRE", "").strip()
    huggingface = os.environ.get("HUGGINGFACE_API_KEY_A_ECRIRE", "").strip()

    if not gemini and not groq and not huggingface:
        try:
            groq = getpass("Cle Groq (rien ne s'affiche) : ").strip()
        except Exception:                                      # noqa: BLE001
            groq = input("Cle Groq : ").strip()

    if not gemini and not groq and not huggingface:
        print(f"{JAUNE}Rien saisi — aucune modification.{FIN}")
        return 1

    valeurs: dict[str, str] = {}
    if gemini:
        valeurs["GEMINI_API_KEY"] = gemini
    if groq:
        valeurs["LUNA_API_URL"] = "https://api.groq.com/openai/v1"
        valeurs["LUNA_API_KEY"] = groq
        valeurs["LUNA_API_MODELE"] = "openai/gpt-oss-120b"
    if huggingface:
        valeurs["HUGGINGFACE_API_KEY"] = huggingface

    copie = _ecrire(valeurs)
    print(f"{VERT}.env mis a jour{FIN} {GRIS}(copie de securite : "
          f"{os.path.basename(copie)}){FIN}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
