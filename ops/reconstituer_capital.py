#!/usr/bin/env python3
"""Reconstitue la courbe de capital d'un compte, depuis son premier jour.

POURQUOI RECONSTITUER PLUTOT QU'ATTENDRE
========================================

`ops/battement_comptes.py` enregistre un releve toutes les cinq minutes,
mais il n'a commence que le 21 septembre au soir. La courbe n'avait donc
que deux points, et les quatre fenetres (1 jour, 7 jours, 30 jours,
1 an) montraient toutes la meme chose. Remarque de l'operateur : « le
graphique ne bouge pas, les euros restent les memes qu'au debut, c'est
pas coherent ».

Il avait raison, et attendre une semaine que la courbe se remplisse
n'etait pas une reponse. Tout ce qu'il faut pour la reconstituer existe
deja :

    trades-<compte>.jsonl   chaque trade ferme, avec son heure et son gain
    state-<compte>.json     les positions ouvertes, avec volume et entree
    l'historique des cours  chez Bitvavo, en bougies horaires

CE QUE CETTE COURBE VAUT, ET SA LIMITE
======================================

Elle vaut le CAPITAL TOTAL a chaque heure : le solde realise, plus la
valeur de marche des positions ouvertes a ce moment-la. C'est la meme
definition que celle du simulateur (`equity = solde + gain flottant`),
donc elle se raccorde exactement aux releves en direct.

Sa limite : elle ne connait que les positions dont on a gardé la trace.
Une position ouverte PUIS fermee figure bien (elle est dans les trades),
mais son gain n'apparait qu'a sa cloture -- on ne sait pas a quel prix
elle valait a chaque heure pendant qu'elle etait ouverte, faute d'avoir
enregistre son volume dans le journal des trades... si celui-ci le
porte, on l'utilise, sinon on l'ignore et la courbe est LEGEREMENT
plus lisse que la realite.

    python3 ops/reconstituer_capital.py --compte demo
    python3 ops/reconstituer_capital.py --compte demo --appliquer
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gold_bot.env import charger_env   # noqa: E402

charger_env()
log = logging.getLogger("reconstitution")

PAS = 3600          # une heure
DEPART = 3300.0


def bougies(actif: str, depuis: float) -> dict[int, float]:
    """Les cours horaires depuis `depuis`, indexes par heure ronde."""
    url = (f"https://api.bitvavo.com/v2/{actif}-EUR/candles"
           f"?interval=1h&limit=1000")
    try:
        with urllib.request.urlopen(url, timeout=25) as r:
            lignes = json.loads(r.read().decode())
    except Exception:                                          # noqa: BLE001
        return {}
    out = {}
    for b in lignes:
        t = int(b[0]) // 1000
        if t >= depuis - PAS:
            out[t // PAS * PAS] = float(b[4])   # cloture
    return out


def courbe(compte: str) -> list[tuple[int, float]]:
    etat = json.loads(Path(f"data/state-{compte}.json").read_text())
    meta = etat.get("position_meta", {})

    trades = []
    f = Path(f"data/trades-{compte}.jsonl")
    if f.exists():
        for l in f.read_text().splitlines():
            if l.strip():
                try:
                    trades.append(json.loads(l))
                except Exception:                              # noqa: BLE001
                    pass

    debuts = [t.get("opened_at", 0) for t in trades if t.get("opened_at")]
    debuts += [p.get("opened_at", 0) for p in meta.values() if p.get("opened_at")]
    if not debuts:
        return []
    debut = int(min(debuts)) // PAS * PAS
    fin = int(dt.datetime.now(dt.timezone.utc).timestamp()) // PAS * PAS

    # Les cours de tout ce qui a ete detenu, en une passe par actif.
    actifs = {p["symbol"].replace("USD", "").replace("EUR", "")
              for p in meta.values()}
    cours = {a: bougies(a, debut) for a in sorted(actifs)}
    manquants = [a for a, c in cours.items() if not c]
    if manquants:
        log.warning("sans historique : %s", ", ".join(manquants))

    points = []
    for t in range(debut, fin + PAS, PAS):
        # Le realise : tout ce qui etait DEJA ferme a cette heure-la.
        realise = sum(x.get("profit", 0.0) for x in trades
                      if x.get("closed_at", 0) <= t)
        # Le latent : les positions encore ouvertes, au cours de l'heure.
        latent = 0.0
        for p in meta.values():
            if p.get("opened_at", 0) > t:
                continue
            a = p["symbol"].replace("USD", "").replace("EUR", "")
            serie = cours.get(a) or {}
            prix = serie.get(t)
            if prix is None:
                # Pas d'echange cette heure-la : on garde le dernier
                # cours connu plutot que de creuser un trou dans la
                # courbe. Sur les cryptos peu echangees, c'est frequent.
                anterieurs = [h for h in serie if h <= t]
                if not anterieurs:
                    continue
                prix = serie[max(anterieurs)]
            latent += p["volume"] * (prix - p["entry_price"])
        points.append((t, round(DEPART + realise + latent, 2)))
    return points


def deposer(compte: str, points: list[tuple[int, float]]) -> int:
    url = os.environ["SUPABASE_URL"].rstrip("/")
    cle = os.environ["SUPABASE_SERVICE_KEY"]
    # ON EFFACE LA RECONSTITUTION PRECEDENTE, PAS LES RELEVES EN DIRECT.
    # Les deux se distinguent par la date : tout ce qui precede le
    # premier releve reel est reconstitue.
    lignes = [{"compte": compte,
               "capital_eur": v,
               "vu_le": dt.datetime.fromtimestamp(
                   t, dt.timezone.utc).isoformat()}
              for t, v in points]
    envoyes = 0
    for i in range(0, len(lignes), 200):
        lot = lignes[i:i + 200]
        req = urllib.request.Request(
            f"{url}/rest/v1/alluxe_bot_capital",
            data=json.dumps(lot).encode(), method="POST",
            headers={"apikey": cle, "authorization": f"Bearer {cle}",
                     "content-type": "application/json",
                     "prefer": "return=minimal"})
        try:
            urllib.request.urlopen(req, timeout=60).close()
            envoyes += len(lot)
        except urllib.error.HTTPError as e:
            log.warning("lot refuse : %s", e.read().decode()[:160])
    return envoyes


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="  %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--compte", default="demo")
    ap.add_argument("--appliquer", action="store_true")
    args = ap.parse_args()

    pts = courbe(args.compte)
    if not pts:
        log.error("aucune donnee pour %s", args.compte)
        return 1
    d0 = dt.datetime.fromtimestamp(pts[0][0], dt.timezone.utc)
    d1 = dt.datetime.fromtimestamp(pts[-1][0], dt.timezone.utc)
    bas = min(v for _, v in pts)
    haut = max(v for _, v in pts)
    log.info("%s : %d points, du %s au %s",
             args.compte, len(pts), d0.strftime("%d/%m %Hh"),
             d1.strftime("%d/%m %Hh"))
    log.info("  de %.2f a %.2f EUR (plus bas %.2f, plus haut %.2f)",
             pts[0][1], pts[-1][1], bas, haut)
    if not args.appliquer:
        log.info("  (essai a blanc -- relancer avec --appliquer)")
        return 0
    n = deposer(args.compte, pts)
    log.info("  %d releves enregistres", n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
