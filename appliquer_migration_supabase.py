#!/usr/bin/env python3
"""Applique un fichier .sql sur le projet Supabase, via l'API de gestion.

    python3 appliquer_migration_supabase.py supabase/migrations/xxx.sql

Utilise SUPABASE_ACCESS_TOKEN (jeton personnel, PAS la cle service_role)
et l'URL du projet (SUPABASE_URL) deja dans .env, pour executer le SQL
directement -- pas besoin du CLI Supabase ni du mot de passe de la base.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request

RACINE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RACINE)

from gold_bot.env import charger_env  # noqa: E402

charger_env()


def main() -> int:
    if len(sys.argv) != 2:
        print("usage : python3 appliquer_migration_supabase.py <fichier.sql>")
        return 1
    chemin = sys.argv[1]
    with open(chemin, "r", encoding="utf-8") as f:
        sql = f.read()

    jeton = os.environ["SUPABASE_ACCESS_TOKEN"]
    url_projet = os.environ["SUPABASE_URL"]
    ref = re.match(r"https://([a-z0-9]+)\.supabase\.co", url_projet).group(1)

    requete = urllib.request.Request(
        f"https://api.supabase.com/v1/projects/{ref}/database/query",
        data=json.dumps({"query": sql}).encode("utf-8"),
        headers={"content-type": "application/json",
                 "authorization": f"Bearer {jeton}"},
        method="POST")
    try:
        with urllib.request.urlopen(requete, timeout=60) as r:
            print(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code} : {e.read().decode('utf-8', 'replace')}")
        return 1
    print(f"applique : {chemin}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
