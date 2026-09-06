#!/usr/bin/env python3
"""Compare le Turtle en service a 4 variantes, parametres FIGES.

Test d'hypothese, pas une recherche : aucun grid search, aucune
optimisation. Chaque variante ajoute UNE idee au baseline, et on regarde
si elle survit aux frais doubles et a la periode hors echantillon.

    python3 comparer.py
"""
from __future__ import annotations

import json
import os
import sys

RACINE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RACINE)

import donnees as D                                    # noqa: E402
import moteur as M                                     # noqa: E402

# Part de l'historique servant de periode d'apprentissage. Les 30 % finaux
# ne sont regardes qu'une fois, a la fin : c'est le vrai juge.
SPLIT = 0.70

CONFIGS = {
    "A_BASELINE": dict(),
    "B_REGIME": dict(filtre_regime_btc=True),
    "C_UNIVERS": dict(filtre_momentum=True, filtre_liquidite=True),
    "D_SIGNAL": dict(canal_entree=(20, 55, 100), vote_minimum=2),
    "E_COMBO": dict(filtre_regime_btc=True, filtre_momentum=True,
                    filtre_liquidite=True,
                    canal_entree=(20, 55, 100), vote_minimum=2),
}


def bornes(donnees) -> tuple[float, float, float]:
    jours = sorted({b.ts for s in donnees.values() for b in s})
    coupe = jours[int(len(jours) * SPLIT)]
    return jours[0], coupe, jours[-1]


def lancer(donnees, mult: float) -> dict:
    out = {}
    for nom, extra in CONFIGS.items():
        out[nom] = M.rejouer(donnees, M.Reglages(multiplicateur_couts=mult, **extra))
    out["BENCHMARK_BTC"] = M.buy_hold(donnees, "BTC", mult_couts=mult)
    return out


def main() -> int:
    print("Chargement des donnees...")
    donnees = D.charger_tout(verbeux=False)
    t0, coupe, t1 = bornes(donnees)
    import datetime as dt
    print(f"  {len(donnees)} paires | {dt.datetime.fromtimestamp(t0):%Y-%m-%d} "
          f"-> {dt.datetime.fromtimestamp(t1):%Y-%m-%d}")
    print(f"  coupe walk-forward : {dt.datetime.fromtimestamp(coupe):%Y-%m-%d} "
          f"({SPLIT:.0%} / {1 - SPLIT:.0%})\n")

    resultats = {"normal": lancer(donnees, 1.0),
                 "double": lancer(donnees, 2.0)}

    # Metriques : periode complete, in-sample, out-of-sample.
    table = {}
    for regime, jeux in resultats.items():
        for nom, res in jeux.items():
            table[(regime, nom, "total")] = M.metriques(res)
            table[(regime, nom, "IS")] = M.metriques(res, t0, coupe)
            table[(regime, nom, "OOS")] = M.metriques(res, coupe, t1)

    # --- Critere de decision, applique et non laisse a l'interpretation ---
    # Une variante n'est retenue que si elle bat le BASELINE en Sharpe ET
    # en max drawdown, AVEC FRAIS DOUBLES, SUR LA PERIODE OOS.
    verdicts = {}
    base = table[("double", "A_BASELINE", "OOS")]
    for nom in CONFIGS:
        if nom == "A_BASELINE":
            continue
        v = table[("double", nom, "OOS")]
        sharpe_ok = v["sharpe"] > base["sharpe"]
        dd_ok = v["max_dd_pct"] < base["max_dd_pct"]
        retenue = sharpe_ok and dd_ok

        # Suspect : bat le baseline en in-sample mais pas en OOS.
        b_is = table[("double", "A_BASELINE", "IS")]
        v_is = table[("double", nom, "IS")]
        suspect = (v_is["sharpe"] > b_is["sharpe"]) and not sharpe_ok

        verdicts[nom] = {
            "retenue": retenue, "sharpe_ok": sharpe_ok, "dd_ok": dd_ok,
            "suspect_surajustement": suspect,
            "sharpe": v["sharpe"], "sharpe_base": base["sharpe"],
            "dd": v["max_dd_pct"], "dd_base": base["max_dd_pct"],
            "trades_oos": v["trades"],
        }

    with open(os.path.join(RACINE, "resultats.json"), "w") as f:
        json.dump({
            "bornes": {"debut": t0, "coupe": coupe, "fin": t1},
            "metriques": {f"{r}|{n}|{p}": m for (r, n, p), m in table.items()},
            "verdicts": verdicts,
            "courbes": {n: [[t, round(v, 2)] for t, v in res["courbe"][::7]]
                        for n, res in resultats["normal"].items()},
        }, f)

    # --- Affichage ---
    def bloc(titre, regime, periode):
        print(f"\n{titre}")
        print(f"  {'variante':16}{'rend.%':>9}{'CAGR%':>8}{'Sharpe':>8}"
              f"{'maxDD%':>8}{'trades':>8}{'reuss%':>8}{'PnL moy':>9}"
              f"{'expo%':>7}{'frais':>8}")
        print("  " + "-" * 89)
        for nom in list(CONFIGS) + ["BENCHMARK_BTC"]:
            m = table[(regime, nom, periode)]
            if not m.get("trades") and nom != "BENCHMARK_BTC":
                print(f"  {nom:16}{'aucun trade':>9}")
                continue
            print(f"  {nom:16}{m['rendement_pct']:>9.1f}{m['cagr_pct']:>8.1f}"
                  f"{m['sharpe']:>8.2f}{m['max_dd_pct']:>8.1f}{m['trades']:>8}"
                  f"{m['reussite_pct']:>8.1f}{m['pnl_moyen']:>9.2f}"
                  f"{m['expose_pct']:>7.1f}{m['frais']:>8.0f}")

    bloc("=== FRAIS REELS — periode complete ===", "normal", "total")
    bloc("=== FRAIS DOUBLES — periode complete ===", "double", "total")
    bloc("=== FRAIS DOUBLES — in-sample (70 %) ===", "double", "IS")
    bloc("=== FRAIS DOUBLES — out-of-sample (30 %) ===", "double", "OOS")

    print("\n=== VERDICT (Sharpe ET drawdown battus, frais doubles, OOS) ===")
    for nom, v in verdicts.items():
        etat = "RETENUE" if v["retenue"] else "NON RETENUE"
        detail = (f"Sharpe {v['sharpe']:+.2f} vs {v['sharpe_base']:+.2f} "
                  f"{'OK' if v['sharpe_ok'] else 'KO'} | "
                  f"DD {v['dd']:.1f}% vs {v['dd_base']:.1f}% "
                  f"{'OK' if v['dd_ok'] else 'KO'}")
        print(f"  {nom:12} {etat:12} {detail}")
        if v["suspect_surajustement"]:
            print(f"  {'':12} !! SUSPECT : bat le baseline en in-sample "
                  "seulement -> sur-ajustement")
    print("\n-> resultats.json ecrit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
