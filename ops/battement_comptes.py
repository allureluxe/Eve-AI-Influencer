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

from gold_bot.env import charger_env                          # noqa: E402
from gold_bot.methode import phrase_methode, resume_methode   # noqa: E402
from gold_bot.settings import BotConfig                        # noqa: E402

# CRON N'HERITE D'AUCUN ENVIRONNEMENT. Premiere version de ce fichier :
# la tache tournait toutes les cinq minutes et echouait a chaque fois sur
# « identifiants Supabase absents » -- donc le pouls qu'elle devait
# retablir n'a jamais battu, et les comptes seraient restes affiches
# « arretes ».
#
# C'est la meme famille de piege que le chien de garde du 31 aout
# (chemin relatif sans `cd`, donc jamais execute) : un travail planifie
# qui echoue en silence ressemble exactement a un travail qui n'existe
# pas. Tous les autres scripts d'`ops/` appellent `charger_env()` pour
# cette raison.
charger_env()

log = logging.getLogger("battement")

COMPTES = {
    "demo": "robot.demo.json",
    "demo2": "robot.demo2.json",
}


#: Les cours de TOUS les marches, lus une fois par passage.
#: Un appel par crypto sur 24 positions, c'est 24 allers-retours pour
#: une donnee que Bitvavo rend entiere en un seul.
_CACHE: dict[str, float] = {}


def _charger_les_cours() -> None:
    """Le CARNET D'ORDRES, pas le prix du dernier echange.

    CINQUIEME ENDROIT OU CETTE MEME ERREUR SE REPETE. Ce script lisait
    `/ticker/price`, qui rend le prix de la derniere TRANSACTION : sur
    un marche peu echange il ne bouge pas tant que personne n'echange,
    et il affiche alors un cours vieux d'une heure.

    Le robot (20 sept.) et l'application (21 sept.) ont deja ete
    corriges. Ce script-ci a ete ecrit AVANT la decouverte et n'a pas
    ete repris -- d'ou l'ecart vu par l'operateur le 22 :

        verite (carnet)                   3 716,22 EUR
        gros chiffre de l'application     3 714,91 EUR   juste
        courbe et fiche du serveur        3 553,61 EUR   162 de moins

    Corriger la formule ne suffit jamais : il faut corriger TOUS ceux
    qui la calculent. C'est la lecon qui revient depuis le 18 septembre.
    """
    global _CACHE
    try:
        with urllib.request.urlopen(
                "https://api.bitvavo.com/v2/ticker/book", timeout=25) as r:
            lignes = json.loads(r.read().decode())
    except Exception:                                          # noqa: BLE001
        return
    out: dict[str, float] = {}
    for l in lignes:
        try:
            b = float(l.get("bid") or 0)
            a = float(l.get("ask") or 0)
            v = (b + a) / 2 if b > 0 and a > 0 else (b or a)
            if v > 0:
                out[str(l["market"]).split("-")[0]] = v
        except (KeyError, TypeError, ValueError):
            continue
    if out:
        _CACHE = out


def _cours(actif: str) -> float | None:
    if not _CACHE:
        _charger_les_cours()
    return _CACHE.get(actif)


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
    # LE CAPITAL VA MAINTENANT EN BASE.
    #
    # Il n'y allait pas le 21 septembre : la colonne n'existait pas
    # (PGRST204) et le jeton d'administration avait expire, donc aucune
    # migration ne passait. Consequence visible pour l'operateur : le
    # capital affiche sur l'onglet demo qu'on NE regarde PAS ne comptait
    # que les trades fermes -- il ignorait toutes les positions
    # ouvertes, et paraissait fige.
    #
    # Le jeton a ete regenere le 22 ; la colonne et la table
    # d'historique existent.
    capital = capital_du_compte(compte)
    if capital is not None:
        corps["capital_eur"] = round(capital, 2)

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
    # UN RELEVE DE PLUS DANS L'HISTORIQUE, pour la courbe.
    #
    # Une ligne toutes les cinq minutes et par compte : c'est peu de
    # donnees, et c'est ce qui permet de tracer 1 jour, 7 jours, 30
    # jours et 1 an. Sans releve regulier, aucune courbe n'est possible
    # -- on ne peut pas reconstituer apres coup une valeur qu'on n'a
    # jamais enregistree.
    #
    # L'echec n'est pas fatal : mieux vaut un trou dans la courbe qu'un
    # pouls perdu.
    if capital is not None:
        try:
            r = urllib.request.Request(
                f"{url}/rest/v1/alluxe_bot_capital",
                data=json.dumps({"compte": compte,
                                 "capital_eur": round(capital, 2)}).encode(),
                headers={"apikey": cle, "authorization": f"Bearer {cle}",
                         "content-type": "application/json"},
                method="POST")
            urllib.request.urlopen(r, timeout=20).close()
        except Exception as exc:                               # noqa: BLE001
            log.warning("releve de capital non enregistre : %s", str(exc)[:120])

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
