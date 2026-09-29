#!/usr/bin/env python3
"""Definit le mot de passe reel du compte de service Alluxe Bot sur
Supabase, et l'enregistre dans .env -- valeur toujours fournie fraiche
en argument (jamais relue depuis un secret existant).

    python3 definir_mdp_service_alluxe_bot.py <nouveau_mot_de_passe>

Le compte de service (alluxe-bot@service.interne) est celui que
l'application utilise pour s'authentifier seule, sans ecran de
connexion (decision du 15 sept.). Cree le 17 sept. quand le mot de
passe enregistre dans le secret GitHub Actions ne correspondait plus a
celui de .env -- l'APK construite affichait "Compte de service non
configure."
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import urllib.error
import urllib.request
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gold_bot.env import charger_env  # noqa: E402

charger_env()

ID_UTILISATEUR = "1e155a11-3591-4d36-8526-597da3c2c010"  # alluxe-bot@service.interne


def main() -> int:
    if len(sys.argv) != 2:
        print("usage : python3 definir_mdp_service_alluxe_bot.py <nouveau_mot_de_passe>")
        return 1
    nouveau = sys.argv[1]

    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    cle_service = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not url or not cle_service:
        print("SUPABASE_URL ou SUPABASE_SERVICE_KEY absent de .env")
        return 1

    requete = urllib.request.Request(
        f"{url}/auth/v1/admin/users/{ID_UTILISATEUR}",
        data=json.dumps({"password": nouveau}).encode("utf-8"),
        headers={"apikey": cle_service, "authorization": f"Bearer {cle_service}",
                 "content-type": "application/json"},
        method="PUT")
    try:
        with urllib.request.urlopen(requete, timeout=15) as r:
            r.read()
    except urllib.error.HTTPError as e:
        print(f"echec Supabase : HTTP {e.code} {e.read().decode('utf-8', 'replace')[:300]}")
        return 1
    print("mot de passe Supabase mis a jour")

    horodatage = datetime.now().strftime("%Hh%M-%d-%m")
    sauvegarde = f".env.avant-mdp-service-alluxe-bot-{horodatage}"
    shutil.copyfile(".env", sauvegarde)
    with open(".env", "r", encoding="utf-8") as f:
        lignes = f.readlines()
    trouve = False
    for i, ligne in enumerate(lignes):
        if ligne.strip().startswith("ALLUXE_BOT_SERVICE_PASSWORD="):
            lignes[i] = f"ALLUXE_BOT_SERVICE_PASSWORD={nouveau}\n"
            trouve = True
            break
    if not trouve:
        lignes.append(f"ALLUXE_BOT_SERVICE_PASSWORD={nouveau}\n")
    with open(".env", "w", encoding="utf-8") as f:
        f.writelines(lignes)
    print(f".env {'mis a jour' if trouve else 'complete'} (sauvegarde : {sauvegarde})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
