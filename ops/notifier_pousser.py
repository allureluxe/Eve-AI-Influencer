#!/usr/bin/env python3
"""Declenche les deux fonctions Supabase de notification, toutes les 5 min.

`notifier-remplir` decide QUI et QUAND (signaux, agenda macro, clotures) et
ecrit la file. `notifier-envoyer` vide cette file vers Firebase. Les deux
sont des fonctions Edge Supabase, protegees par un secret partage
(`EVE_CRON_SECRET`) plutot que par un compte utilisateur — c'est un appel
interne, pas une requete d'application.

Lance par cron (voir crontab), jamais a la main sauf pour deboguer.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from gold_bot.env import charger_env  # noqa: E402

charger_env()

URL_BASE = os.environ.get("SUPABASE_URL", "").rstrip("/")
SECRET = os.environ.get("EVE_CRON_SECRET", "")


def _appeler(fonction: str) -> None:
    if not URL_BASE or not SECRET:
        print(f"{fonction} : SUPABASE_URL ou EVE_CRON_SECRET absent, rien fait")
        return
    requete = urllib.request.Request(
        f"{URL_BASE}/functions/v1/{fonction}",
        method="POST",
        headers={"x-eve-cron": SECRET, "Content-Type": "application/json"},
        data=b"{}",
    )
    try:
        with urllib.request.urlopen(requete, timeout=25) as reponse:
            corps = json.loads(reponse.read() or b"{}")
            print(f"{fonction} : {reponse.status} {corps}")
    except urllib.error.HTTPError as exc:
        print(f"{fonction} : HTTP {exc.code} {exc.read()[:200]}")
    except Exception as exc:  # noqa: BLE001
        print(f"{fonction} : echec {exc}")


def main() -> int:
    _appeler("notifier-remplir")
    _appeler("notifier-envoyer")
    return 0


if __name__ == "__main__":
    sys.exit(main())
