#!/usr/bin/env python3
"""Que donne la reserve de budget destinee aux renforcements ?

Decision de l'operateur : « tu bloques desormais un tiers du capital aux
pyramides ». Ce script la mesure AVANT de l'armer, sur un compte unique
— le seul cadre ou la question a un sens, puisque la reserve n'existe
que parce que nouvelles lignes et etages se disputent le meme budget.

Il mesure aussi ce que l'operateur a demande dans la foulee : « le bon
reglage pour faire pratiquement aucune position fermee en perte ». La
colonne « perdantes » le dit, et la colonne « resultat » dit ce que ca
coute.

    python3 mesurer_reserve.py --paires 60 --bougies 900
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time

from gold_bot.backtest_portefeuille import BacktestPortefeuille
from gold_bot.engine import registre_pour
from gold_bot.settings import BotConfig
from gold_bot.universe import Universe


def principal() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", default="robot.demo.json")
    p.add_argument("--paires", type=int, default=60)
    p.add_argument("--bougies", type=int, default=900)
    p.add_argument("--capital", type=float, default=3300.0)
    p.add_argument("--json", default="")
    # UNE VARIANTE PAR PROCESSUS.
    #
    # Les sept enchainees dans un seul processus ont ete tuees par manque
    # de memoire : ce serveur a 3,8 Go dont le robot demo occupe ~1,9, et
    # un portefeuille de 60 paires garde en vie 60 jeux d'indicateurs. Un
    # `del` ne suffit pas, l'allocateur ne rend pas la memoire au systeme.
    # Sortir du processus, si.
    p.add_argument("--variante", type=int, default=-1,
                   help="n'executer que cette variante (0..6), et ajouter "
                        "son resultat en une ligne JSON au fichier --json")
    args = p.parse_args()

    logging.basicConfig(level=logging.ERROR)
    logging.getLogger("gold_bot").setLevel(logging.ERROR)

    base = BotConfig.load(args.config)
    registre = registre_pour(base)
    symboles = [i.symbol for i in Universe()
                if i.symbol.endswith("USD")][:args.paires]

    total = base.risk.max_total_risk_pct
    variantes = [
        ("aucune reserve (en service)", 0.0, None),
        ("un quart reserve", total / 4, None),
        ("UN TIERS reserve (demande)", total / 3, None),
        ("la moitie reservee", total / 2, None),
        # Le point mort plus tot : moins de perdantes, mais des gagnantes
        # coupees a zero avant d'avoir couru.
        ("un tiers + point mort a 0,4 R", total / 3, 0.4),
        ("un tiers + point mort a 0,5 R", total / 3, 0.5),
        ("un tiers + point mort a 1,0 R", total / 3, 1.0),
    ]

    if args.variante >= 0:
        variantes = [variantes[args.variante]]
    else:
        print(f"{len(symboles)} paires x {args.bougies} bougies, "
              f"capital {args.capital:.0f} EUR, budget total {total:.2f} %")
        print(f"point mort en service : {base.trade.breakeven_at_r} R")
        print()
        print(f"  {'variante':<30}{'trades':>7}{'perdantes':>11}"
              f"{'resultat':>11}{'recul':>8}{'etage max':>10}")
        print("  " + "-" * 77)

    lignes = []
    for nom, reserve, point_mort in variantes:
        cfg = BotConfig.load(args.config)
        cfg.risk.reserve_pyramide_pct = reserve
        if point_mort is not None:
            cfg.trade.breakeven_at_r = point_mort
        t0 = time.time()
        r = BacktestPortefeuille(cfg, registry=registre).run(
            symboles, bars=args.bougies, start_balance=args.capital)
        s = r.stats()
        reels = [t for t in r.trades if not t.partial]
        perdantes = sum(1 for t in reels if t.profit <= 0)
        pct_perdantes = perdantes / len(reels) * 100 if reels else 0.0
        etage_max = max(s.get("par_etage", {}) or {1: None})
        lignes.append({
            "nom": nom, "reserve_pct": reserve, "point_mort": point_mort,
            "trades": len(reels), "perdantes": perdantes,
            "pct_perdantes": round(pct_perdantes, 1),
            "resultat": s.get("resultat", 0.0),
            "recul_pct": s.get("drawdown_max_pct", 0.0),
            "etage_max": etage_max, "secondes": round(time.time() - t0),
            "par_etage": s.get("par_etage", {}),
        })
        print(f"  {nom:<30}{len(reels):>7}"
              f"{perdantes:>6} ({pct_perdantes:>3.0f}%)"
              f"{s.get('resultat', 0.0):>+11.0f}"
              f"{s.get('drawdown_max_pct', 0.0):>7.1f}%{etage_max:>10}")

    if args.variante >= 0:
        if args.json:
            with open(args.json, "a") as f:
                f.write(json.dumps(lignes[0], default=float) + "\n")
        return 0

    print()
    reference = lignes[0]["resultat"]
    print("  Lecture : la colonne « perdantes » est celle que l'operateur")
    print("  veut faire baisser. La colonne « resultat » dit ce que ca coute.")
    print(f"  Reference sans reserve : {reference:+.0f} EUR")

    if args.json:
        with open(args.json, "w") as f:
            json.dump(lignes, f, indent=1, default=float)
        print(f"\n  detail ecrit dans {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(principal())
