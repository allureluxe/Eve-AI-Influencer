#!/usr/bin/env python3
"""Compare deux facons de mesurer la MEME strategie.

  - « comptes separes » : un compte neuf par crypto, profits additionnes.
    C'est ce que fait `comparer.py`, donc ce sur quoi TOUTES les
    decisions du depot ont ete prises.
  - « un seul compte » : les cryptos se disputent le capital et le budget
    de risque, comme le robot.

La question n'est pas « laquelle est la bonne » : la premiere reste utile
pour comparer deux reglages a armes egales. La question est de savoir de
combien elles divergent, et si les conclusions tirees de la premiere
survivent a la seconde.

    python3 mesurer_portefeuille.py --paires 25 --bougies 500
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time

from gold_bot.backtest import Backtester
from gold_bot.backtest_portefeuille import BacktestPortefeuille
from gold_bot.engine import registre_pour
from gold_bot.settings import BotConfig
from gold_bot.universe import Universe


def univers_bitvavo(limite: int) -> list[str]:
    """Les cryptos que le robot suit vraiment, les plus liquides d'abord."""
    u = Universe()
    symboles = [i.symbol for i in u if i.symbol.endswith("USD")]
    # L'ordre de l'univers est celui du catalogue ; on garde les premieres,
    # qui sont les paires majeures. Prendre un echantillon au hasard
    # rendrait la mesure irreproductible d'un soir a l'autre.
    return symboles[:limite]


def principal() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", default="robot.demo.json")
    p.add_argument("--paires", type=int, default=25)
    p.add_argument("--bougies", type=int, default=500)
    p.add_argument("--capital", type=float, default=3300.0)
    p.add_argument("--json", default="", help="ecrire le detail dans ce fichier")
    args = p.parse_args()

    logging.basicConfig(level=logging.WARNING,
                        format="%(levelname)s %(message)s")
    logging.getLogger("gold_bot").setLevel(logging.ERROR)

    cfg = BotConfig.load(args.config)
    registre = registre_pour(cfg)
    symboles = univers_bitvavo(args.paires)

    print(f"Strategie   : {cfg.strategy.famille} {cfg.strategy.entry_tf}, "
          f"canal {cfg.strategy.donchian_entrees}")
    print(f"Risque      : {cfg.risk.base_risk_pct} % par trade, "
          f"plafond total {cfg.risk.max_total_risk_pct} %")
    print(f"Pyramide    : max {cfg.risk.pyramide_max}, "
          f"a l'abri a {cfg.risk.pyramide_locked_r_min} R")
    print(f"Echantillon : {len(symboles)} paires x {args.bougies} bougies, "
          f"capital {args.capital:.0f} EUR")
    print()

    # --- 1. Comptes separes, comme comparer.py ---
    t0 = time.time()
    rejeu = Backtester(cfg, registry=registre)
    profit_separe = 0.0
    trades_separes = 0
    gagnants_separes = 0
    etages_separes: dict[int, dict] = {}
    servis = 0
    for sym in symboles:
        try:
            r = rejeu.run(sym, bars=args.bougies, start_balance=args.capital)
        except Exception as exc:  # noqa: BLE001
            print(f"  ecarte {sym} : {str(exc)[:60]}")
            continue
        servis += 1
        profit_separe += r.end_balance - r.start_balance
        for t in r.trades:
            if t.partial:
                continue
            trades_separes += 1
            gagnants_separes += 1 if t.profit > 0 else 0
            d = etages_separes.setdefault(int(t.etages or 1),
                                          {"trades": 0, "profit": 0.0,
                                           "gagnants": 0})
            d["trades"] += 1
            d["profit"] += t.profit
            d["gagnants"] += 1 if t.profit > 0 else 0
    duree_separe = time.time() - t0

    # --- 2. Un seul compte partage ---
    t0 = time.time()
    porte = BacktestPortefeuille(cfg, registry=registre).run(
        symboles, bars=args.bougies, start_balance=args.capital)
    duree_porte = time.time() - t0
    s = porte.stats()

    # --- Restitution ---
    capital_engage = args.capital * servis
    print("=" * 74)
    print("  COMPTES SEPARES — ce que mesure comparer.py")
    print("=" * 74)
    print(f"  instruments servis     : {servis}")
    print(f"  capital reellement mis : {capital_engage:,.0f} EUR "
          f"({servis} x {args.capital:.0f})".replace(",", " "))
    print(f"  trades                 : {trades_separes}")
    if trades_separes:
        print(f"  reussite               : "
              f"{gagnants_separes / trades_separes * 100:.1f} %")
    print(f"  resultat               : {profit_separe:+,.2f} EUR".replace(",", " "))
    if capital_engage:
        print(f"  rendement              : "
              f"{profit_separe / capital_engage * 100:+.2f} % du capital mis")
    print(f"  duree                  : {duree_separe:.0f} s")
    print()
    print("=" * 74)
    print("  UN SEUL COMPTE — ce que vit le robot")
    print("=" * 74)
    print(f"  instruments            : {s.get('instruments', 0)}")
    print(f"  capital reellement mis : {args.capital:,.0f} EUR".replace(",", " "))
    print(f"  trades                 : {s.get('trades', 0)}")
    print(f"  reussite               : {s.get('taux_reussite_pct', 0)} %")
    print(f"  resultat               : {s.get('resultat', 0):+,.2f} EUR".replace(",", " "))
    print(f"  rendement              : {s.get('rendement_pct', 0):+.2f} %")
    print(f"  pire recul             : {s.get('drawdown_max_pct', 0):.1f} %")
    print(f"  duree                  : {duree_porte:.0f} s")
    print()

    print("=" * 74)
    print("  CE QUE RAPPORTE UNE POSITION SELON SES ETAGES DE PYRAMIDE")
    print("=" * 74)
    print(f"  {'etages':>8} | {'comptes separes':>28} | {'un seul compte':>26}")
    print(f"  {'':>8} | {'trades':>8}{'profit':>10}{'/trade':>10} | "
          f"{'trades':>8}{'profit':>9}{'/trade':>9}")
    print("  " + "-" * 70)
    tous = sorted(set(etages_separes) | set(s.get("par_etage", {})))
    for e in tous:
        a = etages_separes.get(e, {"trades": 0, "profit": 0.0})
        b = s.get("par_etage", {}).get(e, {"trades": 0, "profit": 0.0,
                                           "par_trade": 0.0})
        pa = a["profit"] / a["trades"] if a["trades"] else 0.0
        print(f"  {e:>8} | {a['trades']:>8}{a['profit']:>+10.0f}{pa:>+10.2f} | "
              f"{b['trades']:>8}{b['profit']:>+9.0f}{b.get('par_trade', 0):>+9.2f}")
    print()
    atteints_separe = max(etages_separes) if etages_separes else 0
    atteints_porte = max(s.get("par_etage", {})) if s.get("par_etage") else 0
    print(f"  etage maximal atteint  —  comptes separes : {atteints_separe}"
          f"   |   un seul compte : {atteints_porte}")

    if args.json:
        with open(args.json, "w") as f:
            json.dump({
                "config": args.config, "paires": servis,
                "bougies": args.bougies, "capital": args.capital,
                "separes": {"trades": trades_separes, "profit": profit_separe,
                            "capital_engage": capital_engage,
                            "par_etage": etages_separes},
                "portefeuille": s,
            }, f, indent=1, default=float)
        print(f"\n  detail ecrit dans {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(principal())
