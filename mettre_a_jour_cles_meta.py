#!/usr/bin/env python3
"""Enregistre les cles Meta (Instagram / Page Facebook) dans .env.

    python3 mettre_a_jour_cles_meta.py --app-id 1234567890
    python3 mettre_a_jour_cles_meta.py --secret <cle_secrete>
    python3 mettre_a_jour_cles_meta.py --jeton-page <jeton>

Meme principe que `mettre_a_jour_jeton_supabase.py` : la valeur passe en
argument, elle est ecrite dans `.env` et n'est JAMAIS reaffichee -- ni a
l'ecran, ni dans un journal. Une sauvegarde horodatee du `.env` est
prise avant chaque modification.

CE QUE CHAQUE VALEUR PERMET :
  META_APP_ID        identifiant public de l'application (pas un secret,
                     il part dans chaque requete)
  META_APP_SECRET    la cle secrete. Sert a transformer un jeton court en
                     jeton longue duree. A traiter comme un mot de passe.
  META_PAGE_TOKEN    le jeton de la Page, obtenu ensuite. C'est LUI qui
                     autorise a publier.
  META_IG_USER_ID    identifiant du compte Instagram professionnel lie.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime

CHAMPS = {
    "app_id": "META_APP_ID",
    "secret": "META_APP_SECRET",
    "jeton_page": "META_PAGE_TOKEN",
    "ig_user_id": "META_IG_USER_ID",
}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--app-id", dest="app_id")
    p.add_argument("--secret")
    p.add_argument("--jeton-page", dest="jeton_page")
    p.add_argument("--ig-user-id", dest="ig_user_id")
    args = p.parse_args()

    a_ecrire = {CHAMPS[nom]: valeur.strip()
                for nom, valeur in vars(args).items()
                if valeur and valeur.strip()}
    if not a_ecrire:
        print("rien a enregistrer -- voir --help")
        return 1

    horodatage = datetime.now().strftime("%Hh%M-%d-%m")
    sauvegarde = f".env.avant-cles-meta-{horodatage}"
    shutil.copyfile(".env", sauvegarde)

    with open(".env", "r", encoding="utf-8") as f:
        lignes = f.readlines()

    for cle, valeur in a_ecrire.items():
        remplacee = False
        for i, ligne in enumerate(lignes):
            if ligne.strip().startswith(f"{cle}="):
                lignes[i] = f"{cle}={valeur}\n"
                remplacee = True
                break
        if not remplacee:
            lignes.append(f"{cle}={valeur}\n")
        print(f"{cle} : {'mise a jour' if remplacee else 'ajoutee'}")

    with open(".env", "w", encoding="utf-8") as f:
        f.writelines(lignes)
    print(f"sauvegarde : {sauvegarde}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
