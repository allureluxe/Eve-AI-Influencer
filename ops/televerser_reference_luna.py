#!/usr/bin/env python3
"""Remet `docs/luna/reference.jpg` a l'adresse publique du stockage Supabase.

POURQUOI UN SCRIPT ET PAS UNE COMMANDE A LA MAIN. Le visage de Luna est
ancre par UNE image de reference. Chaque generation la relit ; chaque
moteur externe (ChatGPT, un espace Hugging Face) la telecharge par son
URL. Quand l'operateur fait retoucher ce visage, la nouvelle version
doit atterrir aux DEUX adresses publiques, sinon la moitie de la chaine
continue de travailler sur l'ancien visage sans le moindre message :

    1. le stockage Supabase, seau `marque` -- ce script ;
    2. `docs/luna/reference.jpg` dans le depot, servi par
       raw.githubusercontent -- un commit.

Le 26 septembre, ChatGPT a rendu la version a UN SEUL grain de beaute
(il en mettait six). C'est cette version qui devient la reference.

    python3 ops/televerser_reference_luna.py
"""
from __future__ import annotations

import os
import sys
import urllib.error
import urllib.request

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from gold_bot.env import charger_env  # noqa: E402

charger_env()

SEAU = "marque"
NOM = "luna-reference.jpg"
FICHIER = os.path.join(RACINE, "docs", "luna", "reference.jpg")


def main() -> int:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    cle = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not url or not cle:
        print("SUPABASE_URL ou SUPABASE_SERVICE_KEY absent, rien televerse")
        return 1
    with open(FICHIER, "rb") as f:
        octets = f.read()
    requete = urllib.request.Request(
        f"{url}/storage/v1/object/{SEAU}/{NOM}",
        method="POST", data=octets,
        headers={
            # LES DEUX EN-TETES, ET CE N'EST PAS UNE REDONDANCE. La cle du
            # projet est au nouveau format (`sb_secret_...`), qui n'est PAS
            # un JWT : presentee seule en `Authorization`, le stockage
            # essaie de la decoder et repond « Invalid Compact JWS ». C'est
            # l'en-tete `apikey` qui l'identifie.
            "apikey": cle,
            "Authorization": f"Bearer {cle}",
            "Content-Type": "image/jpeg",
            # SANS CECI, LE DEUXIEME ENVOI ECHOUE EN 409 « Duplicate ».
            # Le fichier existe deja : on le remplace, on ne le cree pas.
            "x-upsert": "true",
        })
    try:
        with urllib.request.urlopen(requete, timeout=60) as r:
            r.read()
    except urllib.error.HTTPError as exc:
        print(f"echec HTTP {exc.code} : {exc.read()[:300]}")
        return 1
    print(f"televerse : {len(octets)} octets -> "
          f"{url}/storage/v1/object/public/{SEAU}/{NOM}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
