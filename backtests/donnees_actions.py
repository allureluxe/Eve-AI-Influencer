#!/usr/bin/env python3
"""Bougies journalieres d'actions US, pour tester la strategie hors crypto.

POURQUOI CE FICHIER EXISTE. Tout ce qui a ete mesure jusqu'ici porte sur
70 paires crypto. Conclure quoi que ce soit sur IBKR a partir de ces
chiffres serait une faute : un canal de Donchian sur des actions n'est
pas le meme animal — le marche ferme la nuit et le week-end, les gaps
d'ouverture remplacent une partie du mouvement continu, et les titres
d'un meme secteur bougent ensemble bien plus que deux cryptos.

L'UNIVERS EST CHOISI POUR ETRE HONNETE, PAS FLATTEUR :

  - des grandes capitalisations liquides, celles qu'on peut vraiment
    acheter et revendre a 0,01 % de spread avec 40 EUR ;
  - des secteurs varies, pour ne pas mesurer un pari sectoriel deguise ;
  - AUCUNE selection sur la performance passee. Prendre les gagnantes
    d'aujourd'hui reproduirait le biais du survivant en pire — on
    saurait deja quelles actions ont monte.

Le biais du survivant reste present malgre tout : ces societes existent
encore. Celles qui ont fait faillite ou ont ete radiees ne sont pas la.
C'est la meme limite que sur la crypto, et elle flatte le resultat.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request

RACINE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(RACINE, "cache_actions")

sys.path.insert(0, RACINE)
from donnees import Bougie                                  # noqa: E402

# LES 502 CONSTITUANTS DU S&P 500, lus sur Wikipedia et non choisis a la
# main. Un univers de 60 titres etait trop etroit : une strategie de
# cassure a besoin de beaucoup d'instruments pour trouver les rares qui
# partent vraiment, et 60 lignes ne produisaient pas assez d'occasions.
#
# Le biais du survivant reste entier, et il est meme PIRE ici qu'en
# crypto : ce sont les societes qui composent l'indice AUJOURD'HUI.
# Celles qui en sont sorties — rachetees, effondrees, radiees — sont
# absentes. Les rendements affiches sont donc surestimes.
_FICHIER = os.path.join(RACINE, "univers_sp500.json")
if os.path.exists(_FICHIER):
    with open(_FICHIER) as _f:
        UNIVERS = json.load(_f)
else:
    UNIVERS = [
    # technologie
    "AAPL", "MSFT", "NVDA", "AVGO", "ORCL", "CSCO", "ADBE", "CRM", "INTC",
    "AMD", "QCOM", "TXN", "IBM", "MU", "AMAT",
    # communication et consommation
    "GOOGL", "META", "NFLX", "DIS", "CMCSA", "AMZN", "TSLA", "HD", "MCD",
    "NKE", "SBUX", "LOW", "TGT", "BKNG",
    # sante
    "JNJ", "UNH", "LLY", "PFE", "ABBV", "MRK", "TMO", "ABT", "AMGN", "GILD",
    # finance
    "JPM", "BAC", "WFC", "GS", "MS", "AXP", "BLK", "SCHW", "C",
    # industrie, energie, matieres
    "CAT", "BA", "HON", "GE", "UPS", "LMT", "XOM", "CVX", "COP", "SLB",
    # defensives
    "PG", "KO", "PEP", "WMT", "COST", "T", "VZ",
    ]


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
    for code in UNIVERS:
        chemin = os.path.join(CACHE, f"{code}.json")
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
                print(f"    ! {code} : reponse inattendue", file=sys.stderr)
                continue
            brut = []
            for i, t in enumerate(ts):
                o, h, b, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
                v = (q.get("volume") or [None] * len(ts))[i]
                if None in (o, h, b, c):
                    continue
                brut.append([int(t), o, h, b, c, v or 0.0])
            with open(chemin, "w") as f:
                json.dump(brut, f)
            time.sleep(0.4)                                 # on reste poli
        serie = [Bougie(ts=x[0], open=x[1], high=x[2], low=x[3],
                        close=x[4], volume=x[5]) for x in brut]
        if len(serie) > 300:
            out[code] = serie
        if verbeux:
            print(f"  {code:6} {len(serie):>5} bougies")
    return out


if __name__ == "__main__":
    d = charger_tout()
    import datetime as dt
    jours = sorted({b.ts for s in d.values() for b in s})
    print(f"\n{len(d)} actions | {sum(len(s) for s in d.values()):,} bougies")
    print(f"{dt.datetime.fromtimestamp(jours[0], dt.UTC):%Y-%m-%d} -> "
          f"{dt.datetime.fromtimestamp(jours[-1], dt.UTC):%Y-%m-%d}")
