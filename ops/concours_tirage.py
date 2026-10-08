"""Tirage au sort du concours de Noël @alluxe.ia (règlement : alluxe.fr/concours, art. 4).

    python3 ops/concours_tirage.py liste  LIEN_OU_ID_DU_POST [--tiktok participants.txt]
    python3 ops/concours_tirage.py tirer  LIEN_OU_ID_DU_POST [--tiktok participants.txt]

`liste` montre les participations sans rien tirer (à lancer avant, pour vérifier).
`tirer` tire 1 gagnant + 2 suppléants, À FILMER pour la story.

Règles appliquées (et seulement celles-là) :
  - chaque commentaire qui identifie AU MOINS 2 comptes DIFFÉRENTS (pas soi-même, pas
    @alluxe.ia) vaut UNE participation ; les réponses aux commentaires comptent aussi ;
  - le compte organisateur est exclu ;
  - TikTok : l'API ne lit pas les commentaires -> l'opérateur colle les participations
    dans un fichier texte, une par ligne : « pseudo @ami1 @ami2 ».
L'abonnement du gagnant n'est PAS vérifiable par programme (Instagram ne donne pas la
liste des abonnés) : l'opérateur le vérifie avant l'annonce, sinon on passe au suppléant.

Le hasard vient de `secrets` (générateur du système, non prévisible). L'empreinte SHA-256
de la liste triée est affichée et enregistrée : elle prouve après coup que la liste n'a
pas été retouchée. Résultat gardé dans data/alluxe_ia/concours/.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import secrets
import sys
import urllib.parse
import urllib.request

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
IG = "17841461765610508"
ORGANISATEUR = "alluxe.ia"
GRAPH = "https://graph.facebook.com/v21.0"
MENTION = re.compile(r"@([A-Za-z0-9_.]{1,30})")


def _graph(chemin: str, **p) -> dict:
    p["access_token"] = os.environ["INSTAGRAM_FB_TOKEN"]
    with urllib.request.urlopen(f"{GRAPH}/{chemin}?" + urllib.parse.urlencode(p), timeout=60) as r:
        return json.load(r)


def _id_du_post(lien_ou_id: str) -> str:
    if lien_ou_id.isdigit():
        return lien_ou_id
    code = re.search(r"/(?:p|reel)/([^/?]+)", lien_ou_id)
    if not code:
        raise SystemExit("lien Instagram non reconnu")
    suivant = f"{IG}/media"
    params = {"fields": "id,permalink", "limit": 50}
    while suivant:
        page = _graph(suivant, **params)
        for m in page.get("data", []):
            if code.group(1) in (m.get("permalink") or ""):
                return m["id"]
        suivant = (page.get("paging") or {}).get("next", "").replace(GRAPH + "/", "") or None
        params = {}
    raise SystemExit("post introuvable sur @alluxe.ia")


def _commentaires(media_id: str) -> list[dict]:
    sortie, apres = [], None
    while True:
        p = {"fields": "id,username,text,timestamp,replies{id,username,text,timestamp}", "limit": 50}
        if apres:
            p["after"] = apres
        page = _graph(f"{media_id}/comments", **p)
        for c in page.get("data", []):
            sortie.append(c)
            sortie.extend((c.get("replies") or {}).get("data", []))
        apres = (page.get("paging") or {}).get("cursors", {}).get("after") if (page.get("paging") or {}).get("next") else None
        if not apres:
            return sortie


def participations(media_id: str, fichier_tiktok: str | None) -> list[dict]:
    brutes = [{"reseau": "instagram", "compte": c.get("username", ""), "texte": c.get("text", ""), "id": c["id"]}
              for c in _commentaires(media_id)]
    if fichier_tiktok:
        with open(fichier_tiktok, encoding="utf-8") as f:
            for i, ligne in enumerate(l.strip() for l in f if l.strip()):
                compte, _, reste = ligne.partition(" ")
                brutes.append({"reseau": "tiktok", "compte": compte.lstrip("@"), "texte": reste, "id": f"tiktok-{i}"})
    valides = []
    for b in brutes:
        compte = b["compte"].lower()
        if compte == ORGANISATEUR:
            continue
        amis = {m.lower() for m in MENTION.findall(b["texte"])} - {compte, ORGANISATEUR}
        if len(amis) >= 2:
            valides.append({**b, "amis": sorted(amis)})
    return valides


def empreinte(valides: list[dict]) -> str:
    lignes = sorted(f"{v['reseau']}|{v['id']}|{v['compte']}|{','.join(v['amis'])}" for v in valides)
    return hashlib.sha256("\n".join(lignes).encode()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("action", choices=["liste", "tirer"])
    ap.add_argument("post")
    ap.add_argument("--tiktok")
    a = ap.parse_args()
    from gold_bot.env import charger_env
    charger_env()
    valides = participations(_id_du_post(a.post), a.tiktok)
    comptes = sorted({v["compte"] for v in valides})
    print(f"\n🎁 Concours de Noël @alluxe.ia — {len(valides)} participation(s), {len(comptes)} participant(s)")
    print(f"   empreinte de la liste : {empreinte(valides)[:16]}…")
    if a.action == "liste":
        for v in valides:
            print(f"   {v['reseau']:9} @{v['compte']:24} -> " + " ".join("@" + x for x in v["amis"]))
        return 0
    if len(comptes) < 3:
        raise SystemExit("moins de 3 participants distincts : pas de tirage possible")
    hasard = secrets.SystemRandom()
    tires: list[str] = []
    while len(tires) < 3:                       # chaque PARTICIPATION a la même chance ;
        c = hasard.choice(valides)["compte"]    # un même compte ne gagne qu'une fois
        if c not in tires:
            tires.append(c)
    print(f"\n   🏆 GAGNANT    : @{tires[0]}")
    print(f"   suppléant 1 : @{tires[1]}\n   suppléant 2 : @{tires[2]}")
    print("\n   → Vérifie que le gagnant est abonné à @alluxe.ia avant de l'annoncer.")
    os.makedirs(os.path.join(RACINE, "data", "alluxe_ia", "concours"), exist_ok=True)
    trace = os.path.join(RACINE, "data", "alluxe_ia", "concours",
                         dt.datetime.now().strftime("tirage-%Y%m%d-%H%M%S.json"))
    with open(trace, "w", encoding="utf-8") as f:
        json.dump({"le": dt.datetime.now(dt.timezone.utc).isoformat(), "post": a.post,
                   "empreinte": empreinte(valides), "participations": valides,
                   "gagnant": tires[0], "suppleants": tires[1:]}, f, ensure_ascii=False, indent=1)
    print(f"   trace : {os.path.relpath(trace, RACINE)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
