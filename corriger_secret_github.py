#!/usr/bin/env python3
"""Ecrit un secret GitHub Actions depuis .env, sans jamais l'afficher.

    python3 corriger_secret_github.py ALLUXE_BOT_SERVICE_PASSWORD

Chiffre la valeur cote client (libsodium, sealed box) avec la cle
publique du depot avant de l'envoyer -- c'est ce que fait `gh secret
set` en coulisses. Necessite GITHUB_ACTIONS_WRITE_TOKEN dans .env
(jeton fine-grained, permission Secrets: Read and write, sur ce seul
depot -- voir mettre_a_jour_jeton_github_ecriture.py).

Cree le 16 sept. quand l'APK construite montrait "Compte de service
non configure." : les identifiants dans .env fonctionnaient (verifie
par une vraie connexion Supabase), mais le secret GitHub utilise par
le build ne correspondait pas.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gold_bot.env import charger_env  # noqa: E402

charger_env()

DEPOT = "allureluxe/Eve-AI-Influencer"


def main() -> int:
    if len(sys.argv) != 2:
        print("usage : python3 corriger_secret_github.py <NOM_DU_SECRET>")
        return 1
    nom_secret = sys.argv[1]

    jeton = os.environ.get("GITHUB_ACTIONS_WRITE_TOKEN", "")
    valeur = os.environ.get(nom_secret, "")
    if not jeton:
        print("GITHUB_ACTIONS_WRITE_TOKEN absent de .env")
        return 1
    if not valeur:
        print(f"{nom_secret} absent ou vide dans .env -- rien a ecrire")
        return 1

    from nacl import encoding, public

    entetes = {"authorization": f"Bearer {jeton}",
               "accept": "application/vnd.github+json"}

    requete = urllib.request.Request(
        f"https://api.github.com/repos/{DEPOT}/actions/secrets/public-key",
        headers=entetes)
    with urllib.request.urlopen(requete, timeout=15) as r:
        cle_publique = json.loads(r.read())

    boite = public.SealedBox(public.PublicKey(
        cle_publique["key"], encoding.Base64Encoder()))
    chiffre = base64.b64encode(boite.encrypt(valeur.encode("utf-8"))).decode("utf-8")

    corps = json.dumps({
        "encrypted_value": chiffre,
        "key_id": cle_publique["key_id"],
    }).encode("utf-8")
    requete = urllib.request.Request(
        f"https://api.github.com/repos/{DEPOT}/actions/secrets/{nom_secret}",
        data=corps, headers={**entetes, "content-type": "application/json"},
        method="PUT")
    with urllib.request.urlopen(requete, timeout=15) as r:
        print(f"secret {nom_secret} mis a jour (HTTP {r.status})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
