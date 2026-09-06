#!/usr/bin/env python3
"""La Turtle originale contre la notre, sur 6 mois.

Meme univers, meme periode, memes frais, meme capital de depart. Les
seules differences sont les regles des deux methodes — c'est tout
l'interet.

Deux fenetres de 6 mois sont mesurees, pas une : la derniere, et celle
d'avant. Un classement qui s'inverse d'une fenetre a l'autre ne prouve
rien, et il vaut mieux le voir que l'ignorer.

    python3 comparer_turtle.py
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

RACINE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RACINE)

import donnees as D                                   # noqa: E402
import moteur as M                                    # noqa: E402
import turtle as T                                    # noqa: E402

JOUR = 86400.0
SEMESTRE = 182 * JOUR


def config_notre(deb, fin, mult=1.0):
    """La configuration ARMEE sur le robot, pas une variante de banc d'essai."""
    return M.Reglages(
        risque_pct=0.006, canal_entree=(20,), atr_periode=14,
        stop_atr=1.6, trail_atr=2.2, trail_depart_r=1.1,
        stop_temporel_jours=12, max_positions=6, risque_total_max=0.035,
        multiplicateur_couts=mult, debut=deb, fin=fin)


def config_turtle(deb, fin, vente: bool, mult=1.0):
    return T.ReglagesTurtle(
        risque_n_pct=0.01, n_periode=20, stop_n=2.0, pyramide_max=4,
        espacement_n=0.5, filtre_system1=True, autoriser_vente=vente,
        multiplicateur_couts=mult, debut=deb, fin=fin)


def stats(res, r_capital=1000.0):
    m = M.metriques(res)
    tr = res["trades"]
    m["pyramidages"] = res.get("pyramidages", 0)
    if tr:
        g = [x.pnl for x in tr if x.pnl > 0]
        p = [x.pnl for x in tr if x.pnl <= 0]
        m["gain_moyen"] = sum(g) / len(g) if g else 0.0
        m["perte_moyenne"] = sum(p) / len(p) if p else 0.0
        m["meilleur"] = max(x.pnl for x in tr)
        m["pire"] = min(x.pnl for x in tr)
        m["jours_moyens"] = sum(x.jours for x in tr) / len(tr)
        m["ventes"] = sum(1 for x in tr if x.sortie < x.entree and x.pnl > 0)
    return m


def ligne(nom, m):
    if not m.get("trades"):
        return f"  {nom:26}{'aucun trade':>10}"
    return (f"  {nom:26}{m['rendement_pct']:>9.1f}{m['sharpe']:>8.2f}"
            f"{m['max_dd_pct']:>8.1f}{m['trades']:>8}{m['reussite_pct']:>8.1f}"
            f"{m['gain_moyen']:>9.2f}{m['perte_moyenne']:>9.2f}"
            f"{m['jours_moyens']:>7.1f}{m['frais']:>8.0f}")


ENTETE = (f"  {'methode':26}{'rend.%':>9}{'Sharpe':>8}{'maxDD%':>8}"
          f"{'trades':>8}{'reuss%':>8}{'gain moy':>9}{'perte':>9}"
          f"{'jours':>7}{'frais':>8}")


def main() -> int:
    print("Chargement des donnees...")
    d = D.charger_tout(verbeux=False)
    fin_hist = max(b.ts for s in d.values() for b in s)

    fenetres = [
        ("SEMESTRE 2 (le plus recent)", fin_hist - SEMESTRE, fin_hist),
        ("SEMESTRE 1 (les 6 mois d'avant)", fin_hist - 2 * SEMESTRE,
         fin_hist - SEMESTRE),
    ]
    print(f"  {len(d)} paires | historique jusqu'au "
          f"{dt.datetime.utcfromtimestamp(fin_hist):%Y-%m-%d}\n")

    sortie = {}
    for titre, deb, fin in fenetres:
        print("=" * 100)
        print(f"{titre} : {dt.datetime.utcfromtimestamp(deb):%d %b %Y} -> "
              f"{dt.datetime.utcfromtimestamp(fin):%d %b %Y}")
        print("=" * 100)

        jeux = {
            "NOTRE (armee sur le robot)": M.rejouer(d, config_notre(deb, fin)),
            "TURTLE vraie (avec ventes)": T.rejouer_turtle(
                d, config_turtle(deb, fin, vente=True)),
            "TURTLE achat seul (armable)": T.rejouer_turtle(
                d, config_turtle(deb, fin, vente=False)),
        }
        mesures = {k: stats(v) for k, v in jeux.items()}
        bh = M.buy_hold({k: [b for b in v if deb <= b.ts <= fin]
                         for k, v in d.items() if k == "BTC"}, "BTC")
        mesures["BTC achete et garde"] = M.metriques(bh)

        print("\n--- frais reels ---")
        print(ENTETE)
        print("  " + "-" * 98)
        for k, m in mesures.items():
            if k.startswith("BTC"):
                print(f"  {k:26}{m['rendement_pct']:>9.1f}{m['sharpe']:>8.2f}"
                      f"{m['max_dd_pct']:>8.1f}{'—':>8}")
            else:
                print(ligne(k, m))

        print("\n--- frais et glissement DOUBLES ---")
        print(ENTETE)
        print("  " + "-" * 98)
        dbl = {
            "NOTRE (armee sur le robot)": M.rejouer(d, config_notre(deb, fin, 2.0)),
            "TURTLE vraie (avec ventes)": T.rejouer_turtle(
                d, config_turtle(deb, fin, True, 2.0)),
            "TURTLE achat seul (armable)": T.rejouer_turtle(
                d, config_turtle(deb, fin, False, 2.0)),
        }
        mdbl = {k: stats(v) for k, v in dbl.items()}
        for k, m in mdbl.items():
            print(ligne(k, m))

        p = jeux["TURTLE vraie (avec ventes)"]["pyramidages"]
        p2 = jeux["TURTLE achat seul (armable)"]["pyramidages"]
        print(f"\n  pyramidages : {p} (avec ventes) · {p2} (achat seul)")
        print()

        sortie[titre] = {"bornes": [deb, fin],
                         "reels": {k: m for k, m in mesures.items()},
                         "doubles": {k: m for k, m in mdbl.items()}}

    with open(os.path.join(RACINE, "resultats_turtle.json"), "w") as f:
        json.dump(sortie, f, indent=1, default=float)
    print("-> resultats_turtle.json ecrit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
