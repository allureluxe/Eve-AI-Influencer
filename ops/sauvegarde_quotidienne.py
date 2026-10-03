"""Sauvegarde quotidienne des donnees du robot HORS du serveur.

3 oct. 2026 : il n'y en avait aucune. Un disque perdu emportait le journal
des trades reels, les prix d'entree et les stops des positions ouvertes
(position_meta), l'etat des demos et tout le carnet du Lab.

Archive compressee -> espace de stockage PRIVE Supabase « sauvegardes »,
14 jours gardes. Ne contient AUCUN secret : .env et secrets/ sont exclus
par construction (liste blanche de fichiers).

    python3 ops/sauvegarde_quotidienne.py          # cron, 03h40
"""
from __future__ import annotations

import datetime as dt
import glob
import io
import json
import os
import sys
import tarfile
import urllib.request
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))

BUCKET = "sauvegardes"
GARDER_JOURS = 14
#: Liste BLANCHE : seuls ces fichiers partent. Jamais .env, jamais secrets/.
MOTIFS = ["data/state*.json", "data/trades*.jsonl", "data/journal*.jsonl",
          "data/objectives*.json", "data/lab-book.jsonl", "data/lab-state.json",
          "data/demo2-strategy.json", "data/chien_de_garde_reference.json",
          "robot*.json"]


def fichiers() -> list[Path]:
    vus = []
    for motif in MOTIFS:
        for f in sorted(glob.glob(str(RACINE / motif))):
            p = Path(f)
            if p.is_file() and ".env" not in p.name and "secret" not in str(p).lower():
                vus.append(p)
    return vus


def archive(liste: list[Path]) -> bytes:
    tampon = io.BytesIO()
    with tarfile.open(fileobj=tampon, mode="w:gz") as tar:
        for p in liste:
            tar.add(p, arcname=str(p.relative_to(RACINE)))
    return tampon.getvalue()


def _appel(url: str, cle: str, methode: str = "GET", corps: bytes | None = None,
           type_: str = "application/json", extra: dict | None = None):
    h = {"apikey": cle, "authorization": f"Bearer {cle}", "content-type": type_}
    h.update(extra or {})
    with urllib.request.urlopen(urllib.request.Request(url, data=corps, method=methode, headers=h),
                                timeout=120) as r:
        brut = r.read()
        return json.loads(brut) if brut[:1] in (b"{", b"[") else brut


def main() -> int:
    from gold_bot.env import charger_env
    charger_env()
    url = os.environ["SUPABASE_URL"].rstrip("/")
    cle = os.environ["SUPABASE_SERVICE_KEY"]
    try:
        _appel(f"{url}/storage/v1/bucket", cle, "POST",
               json.dumps({"id": BUCKET, "name": BUCKET, "public": False}).encode())
    except urllib.error.HTTPError:
        pass  # deja cree
    liste = fichiers()
    donnees = archive(liste)
    nom = dt.date.today().isoformat() + ".tar.gz"
    _appel(f"{url}/storage/v1/object/{BUCKET}/{nom}", cle, "POST", donnees,
           "application/gzip", {"x-upsert": "true"})
    # Menage : on ne garde que les GARDER_JOURS dernieres.
    objets = _appel(f"{url}/storage/v1/object/list/{BUCKET}", cle, "POST",
                    json.dumps({"prefix": "", "limit": 1000}).encode())
    limite = dt.date.today() - dt.timedelta(days=GARDER_JOURS)
    vieux = [o["name"] for o in objets if o.get("name", "")[:10] < limite.isoformat()]
    if vieux:
        _appel(f"{url}/storage/v1/object/{BUCKET}", cle, "DELETE",
               json.dumps({"prefixes": vieux}).encode())
    print(f"sauvegarde {nom} : {len(liste)} fichiers, {len(donnees) / 1048576:.1f} Mo ; "
          f"{len(vieux)} ancienne(s) effacee(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
