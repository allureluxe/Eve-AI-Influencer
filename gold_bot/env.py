"""Chargement du fichier .env pour les commandes lancees a la main.

POURQUOI CE MODULE EXISTE
-------------------------
Le service systemd lit les secrets via `EnvironmentFile=/…/.env`. Une
commande tapee dans un terminal, elle, ne lit rien du tout : les cles sont
sur le disque, le robot ne les voit pas, et le message d'erreur parle de
cles « absentes » alors qu'elles sont la.

Observe : `pourquoi_pas_de_trade.py` refusait de demarrer sur
« BITVAVO_API_KEY et BITVAVO_API_SECRET absents » avec un .env complet a
cote. Le diagnostic censé expliquer pourquoi le robot ne trade pas ne
pouvait lui-meme pas se connecter.

Regle : l'environnement DEJA POSE l'emporte toujours. Un
`BITVAVO_DRY_RUN=1 python3 …` en ligne de commande doit rester plus fort
que le fichier — sans quoi on croirait simuler tout en engageant de
l'argent.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

RACINE = Path(__file__).resolve().parent.parent


def charger_env(chemin: str | os.PathLike | None = None) -> int:
    """Pose dans l'environnement les cles du .env qui n'y sont pas deja.

    Retourne le nombre de variables ajoutees. Ne leve jamais : un fichier
    absent ou illisible ne doit pas empecher une commande de tourner, il
    doit seulement se voir dans le journal.
    """
    fichier = Path(chemin) if chemin else RACINE / ".env"
    if not fichier.is_file():
        logger.debug("aucun fichier .env a %s", fichier)
        return 0

    ajoutees = 0
    try:
        for ligne in fichier.read_text(encoding="utf-8", errors="replace").splitlines():
            ligne = ligne.strip()
            if not ligne or ligne.startswith("#") or "=" not in ligne:
                continue
            cle, _, valeur = ligne.partition("=")
            cle = cle.strip()
            if cle.startswith("export "):
                cle = cle[len("export "):].strip()
            if not cle or cle in os.environ:
                # Deja pose : la ligne de commande l'emporte sur le fichier.
                continue
            valeur = valeur.strip()
            # Retire les guillemets englobants, pas ceux du contenu.
            if len(valeur) >= 2 and valeur[0] == valeur[-1] and valeur[0] in "\"'":
                valeur = valeur[1:-1]
            os.environ[cle] = valeur
            ajoutees += 1
    except OSError as exc:
        logger.warning("fichier .env illisible (%s) : %s", fichier, exc)
        return ajoutees

    if ajoutees:
        logger.info("%d variable(s) chargee(s) depuis %s", ajoutees, fichier)
    return ajoutees
