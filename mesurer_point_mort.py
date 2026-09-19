#!/usr/bin/env python3
"""A quel R faut-il remonter le stop au prix d'achat ?

Demande de l'operateur : « le bon reglage pour faire pratiquement aucune
position fermee en perte ».

MESURE PAR INSTRUMENT, ET C'EST VOULU. Le point mort se joue position
par position ; il ne depend pas de la concurrence entre cryptos pour le
budget. Le rejeu par instrument est donc ici le bon outil — il donne des
CENTAINES de trades la ou le compte unique en donne huit, et huit trades
ne tranchent rien.

Ce qu'il ne faut PAS faire avec ces chiffres : additionner les profits
et y lire le rendement d'un compte. Voir CLAUDE.md, « comparer.py mesure
des comptes separes ».
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time

from gold_bot.backtest import Backtester
from gold_bot.engine import registre_pour
from gold_bot.settings import BotConfig
from gold_bot.universe import Universe


def principal() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", default="robot.demo.json")
    p.add_argument("--paires", type=int, default=40)
    p.add_argument("--bougies", type=int, default=900)
    p.add_argument("--capital", type=float, default=3300.0)
    p.add_argument("--valeur", type=float, required=True,
                   help="le point mort a mesurer, en R")
    p.add_argument("--json", default="")
    args = p.parse_args()

    logging.basicConfig(level=logging.ERROR)
    logging.getLogger("gold_bot").setLevel(logging.ERROR)

    cfg = BotConfig.load(args.config)
    cfg.trade.breakeven_at_r = args.valeur
    registre = registre_pour(cfg)
    symboles = [i.symbol for i in Universe()
                if i.symbol.endswith("USD")][:args.paires]

    rejeu = Backtester(cfg, registry=registre)
    trades = []
    servis = 0
    t0 = time.time()
    for sym in symboles:
        try:
            r = rejeu.run(sym, bars=args.bougies, start_balance=args.capital)
        except Exception:                                    # noqa: BLE001
            continue
        servis += 1
        trades.extend(t for t in r.trades if not t.partial)

    perdantes = sum(1 for t in trades if t.profit <= 0)
    profit = sum(t.profit for t in trades)
    etages = {}
    for t in trades:
        d = etages.setdefault(int(t.etages or 1), {"n": 0, "profit": 0.0})
        d["n"] += 1
        d["profit"] += t.profit
    ligne = {
        "point_mort_R": args.valeur, "paires": servis,
        "trades": len(trades), "perdantes": perdantes,
        "pct_perdantes": round(perdantes / len(trades) * 100, 1) if trades else 0.0,
        "profit": round(profit, 2),
        "par_trade": round(profit / len(trades), 3) if trades else 0.0,
        "etage_max": max(etages) if etages else 1,
        "par_etage": {k: {"n": v["n"], "profit": round(v["profit"], 2)}
                      for k, v in sorted(etages.items())},
        "secondes": round(time.time() - t0),
    }
    print(f"  point mort {args.valeur:>4.1f} R : {len(trades):>4} trades, "
          f"{perdantes:>4} perdantes ({ligne['pct_perdantes']:>4.1f} %), "
          f"{profit:>+9.0f} EUR ({ligne['par_trade']:>+7.2f}/trade), "
          f"etage max {ligne['etage_max']}")
    if args.json:
        with open(args.json, "a") as f:
            f.write(json.dumps(ligne) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(principal())
