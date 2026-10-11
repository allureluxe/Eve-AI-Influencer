"""Dépose la boutique de Noël (docs/kit/noel/) sur alluxe.fr.

    python3 ops/publier_boutique_noel.py            # alluxe.fr/apercu/noel/ (pour relire)
    python3 ops/publier_boutique_noel.py --en-ligne # alluxe.fr/noel/ (sur accord de l'opérateur)

Séparé de publier_site_alluxe.py : la boutique est un dossier à part, et la
republier ne doit pas redéposer tout le site (ni l'inverse).
"""
from __future__ import annotations

import ftplib
import os
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
SOURCE = RACINE / "docs" / "kit" / "noel"
EXTENSIONS = {".html", ".css", ".js", ".json", ".jpg", ".png"}


def _entrer(ftp: ftplib.FTP, nom: str) -> None:
    try:
        ftp.mkd(nom)
    except ftplib.error_perm:
        pass
    ftp.cwd(nom)


def main() -> int:
    sys.path.insert(0, str(RACINE))
    from gold_bot.env import charger_env
    charger_env()
    ftp = ftplib.FTP(os.environ["OVH_FTP_HOST"], timeout=60)
    ftp.login(os.environ["OVH_FTP_USER"], os.environ["OVH_FTP_PASSWORD"])
    ftp.cwd("www")
    chemin = "noel/" if "--en-ligne" in sys.argv else "apercu/noel/"
    for morceau in chemin.strip("/").split("/"):
        _entrer(ftp, morceau)
    for f in sorted(SOURCE.iterdir()):
        if f.suffix in EXTENSIONS:
            with open(f, "rb") as fh:
                ftp.storbinary(f"STOR {f.name}", fh)
            print(f"déposé : {chemin}{f.name}")
    ftp.quit()
    print(f"https://alluxe.fr/{chemin}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
