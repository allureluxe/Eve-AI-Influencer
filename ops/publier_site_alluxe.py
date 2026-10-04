"""Dépose le site public alluxe.fr sur l'hébergement OVH.

    python3 ops/publier_site_alluxe.py            # le vrai site (www/)
    python3 ops/publier_site_alluxe.py --apercu   # une copie à alluxe.fr/apercu/, pour relire

Domaine acheté par l'opérateur le 4 oct. 2026, hébergement gratuit OVH
« Start 10M » (FTP seulement). Le site est séparé de l'appli privée (GitHub
Pages) : rien de privé ne doit venir ici. Sources : docs/kit/.
La bibliothèque de prompts (prompts.json) et les aperçus sont reconstruits
depuis les publications avant chaque dépôt (alluxe_ia/site.py).
Identifiants dans .env : OVH_FTP_HOST, OVH_FTP_USER, OVH_FTP_PASSWORD.
"""
from __future__ import annotations

import ftplib
import os
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
SOURCE = RACINE / "docs" / "kit"
FICHIERS = ["index.html", "kit-constructeur.pdf", "alluxe.jpg", "logo-alluxe.png"]


def _dossier(ftp: ftplib.FTP, nom: str) -> None:
    try:
        ftp.mkd(nom)
    except ftplib.error_perm:
        pass                                   # il existe déjà


def main() -> int:
    sys.path.insert(0, str(RACINE))
    from gold_bot.env import charger_env
    from alluxe_ia.site import construire
    charger_env()
    fichiers = FICHIERS + construire()
    apercu = "--apercu" in sys.argv
    ftp = ftplib.FTP(os.environ["OVH_FTP_HOST"], timeout=60)
    ftp.login(os.environ["OVH_FTP_USER"], os.environ["OVH_FTP_PASSWORD"])
    ftp.cwd("www")
    if apercu:
        _dossier(ftp, "apercu")
        ftp.cwd("apercu")
    _dossier(ftp, "apercus")
    for nom in fichiers:
        with open(SOURCE / nom, "rb") as fh:
            ftp.storbinary(f"STOR {nom}", fh)
        print(f"déposé : {'apercu/' if apercu else ''}{nom}")
    ftp.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
