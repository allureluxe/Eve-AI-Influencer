#!/usr/bin/env python3
"""Publie l'etat des comptes sociaux de Luna, pour l'application.

POURQUOI UN FICHIER ET PAS UNE TABLE
====================================

L'etat des reseaux devait aller dans une table `luna_reseaux`. Le jeton
d'administration Supabase (`SUPABASE_ACCESS_TOKEN`) est expire depuis le
21 septembre au soir -- meme lister les projets rend 401 -- donc aucune
migration ne passe, et attendre un nouveau jeton bloquait tout l'ecran.

Un fichier JSON depose dans le seau PUBLIC `marque` fait le meme travail
sans DDL : l'application le lit par une URL publique, exactement comme
elle lit le logo. L'ecran ne connait qu'une adresse.

MISE A JOUR DU 21 SEPTEMBRE, 22h30 : le jeton a ete regenere et la
table `luna_reseaux` EXISTE desormais. On n'y bascule PAS tout de
suite -- le fichier fonctionne, il est en service, et remplacer une
piece qui marche par une autre « plus propre » en fin de soiree est
exactement la decision qui casse quelque chose sans rien apporter.

La bascule est un chantier de quinze lignes (ce script ecrit la table,
`services/reseaux.ts` la lit par PostgREST) a faire de jour, avec les
tests sous la main.

CE QUE L'APPLICATION NE DOIT JAMAIS AVOIR
=========================================

Le jeton Instagram. Il vit dans `.env`, sur le serveur, et rien d'autre.
Ce script lit l'API avec, puis n'ecrit que des CHIFFRES : nom du compte,
nombre d'abonnes, nombre de publications. Une application mobile est un
fichier que n'importe qui peut ouvrir ; un jeton qui s'y trouve est un
jeton publie.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gold_bot.env import charger_env   # noqa: E402

charger_env()

log = logging.getLogger("luna-reseaux")

SEAU = "marque"
FICHIER = "reseaux.json"


def instagram() -> dict:
    """Ce que dit l'API d'Instagram, ou pourquoi elle ne dit rien."""
    try:
        from ops.instagram import qui_suis_je, _appel
    except Exception as exc:                                   # noqa: BLE001
        return {"connecte": False, "detail": f"module indisponible : {exc}"}
    try:
        moi = qui_suis_je()
    except Exception as exc:                                   # noqa: BLE001
        # Le jeton dure 60 jours. Passe ce delai il faut refaire
        # l'autorisation a la main : autant que l'ecran le dise.
        return {"connecte": False,
                "detail": f"non joignable : {str(exc)[:120]}"}

    fiche = {
        "connecte": True,
        "identifiant": moi.get("username"),
        "type": moi.get("account_type"),
        "publications": moi.get("media_count"),
        "detail": "",
    }
    # Les abonnes ne viennent pas de `me` : il faut les demander.
    try:
        d = _appel("GET", "me", fields="followers_count,follows_count")
        fiche["abonnes"] = d.get("followers_count")
        fiche["abonnements"] = d.get("follows_count")
    except Exception:                                          # noqa: BLE001
        pass
    return fiche


def _vraie_valeur(v: str | None) -> str | None:
    """Ecarte les valeurs d'exemple jamais remplacees.

    `.env.example` remplit les cles absentes par « your_... », et la
    convention est suivie dans tout le depot (voir `GenerateurImages`).
    Sans ce filtre, l'ecran annoncait fierement l'identifiant TikTok
    « your_tiktok_email ».
    """
    if not v or v.strip().lower().startswith("your_"):
        return None
    return v.strip()


def tiktok() -> dict:
    """TikTok n'est pas branche, et il faut le dire honnetement.

    Leur API de publication exige que l'application soit VALIDEE par
    leurs equipes, ce qui prend plusieurs jours. Afficher « bientot »
    serait une promesse ; afficher ce qui manque est utile.
    """
    return {
        "connecte": False,
        "identifiant": _vraie_valeur(os.environ.get("TIKTOK_USERNAME")),
        "detail": "l'application doit etre validee par TikTok avant "
                  "toute publication automatique (plusieurs jours)",
    }


def deposer(etat: dict) -> str:
    base = os.environ["SUPABASE_URL"].rstrip("/")
    cle = os.environ["SUPABASE_SERVICE_KEY"]
    corps = json.dumps(etat, ensure_ascii=False, indent=1).encode()
    for methode in ("POST", "PUT"):
        req = urllib.request.Request(
            f"{base}/storage/v1/object/{SEAU}/{FICHIER}",
            data=corps, method=methode,
            headers={"apikey": cle, "Authorization": f"Bearer {cle}",
                     "Content-Type": "application/json",
                     "x-upsert": "true"})
        try:
            urllib.request.urlopen(req, timeout=40).close()
            break
        except urllib.error.HTTPError as e:
            if methode == "PUT":
                raise RuntimeError(
                    f"depot refuse : {e.read().decode()[:200]}") from e
    return f"{base}/storage/v1/object/public/{SEAU}/{FICHIER}"


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    etat = {
        "vu_le": dt.datetime.now(dt.timezone.utc).isoformat(),
        "instagram": instagram(),
        "tiktok": tiktok(),
    }
    url = deposer(etat)
    ig = etat["instagram"]
    log.info("Instagram : %s", "@" + str(ig.get("identifiant"))
             if ig.get("connecte") else "non connecte")
    log.info("depose : %s", url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
