"""Prévient les moteurs IndexNow (Bing, Yandex, Seznam… et ceux qui lisent Bing :
DuckDuckGo, Yahoo, Ecosia, ChatGPT Search) que les pages d'alluxe.fr ont changé.

    python3 ops/indexnow.py            # toutes les pages du sitemap

Appelé à la fin de ops/publier_site_alluxe.py (vrai site seulement, pas l'aperçu).
La clé est le fichier docs/kit/<clé>.txt déposé à la racine du site (13 oct. 2026) :
c'est elle qui prouve aux moteurs que la demande vient bien du propriétaire.
Google n'utilise pas IndexNow : pour lui, c'est la Search Console et le sitemap.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "docs" / "kit"
HOTE = "alluxe.fr"


def cle() -> str:
    for f in SOURCE.glob("*.txt"):
        if re.fullmatch(r"[0-9a-f]{32}", f.stem) and f.read_text().strip() == f.stem:
            return f.stem
    raise SystemExit("clé IndexNow introuvable dans docs/kit/")


def pages() -> list[str]:
    return re.findall(r"<loc>([^<]+)</loc>", (SOURCE / "sitemap.xml").read_text())


def main() -> int:
    k = cle()
    corps = {"host": HOTE, "key": k, "keyLocation": f"https://{HOTE}/{k}.txt", "urlList": pages()}
    req = urllib.request.Request("https://api.indexnow.org/indexnow", data=json.dumps(corps).encode(),
                                 headers={"Content-Type": "application/json; charset=utf-8"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print(f"IndexNow : {len(corps['urlList'])} pages signalées (réponse {r.status})")
    except Exception as e:                      # ne jamais faire échouer une publication pour ça
        print(f"IndexNow : non signalé ({e})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
