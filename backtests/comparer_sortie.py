#!/usr/bin/env python3
"""Une seule question : notre stop suiveur coupe-t-il les gagnants trop tot ?

La Turtle garde ses gagnants 21 jours, nous 5. On teste donc UNIQUEMENT
la regle de sortie. Entree, dimensionnement, risque, nombre de places,
stop initial, stop temporel : tout est fige a la configuration ARMEE.
Si un chiffre bouge, c'est la sortie qui l'a fait bouger, rien d'autre.

CRITERE DE DECISION, pose AVANT de regarder les resultats. Une variante
n'est retenue que si, hors echantillon et frais doubles, elle fait les
trois a la fois :
    1. Sharpe superieur a celui de la sortie actuelle
    2. Recul maximal inferieur a celui de la sortie actuelle
    3. Rendement POSITIF
La regle 3 repare le trou du test precedent, ou une variante avait ete
« retenue » avec un Sharpe de -0,12 : elle perdait juste moins vite.

    python3 comparer_sortie.py
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys

RACINE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RACINE)

import donnees as D                                    # noqa: E402
import moteur as M                                     # noqa: E402

SPLIT = 0.70

# Le socle commun. Ne PAS y toucher : c'est ce qui tourne en reel.
SOCLE = dict(risque_pct=0.006, canal_entree=(20,), atr_periode=14,
             stop_atr=1.6, trail_depart_r=1.1, stop_temporel_jours=12,
             max_positions=6, risque_total_max=0.035)

SORTIES = {
    "ACTUELLE  trail 2,2 ATR": dict(trail_atr=2.2),
    "trail 3,0 ATR":           dict(trail_atr=3.0),
    "trail 4,0 ATR":           dict(trail_atr=4.0),
    "trail 5,0 ATR":           dict(trail_atr=5.0),
    "canal 10 j (Turtle)":     dict(sortie_canal_jours=10),
    "canal 20 j":              dict(sortie_canal_jours=20),
    "AUCUN suiveur":           dict(trail_atr=999.0),
}
REF = "ACTUELLE  trail 2,2 ATR"


def mesure(res, a=0.0, b=9e18):
    m = M.metriques(res, a, b)
    tr = [x for x in res["trades"] if a <= x.ferme_le <= b]
    m["jours_moyens"] = sum(x.jours for x in tr) / len(tr) if tr else 0.0
    g = [x.pnl for x in tr if x.pnl > 0]
    m["gain_moyen"] = sum(g) / len(g) if g else 0.0
    m["part_gagnants"] = (sum(g) / sum(abs(x.pnl) for x in tr if x.pnl <= 0)
                          if any(x.pnl <= 0 for x in tr) else 0.0)
    return m


E = (f"  {'sortie':26}{'rend.%':>9}{'CAGR%':>8}{'Sharpe':>8}{'maxDD%':>8}"
     f"{'trades':>8}{'reuss%':>8}{'jours':>7}{'gain moy':>10}{'frais':>8}")


def bloc(titre, table, regime, periode):
    print(f"\n{titre}")
    print(E)
    print("  " + "-" * 100)
    for nom in SORTIES:
        m = table[(regime, nom, periode)]
        if not m.get("trades"):
            print(f"  {nom:26}{'aucun trade':>9}")
            continue
        print(f"  {nom:26}{m['rendement_pct']:>9.1f}{m['cagr_pct']:>8.1f}"
              f"{m['sharpe']:>8.2f}{m['max_dd_pct']:>8.1f}{m['trades']:>8}"
              f"{m['reussite_pct']:>8.1f}{m['jours_moyens']:>7.1f}"
              f"{m['gain_moyen']:>10.2f}{m['frais']:>8.0f}")


def main() -> int:
    print("Chargement des donnees...")
    d = D.charger_tout(verbeux=False)
    jours = sorted({b.ts for s in d.values() for b in s})
    t0, coupe, t1 = jours[0], jours[int(len(jours) * SPLIT)], jours[-1]
    fmt = lambda x: dt.datetime.fromtimestamp(x, dt.UTC).strftime("%Y-%m-%d")
    print(f"  {len(d)} paires | {fmt(t0)} -> {fmt(t1)}")
    print(f"  coupe walk-forward : {fmt(coupe)}  "
          f"(apprentissage {SPLIT:.0%} / juge {1-SPLIT:.0%})\n")

    table = {}
    for regime, mult in (("normal", 1.0), ("double", 2.0)):
        for nom, extra in SORTIES.items():
            print(f"  ... {regime:7} {nom}", flush=True)
            res = M.rejouer(d, M.Reglages(multiplicateur_couts=mult,
                                          **SOCLE, **extra))
            table[(regime, nom, "total")] = mesure(res)
            table[(regime, nom, "IS")] = mesure(res, t0, coupe)
            table[(regime, nom, "OOS")] = mesure(res, coupe, t1)
            table[(regime, nom, "_motifs")] = {}
            for x in res["trades"]:
                table[(regime, nom, "_motifs")][x.motif] = \
                    table[(regime, nom, "_motifs")].get(x.motif, 0) + 1

    bloc("=== FRAIS REELS — 7,5 ans ===", table, "normal", "total")
    bloc("=== FRAIS DOUBLES — apprentissage (5,3 ans) ===", table, "double", "IS")
    bloc("=== FRAIS DOUBLES — HORS ECHANTILLON (2,2 ans) — le juge ===",
         table, "double", "OOS")

    print("\n=== VERDICT — les 3 conditions, hors echantillon, frais doubles ===")
    base = table[("double", REF, "OOS")]
    verdicts = {}
    for nom in SORTIES:
        if nom == REF:
            continue
        v = table[("double", nom, "OOS")]
        c1 = v["sharpe"] > base["sharpe"]
        c2 = v["max_dd_pct"] < base["max_dd_pct"]
        c3 = v["rendement_pct"] > 0
        ok = c1 and c2 and c3
        # Sur-ajustement : meilleure en apprentissage, pas hors echantillon.
        suspect = (table[("double", nom, "IS")]["sharpe"]
                   > table[("double", REF, "IS")]["sharpe"]) and not c1
        verdicts[nom] = dict(retenue=ok, sharpe=v["sharpe"],
                             dd=v["max_dd_pct"], rend=v["rendement_pct"],
                             suspect=suspect)
        print(f"  {nom:26}{'RETENUE' if ok else 'NON RETENUE':13}"
              f"Sharpe {v['sharpe']:+.2f} vs {base['sharpe']:+.2f} "
              f"{'OK' if c1 else 'KO'} | DD {v['max_dd_pct']:.1f} vs "
              f"{base['max_dd_pct']:.1f} {'OK' if c2 else 'KO'} | "
              f"rend {v['rendement_pct']:+.1f} % {'OK' if c3 else 'KO'}")
        if suspect:
            print(f"  {'':26}!! meilleure en apprentissage seulement "
                  "-> sur-ajustement")

    print("\n=== Comment chaque sortie ferme ses trades (frais reels) ===")
    for nom in SORTIES:
        m = table[("normal", nom, "_motifs")]
        tot = sum(m.values()) or 1
        detail = "  ".join(f"{k} {100*v/tot:.0f} %"
                           for k, v in sorted(m.items(), key=lambda x: -x[1]))
        print(f"  {nom:26}{detail}")

    with open(os.path.join(RACINE, "resultats_sortie.json"), "w") as f:
        json.dump({"verdicts": verdicts,
                   "metriques": {f"{a}|{b}|{c}": v for (a, b, c), v
                                 in table.items() if c != "_motifs"}},
                  f, indent=1, default=float)
    print("\n-> resultats_sortie.json ecrit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
