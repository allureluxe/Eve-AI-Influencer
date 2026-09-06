#!/usr/bin/env python3
"""Telechargement et cache des bougies journalieres Bitvavo.

L'historique le plus long que la plateforme accepte de servir, sur les
paires que le robot trade REELLEMENT (celles de son univers qui existent
en EUR chez Bitvavo).

Le cache est sur disque : un rejeu de comparaison se relance en secondes
au lieu d'un quart d'heure. C'est ce qui permet de mesurer plusieurs fois
au lieu de se contenter d'une mesure « pour aller plus vite ».
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from dataclasses import dataclass

RACINE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(RACINE, "cache")
BITVAVO = "https://api.bitvavo.com/v2"


@dataclass(frozen=True)
class Bougie:
    ts: float          # secondes UTC, ouverture de la journee
    open: float
    high: float
    low: float
    close: float
    volume: float      # en unites de l'actif de base


def _get(chemin: str, essais: int = 5):
    for i in range(essais):
        try:
            with urllib.request.urlopen(f"{BITVAVO}{chemin}", timeout=30) as r:
                return json.load(r)
        except Exception as exc:  # noqa: BLE001
            if i == essais - 1:
                print(f"    ! {chemin[:60]} : {str(exc)[:70]}", file=sys.stderr)
                return None
            time.sleep(2 + i)
    return None


def univers_reel() -> dict[str, str]:
    """Les instruments du robot qui ont une paire EUR negociable.

    On ne prend PAS une liste inventee : on lit l'univers du bot et on
    garde l'intersection avec ce que Bitvavo cote reellement.
    """
    sys.path.insert(0, "/home/ubuntu/Eve-AI-Influencer")
    from gold_bot.universe import Universe

    marches = _get("/markets") or []
    dispo = {m["market"] for m in marches
             if isinstance(m, dict) and m.get("quote") == "EUR"
             and m.get("status") == "trading"}
    paires = {}
    for inst in Universe():
        if inst.asset_class != "crypto":
            continue
        base = inst.symbol[:-3]                    # BTCUSD -> BTC
        if f"{base}-EUR" in dispo:
            paires[base] = f"{base}-EUR"
    return dict(sorted(paires.items()))


def bougies(marche: str, jours: int = 2000) -> list[Bougie]:
    """Bougies D1, du plus ancien au plus recent, avec cache disque.

    Bitvavo rend au plus 1440 bougies par requete : on pagine vers le
    passe jusqu'a ce que la plateforme n'ait plus rien a donner.
    """
    os.makedirs(CACHE, exist_ok=True)
    cle = os.path.join(CACHE, f"{marche}_D1.json")
    if os.path.exists(cle):
        try:
            with open(cle) as f:
                return [Bougie(*r) for r in json.load(f)]
        except Exception:  # noqa: BLE001
            pass

    pas = 86400_000
    fin = int(time.time() * 1000)
    par_ts: dict[int, Bougie] = {}
    for _ in range(jours // 1400 + 2):
        deb = fin - 1400 * pas
        lignes = _get(f"/{marche}/candles?interval=1d&start={deb}&end={fin}&limit=1440")
        if not lignes:
            break
        for r in lignes:
            t = int(r[0])
            par_ts[t] = Bougie(t / 1000.0, float(r[1]), float(r[2]),
                               float(r[3]), float(r[4]), float(r[5]))
        plus_ancien = min(int(r[0]) for r in lignes)
        if plus_ancien >= fin:
            break
        fin = plus_ancien - pas
        time.sleep(0.3)

    serie = [par_ts[k] for k in sorted(par_ts)]
    if serie:
        with open(cle, "w") as f:
            json.dump([[b.ts, b.open, b.high, b.low, b.close, b.volume]
                       for b in serie], f)
    return serie


def charger_tout(verbeux: bool = True) -> dict[str, list[Bougie]]:
    paires = univers_reel()
    if verbeux:
        print(f"{len(paires)} paires EUR dans l'univers du robot\n")
    donnees = {}
    for i, (base, marche) in enumerate(paires.items(), 1):
        s = bougies(marche)
        if len(s) < 250:                 # trop court pour une MM200 + rodage
            if verbeux:
                print(f"  [{i:2}/{len(paires)}] {base:8} ECARTE ({len(s)} jours)")
            continue
        donnees[base] = s
        if verbeux:
            import datetime as dt
            d0 = dt.datetime.fromtimestamp(s[0].ts)
            print(f"  [{i:2}/{len(paires)}] {base:8} {len(s):5} jours "
                  f"depuis {d0:%Y-%m-%d}")
    return donnees


if __name__ == "__main__":
    d = charger_tout()
    tot = sum(len(v) for v in d.values())
    print(f"\n{len(d)} paires retenues, {tot} bougies au total")
