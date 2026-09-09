#!/usr/bin/env python3
"""Bougies journalieres forex, via Yahoo.

Le forex est le troisieme marche teste, apres la crypto et les actions.
Il a une propriete que les deux autres n'ont pas : les paires majeures
sont peu volatiles (ATR journalier autour de 0,5 % contre 3 a 5 % en
crypto), ce qui change tout le rapport frais / risque.

ATTENTION AU MODELE DE FRAIS. IBKR facture le forex au notionnel — 0,20
point de base — avec un MINIMUM de 2 USD par ordre. Sur un petit compte
c'est le minimum qui s'applique toujours, et c'est lui qui decide : un
aller-retour coute 4 USD quelle que soit la taille de la position.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request

RACINE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(RACINE, "cache_forex")

sys.path.insert(0, RACINE)
from donnees import Bougie                                  # noqa: E402

# Majeures et croisees liquides. Le suffixe Yahoo est "=X".
UNIVERS = {
    "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "USDJPY": "USDJPY=X",
    "AUDUSD": "AUDUSD=X", "USDCAD": "USDCAD=X", "USDCHF": "USDCHF=X",
    "NZDUSD": "NZDUSD=X", "EURGBP": "EURGBP=X", "EURJPY": "EURJPY=X",
    "GBPJPY": "GBPJPY=X", "AUDJPY": "AUDJPY=X", "EURAUD": "EURAUD=X",
    "EURCHF": "EURCHF=X", "CADJPY": "CADJPY=X", "CHFJPY": "CHFJPY=X",
    "AUDCAD": "AUDCAD=X", "AUDNZD": "AUDNZD=X", "EURCAD": "EURCAD=X",
    "GBPAUD": "GBPAUD=X", "GBPCAD": "GBPCAD=X", "NZDJPY": "NZDJPY=X",
    "USDMXN": "USDMXN=X", "USDSEK": "USDSEK=X", "USDNOK": "USDNOK=X",
    "USDZAR": "USDZAR=X", "EURSEK": "EURSEK=X", "EURNOK": "EURNOK=X",
    "USDPLN": "USDPLN=X",
}


def _telecharger(code: str, essais: int = 3):
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{code}"
           "?interval=1d&range=10y")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    for i in range(essais):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except Exception as exc:                            # noqa: BLE001
            if i == essais - 1:
                print(f"    ! {code} : {str(exc)[:60]}", file=sys.stderr)
                return None
            time.sleep(2 + i)
    return None


def charger_tout(verbeux: bool = True) -> dict[str, list[Bougie]]:
    os.makedirs(CACHE, exist_ok=True)
    out: dict[str, list[Bougie]] = {}
    for nom, code in UNIVERS.items():
        chemin = os.path.join(CACHE, f"{nom}.json")
        if os.path.exists(chemin):
            with open(chemin) as f:
                brut = json.load(f)
        else:
            data = _telecharger(code)
            if not data:
                continue
            try:
                res = data["chart"]["result"][0]
                ts = res["timestamp"]
                q = res["indicators"]["quote"][0]
            except (KeyError, IndexError, TypeError):
                print(f"    ! {nom} : reponse inattendue", file=sys.stderr)
                continue
            brut = []
            for i, t in enumerate(ts):
                o, h, b, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
                if None in (o, h, b, c) or h <= 0:
                    continue
                brut.append([int(t), o, h, b, c, 0.0])
            with open(chemin, "w") as f:
                json.dump(brut, f)
            time.sleep(0.4)
        serie = [Bougie(ts=x[0], open=x[1], high=x[2], low=x[3],
                        close=x[4], volume=x[5]) for x in brut]
        if len(serie) > 300:
            out[nom] = serie
        if verbeux:
            print(f"  {nom:8} {len(serie):>5} bougies")
    return out


if __name__ == "__main__":
    import datetime as dt
    d = charger_tout()
    jours = sorted({b.ts for s in d.values() for b in s})
    print(f"\n{len(d)} paires | {sum(len(s) for s in d.values()):,} bougies")
    print(f"{dt.datetime.fromtimestamp(jours[0], dt.UTC):%Y-%m-%d} -> "
          f"{dt.datetime.fromtimestamp(jours[-1], dt.UTC):%Y-%m-%d}")
    # L'ATR relatif decide du rapport frais / risque : on le mesure.
    import statistics
    import moteur as M
    ratios = []
    for nom, s in d.items():
        i = len(s) - 1
        a = M.atr(s, i, 14)
        if a > 0 and s[i].close > 0:
            ratios.append(100 * a / s[i].close)
    print(f"ATR journalier median : {statistics.median(ratios):.2f} % du prix")
