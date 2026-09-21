#!/usr/bin/env python3
"""La methode de la demo 1, mesuree sur des ACTIONS americaines.

POURQUOI CE FICHIER EXISTE. Le CLAUDE.md le reclame depuis le
9 septembre, avant tout transfert chez IBKR : « un Donchian 20 jours sur
actions n'est pas le meme animal qu'en crypto -- horaires, gaps
d'ouverture, correlations ». Ces donnees n'avaient jamais ete
telechargees, et la demande de l'operateur d'ouvrir un compte de
demonstration IBKR avec la methode de la demo 1 rend la question
immediate : la methode tient-elle sur ce marche-la ?

Armer un reglage sur un marche ou il n'a jamais ete mesure, c'est
exactement l'erreur du 30 aout -- huit paires, trente jours, et une
conclusion inversee des qu'on a mesure pour de vrai.

    python3 mesurer_actions.py --mois 6
"""
from __future__ import annotations

import argparse
import copy
import math
import sys

from gold_bot.backtest_portefeuille import BacktestPortefeuille
from gold_bot.datasources import DataRegistry
from gold_bot.settings import BotConfig
from gold_bot.universe import Universe, univers_actions


def ligne(nom: str, res) -> str:
    s = res.stats()
    t = s.get("trades", 0)
    if not t:
        return f"  {nom:<34} {'aucun trade':>12}"
    perdantes = t - round(s["taux_reussite_pct"] / 100 * t)
    profits = [x.profit for x in res.trades if not x.partial]
    moyenne = sum(profits) / len(profits)
    var = sum((p - moyenne) ** 2 for p in profits) / max(1, len(profits) - 1)
    incert = 2 * math.sqrt(var / len(profits))
    verdict = ("BENEFICE" if moyenne - incert > 0
               else "PERTE" if moyenne + incert < 0 else "indiscernable")
    return (f"  {nom:<34} {t:>5} {perdantes:>4} ({perdantes/t*100:>3.0f}%) "
            f"{s['resultat']:>+8.0f} {s['rendement_pct']:>+7.1f}% "
            f"{s['drawdown_max_pct']:>6.1f}% {moyenne:>+6.2f}+-{incert:<5.2f}  {verdict}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mois", type=float, default=6.0)
    ap.add_argument("--capital", type=float, default=3300.0)
    ap.add_argument("--decalage", type=int, default=0)
    ap.add_argument("--base", default="robot.demo.json")
    args = ap.parse_args()

    PRECHAUFFE = 150
    bougies = PRECHAUFFE + int(round(args.mois * 30))

    cfg = copy.deepcopy(BotConfig.load(args.base))
    # La bride par famille vient d'une experience, pas de la methode.
    cfg.risk.max_per_correlation_group = 99

    # L'UNIVERS DU REJEU DOIT ETRE CELUI DES ACTIONS, pas le catalogue
    # crypto : sans ca, `check_exposure` et le dimensionnement liraient
    # des instruments qui n'existent pas dans la mesure.
    actions = univers_actions()
    moteur = BacktestPortefeuille(cfg, registry=DataRegistry())
    moteur.rejeu.universe = Universe(actions)

    print(f"{len(actions)} actions americaines, {bougies - PRECHAUFFE} bougies "
          f"tradees (~{args.mois:.0f} mois) + {PRECHAUFFE} de prechauffage,")
    print(f"UN compte de {args.capital:.0f} EUR, methode de la demo 1\n")
    print(f"  {'marche':<34} {'trad':>5} {'perdantes':>10} {'resultat':>8} "
          f"{'rendem':>8} {'recul':>7} {'par trade':>13}  verdict")
    print("  " + "-" * 104)

    res = moteur.run([i.symbol for i in actions], bars=bougies,
                     start_balance=args.capital, decalage=args.decalage)
    # L'ETIQUETTE SE LIT DANS LA CONFIGURATION, elle ne se recopie pas.
    # Premier jet : elle disait « demo 1 / Donchian 10 j » alors que le
    # rejeu tournait sur robot.demo2.json (momentum). Meme defaut que la
    # « methode » affichee dans l'application, qui a menti une semaine.
    from gold_bot.methode import resume_methode
    print(ligne(f"ACTIONS US — {resume_methode(cfg)[:26]}", res))
    if res.ecartes:
        print(f"\n  {len(res.ecartes)} ecartees : "
              f"{', '.join(list(res.ecartes)[:6])}")
        for sym, motif in list(res.ecartes.items())[:2]:
            print(f"     {sym} : {motif}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
