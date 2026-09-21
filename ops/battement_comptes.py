#!/usr/bin/env python3
"""Publie le pouls et le capital des comptes demo, sans toucher aux robots.

POURQUOI CE FICHIER EXISTE, ET POURQUOI IL EST TEMPORAIRE
=========================================================

L'application declare un compte « arrete » quand sa fiche
(`alluxe_bot_comptes.vu_le`) n'a pas ete rafraichie depuis un quart
d'heure. Or `run_demo.py` ne la publiait qu'au DEMARRAGE : les deux
robots etaient donc affiches arretes en permanence alors qu'ils
tournaient. Constate le 21 septembre :

    demo    vu_le = la veille 13h14   (20 heures)
    demo2   vu_le = 05h43             (3 h 30)

Un voyant toujours rouge ne dit plus rien. On cesse de le regarder, et
le jour ou un robot tombe vraiment, personne ne le voit.

`run_demo.py` republie desormais sa fiche toutes les cinq minutes --
mais cela n'entrera en vigueur qu'a son prochain demarrage, et
l'operateur a demande le 20 septembre que les deux comptes tournent
JUSQU'AU 28 SANS QUE RIEN NE SOIT TOUCHE. Ce script fait donc le travail
depuis l'exterieur, en lisant les fichiers d'etat : aucun redemarrage,
aucune interruption.

    A SUPPRIMER apres le premier redemarrage des robots, le 28. Le
    battement interne fera alors double emploi.

Il calcule aussi le capital vivant de chaque compte et le journalise --
utile pour verifier d'un coup d'oeil ce que vaut une simulation sans
ouvrir l'application. Il ne l'ECRIT pas en base : la table n'a pas de
colonne pour ca.
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

from gold_bot.methode import phrase_methode, resume_methode   # noqa: E402
from gold_bot.settings import BotConfig                        # noqa: E402

log = logging.getLogger("battement")

COMPTES = {
    "demo": "robot.demo.json",
    "demo2": "robot.demo2.json",
}


def _cours(actif: str) -> float | None:
    """Le cours en euros, chez le courtier du robot."""
    try:
        with urllib.request.urlopen(
                f"https://api.bitvavo.com/v2/ticker/price?market={actif}-EUR",
                timeout=10) as r:
            return float(json.loads(r.read().decode())["price"])
    except Exception:                                          # noqa: BLE001
        return None


def capital_du_compte(compte: str) -> float | None:
    """Le capital VIVANT : liquide + gain latent des positions ouvertes.

    C'est la definition du simulateur (`PaperBroker.account`) : la valeur
    achetee n'est jamais debitee du solde, seul le gain flottant compte.
    Additionner le solde ET la valeur des positions reviendrait a compter
    l'argent deux fois -- erreur commise le 21 septembre, qui annoncait
    6 120 EUR sur un compte de 3 300.
    """
    chemin = Path(f"data/state-{compte}.json")
    if not chemin.exists():
        return None
    try:
        etat = json.loads(chemin.read_text())
    except Exception:                                          # noqa: BLE001
        return None
    solde = etat.get("solde_simule")
    if solde is None:
        return None
    latent = 0.0
    for p in (etat.get("position_meta") or {}).values():
        actif = p.get("symbol", "").replace("USD", "").replace("EUR", "")
        prix = _cours(actif)
        if prix is None:
            continue
        signe = -1.0 if str(p.get("side", "")).upper().endswith("SELL") else 1.0
        latent += signe * p.get("volume", 0.0) * (prix - p.get("entry_price", 0.0))
    return float(solde) + latent


def publier(compte: str, fichier: str) -> bool:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    cle = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not url or not cle:
        log.warning("identifiants Supabase absents")
        return False
    try:
        cfg = BotConfig.load(fichier)
    except Exception as exc:                                   # noqa: BLE001
        log.warning("%s illisible : %s", fichier, str(exc)[:120])
        return False

    corps = {
        "compte": compte,
        "resume_methode": resume_methode(cfg),
        "methode": phrase_methode(cfg),
        "capital_depart": float(getattr(cfg.engine, "start_balance", 0.0) or 0.0),
        "vu_le": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
    # Le capital est calcule pour le JOURNAL, pas pour la base : la table
    # n'a pas de colonne pour lui (PGRST204, verifie le 21 septembre), et
    # un champ inconnu fait echouer toute la requete en 400 -- le pouls
    # serait perdu avec lui.
    capital = capital_du_compte(compte)

    try:
        requete = urllib.request.Request(
            f"{url}/rest/v1/alluxe_bot_comptes",
            data=json.dumps(corps).encode(),
            headers={"apikey": cle, "authorization": f"Bearer {cle}",
                     "content-type": "application/json",
                     "prefer": "resolution=merge-duplicates"},
            method="POST")
        urllib.request.urlopen(requete, timeout=20).close()
    except Exception as exc:                                   # noqa: BLE001
        log.warning("fiche « %s » non publiee : %s", compte, str(exc)[:160])
        return False
    log.info("fiche « %s » publiee — capital %s",
             compte, f"{capital:.2f} EUR" if capital is not None else "inconnu")
    return True


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    # ON NE PUBLIE QUE POUR UN ROBOT QUI TOURNE VRAIMENT. Sinon ce script
    # maintiendrait le voyant au vert sur un compte mort, ce qui est pire
    # que le defaut qu'il corrige.
    import subprocess
    ok = 0
    for compte, fichier in COMPTES.items():
        actif = subprocess.run(
            ["systemctl", "is-active", f"robot-{compte}"],
            capture_output=True, text=True).stdout.strip() == "active"
        if not actif:
            log.info("robot-%s n'est pas actif : fiche non rafraichie", compte)
            continue
        ok += 1 if publier(compte, fichier) else 0
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
