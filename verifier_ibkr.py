#!/usr/bin/env python3
"""Verifie, etape par etape, ce qui manque a la connexion IBKR.

    python3 verifier_ibkr.py

Le robot ne peut pas s'authentifier a votre place : IBKR exige un second
facteur (code recu par SMS) qui n'existe que sur votre telephone. Ce script
ne remplace donc pas cette etape — il dit precisement OU ca coince, pour ne
pas avoir a deviner en lisant des journaux.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gold_bot.env import charger_env
from gold_bot.ibkr_readiness import (DEPENDANCE_ABSENTE, HORS_LIGNE,
                                     NON_AUTHENTIFIE, PRETE, etat_passerelle)

# IBKR_HOST, IBKR_PORT et IBKR_TRADING_LIVE viennent du .env.
charger_env()

VERT, ROUGE, JAUNE, GRAS, FIN = "\033[32m", "\033[31m", "\033[33m", "\033[1m", "\033[0m"


def ligne(ok: bool | None, texte: str) -> None:
    marque = f"{VERT}OK  {FIN}" if ok else (f"{ROUGE}NON {FIN}" if ok is False else f"{JAUNE}?   {FIN}")
    print(f"  [{marque}] {texte}")


def main() -> int:
    host = os.getenv("IBKR_HOST", "127.0.0.1")
    port = int(os.getenv("IBKR_PORT", "4001"))
    live = os.getenv("IBKR_TRADING_LIVE", "0").strip().lower() in {"1", "true", "yes", "oui"}

    print(f"\n{GRAS}Verification de la connexion IBKR{FIN}")
    print(f"  passerelle attendue : {host}:{port}"
          f"   ({'4001 = reel' if port == 4001 else '4002 = papier' if port == 4002 else 'port inhabituel'})")
    print()

    etat = etat_passerelle(host, port)

    ligne(etat.etat != DEPENDANCE_ABSENTE, "la bibliotheque ib_async est installee")
    ligne(etat.etat != HORS_LIGNE, f"un IB Gateway ecoute sur {host}:{port}")
    ligne(etat.etat == PRETE, "la session IBKR est authentifiee (identifiant + code SMS)")
    ligne(bool(etat.comptes), f"un compte est visible : {', '.join(etat.comptes) or 'aucun'}")
    ligne(live, "le trading reel est arme (IBKR_TRADING_LIVE=1)")

    print(f"\n{GRAS}Verdict{FIN}\n  {etat.resume()}\n")

    if etat.etat == DEPENDANCE_ABSENTE:
        print(f"{GRAS}A faire{FIN}")
        print("  pip install 'ib_async>=2.0,<3'    (dans le venv du robot)")
        return 1

    if etat.etat == HORS_LIGNE:
        print(f"{GRAS}A faire — le Gateway n'est pas lance{FIN}")
        print("  1. Ouvrir IB Gateway sur la machine qui heberge le robot.")
        print("  2. Choisir le mode « IB API », puis « Live Trading » pour le port 4001")
        print("     (« Paper Trading » ecoute sur 4002 : c'est un autre compte).")
        print("  3. Saisir identifiant et mot de passe.")
        print(f"  4. {GRAS}IBKR envoie alors un code par SMS sur votre telephone.{FIN}")
        print("     Le saisir dans la fenetre du Gateway. Sans lui, rien ne s'ouvre.")
        print("  5. Relancer ce script.")
        return 1

    if etat.etat == NON_AUTHENTIFIE:
        print(f"{GRAS}A faire — le Gateway tourne mais ne repond pas a l'API{FIN}")
        print(f"  {GRAS}Cause la plus frequente : le code SMS n'a pas ete saisi.{FIN}")
        print("  Regarder l'ecran du Gateway : s'il demande un « security code »,")
        print("  c'est exactement la que le robot est bloque.")
        print()
        print("  Si la session est bien ouverte, verifier dans le Gateway :")
        print("    Configure > Settings > API > Settings")
        print("      - « Enable ActiveX and Socket Clients »  doit etre COCHE")
        print("      - « Read-Only API »                      doit etre DECOCHE")
        print(f"      - « Socket port »                        doit valoir {port}")
        print("      - « Trusted IPs » doit contenir 127.0.0.1")
        print()
        print("  Verifier aussi qu'aucune autre session n'utilise le meme clientId,")
        print("  et qu'une connexion au portail web IBKR ne vous a pas deconnecte :")
        print("  IBKR n'autorise qu'une session a la fois par identifiant.")
        return 1

    if not live:
        print(f"{GRAS}Presque{FIN}  La passerelle repond, mais IBKR_TRADING_LIVE=0 :")
        print("  le robot lira le compte sans jamais passer d'ordre.")
        print("  Passer a 1 dans .env quand vous voudrez engager de l'argent.")
        return 0

    print(f"{VERT}{GRAS}Tout est en place : le moteur IBKR peut demarrer.{FIN}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
