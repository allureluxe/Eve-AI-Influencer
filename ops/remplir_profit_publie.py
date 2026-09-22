#!/usr/bin/env python3
"""Pose le benefice REEL sur les trades deja fermes.

POURQUOI
========

Jusqu'au 22 septembre 2026, l'application reconstituait le benefice d'un
trade ferme a partir du pourcentage publie :

    gain = volume x prix d'achat x result_pct / 100

C'est le gain du PRIX. Il ignore les frais que le robot a pourtant
payes, et il herite des arrondis du pourcentage. Releve par l'operateur
en comparant ses ecrans au serveur : la demo 2 affichait **128,28 EUR
encaisses** pour **117,08** reels — 7,93 de frais, 3,27 d'arrondis, sur
sept trades seulement.

Le robot ecrit desormais `signals.profit_eur` a chaque cloture. Mais les
lignes DEJA fermees ne l'ont pas, et l'operateur verrait un chiffre faux
jusqu'a ce que tout l'historique ait roule. Ce script comble le passe
depuis `data/trades-<compte>.jsonl`, qui porte le profit exact.

UNE SEULE LIGNE PAR POSITION
============================

Une pyramide publie une ligne par etage et elles se ferment toutes
ensemble. Le benefice appartient a la POSITION, pas a l'etage : on le
pose sur l'etage 1 et on met zero sur les suivants, sinon l'application
— qui additionne les lignes — compterait une pyramide a quatre etages
quatre fois.

    python3 ops/remplir_profit_publie.py --compte demo2
    python3 ops/remplir_profit_publie.py --compte demo2 --appliquer
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gold_bot.env import charger_env   # noqa: E402

charger_env()
log = logging.getLogger("profit-publie")


def _entetes() -> tuple[str, dict]:
    base = os.environ["SUPABASE_URL"].rstrip("/")
    cle = os.environ["SUPABASE_SERVICE_KEY"]
    return base, {"apikey": cle, "Authorization": f"Bearer {cle}",
                  "Content-Type": "application/json"}


def trades(compte: str) -> dict[str, dict]:
    """Le profit exact, par identifiant de position."""
    f = Path(f"data/trades-{compte}.jsonl")
    if not f.exists():
        return {}
    out: dict[str, dict] = {}
    for ligne in f.read_text().splitlines():
        if not ligne.strip():
            continue
        try:
            t = json.loads(ligne)
        except Exception:                                  # noqa: BLE001
            continue
        if t.get("partial"):
            # Une sortie partielle n'est pas la fin du trade : son
            # profit est deja compris dans la ligne finale.
            continue
        pid = t.get("position_id")
        if pid:
            out[str(pid)] = t
    return out


def lignes_fermees(compte: str) -> list[dict]:
    base, ent = _entetes()
    q = (f"signals?compte=eq.{compte}"
         "&status=in.(closed_tp,closed_sl)"
         "&select=id,reference,profit_eur,result_pct&limit=2000")
    r = urllib.request.Request(f"{base}/rest/v1/{q}", headers=ent)
    return json.load(urllib.request.urlopen(r, timeout=40))


def poser(ident: str, montant: float) -> None:
    base, ent = _entetes()
    req = urllib.request.Request(
        f"{base}/rest/v1/signals?id=eq.{urllib.parse.quote(str(ident))}",
        data=json.dumps({"profit_eur": round(montant, 2)}).encode(),
        method="PATCH", headers={**ent, "Prefer": "return=minimal"})
    urllib.request.urlopen(req, timeout=30).close()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="  %(message)s")
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--compte", default="demo2")
    ap.add_argument("--appliquer", action="store_true")
    args = ap.parse_args()

    journal = trades(args.compte)
    if not journal:
        log.error("aucun journal pour %s", args.compte)
        return 1
    lignes = lignes_fermees(args.compte)
    log.info("%s : %d trades au journal, %d lignes fermees publiees",
             args.compte, len(journal), len(lignes))

    a_poser: list[tuple[str, float, str]] = []
    introuvables = 0
    for l in lignes:
        ref = str(l.get("reference") or "")
        pid, _, etage = ref.partition(":")
        t = journal.get(pid)
        if t is None:
            introuvables += 1
            continue
        # Le benefice appartient a la position : etage 1 le porte, les
        # autres portent zero.
        montant = float(t.get("profit", 0.0)) if etage in ("", "1") else 0.0
        if l.get("profit_eur") is not None \
                and abs(float(l["profit_eur"]) - montant) < 0.005:
            continue
        a_poser.append((l["id"], montant, f"{t['symbol']} etage {etage or 1}"))

    total = sum(m for _, m, _ in a_poser)
    log.info("  %d ligne(s) a corriger, %d sans trade correspondant",
             len(a_poser), introuvables)
    log.info("  somme des benefices poses : %+.2f EUR", total)
    for _, m, quoi in a_poser[:12]:
        log.info("     %-22s %+8.2f", quoi, m)
    if len(a_poser) > 12:
        log.info("     ... et %d autres", len(a_poser) - 12)

    if not args.appliquer:
        log.info("  (essai a blanc -- relancer avec --appliquer)")
        return 0
    faits = 0
    for ident, montant, _ in a_poser:
        try:
            poser(ident, montant)
            faits += 1
        except urllib.error.HTTPError as e:               # noqa: PERF203
            log.warning("  refus sur %s : %s", ident,
                        e.read().decode()[:120])
    log.info("  %d ligne(s) mises a jour", faits)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
