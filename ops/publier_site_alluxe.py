"""Depose le site public alluxe.fr (page du kit) sur l'hebergement OVH.

    python3 ops/publier_site_alluxe.py

Domaine achete par l'operateur le 4 oct. 2026, hebergement gratuit OVH
« Start 10M » (FTP seulement, pas de TLS). Le site est separe de l'appli
privee (GitHub Pages) : rien de prive ne doit venir ici. Sources : docs/kit/.
Identifiants dans .env : OVH_FTP_HOST, OVH_FTP_USER, OVH_FTP_PASSWORD.
"""
from __future__ import annotations

import ftplib
import os
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
SOURCE = RACINE / "docs" / "kit"
FICHIERS = ("index.html", "kit-constructeur.pdf", "alluxe.jpg")


def main() -> int:
    sys.path.insert(0, str(RACINE))
    from gold_bot.env import charger_env
    charger_env()
    ftp = ftplib.FTP(os.environ["OVH_FTP_HOST"], timeout=60)
    ftp.login(os.environ["OVH_FTP_USER"], os.environ["OVH_FTP_PASSWORD"])
    ftp.cwd("www")
    for nom in FICHIERS:
        with open(SOURCE / nom, "rb") as fh:
            ftp.storbinary(f"STOR {nom}", fh)
        print(f"depose : {nom}")
    ftp.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
