#!/usr/bin/env python3
"""Le momentum a date fixe contre notre cassure de canal, MEME compte.

POURQUOI CE FICHIER EXISTE. L'operateur a demande, le 20 septembre, une
seconde methode « rien a voir avec la notre » pour la demo 2 -- pas un
reglage different. La famille `momentum` a ete codee pour ca. Reste a
savoir si elle tient chez NOUS : nos frais, nos cryptos, notre budget de
risque partage entre toutes les paires.

Le rejeu de PORTEFEUILLE est le seul honnete ici : `comparer.py` ouvre un
compte neuf par crypto et additionne, ce qui suppose 45 comptes separes.
Celui-ci fait se disputer le meme euro.

    python3 mesurer_momentum.py --paires 40 --bougies 900
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import sys
from pathlib import Path

from gold_bot.backtest_portefeuille import BacktestPortefeuille
from gold_bot.settings import BotConfig


def univers(n: int) -> list[str]:
    """Les cryptos du catalogue, comme `comparer.py --univers-complet`."""
    from gold_bot.universe import Universe
    return [i.symbol for i in Universe() if i.asset_class == "crypto"][:n]


def ligne(nom: str, res) -> str:
    s = res.stats()
    t = s.get("trades", 0)
    if not t:
        return f"  {nom:<28} {'aucun trade':>10}"
    perdantes = t - round(s["taux_reussite_pct"] / 100 * t)
    # Incertitude : ecart-type des profits / racine(n), a 2 sigma.
    profits = [x.profit for x in res.trades if not x.partial]
    moyenne = sum(profits) / len(profits)
    var = sum((p - moyenne) ** 2 for p in profits) / max(1, len(profits) - 1)
    incert = 2 * math.sqrt(var / len(profits))
    verdict = ("BENEFICE" if moyenne - incert > 0
               else "PERTE" if moyenne + incert < 0
               else "indiscernable du hasard")
    return (f"  {nom:<28} {t:>6} {perdantes:>4} ({perdantes/t*100:>3.0f}%) "
            f"{s['resultat']:>+9.0f} {s['rendement_pct']:>+7.1f}% "
            f"{s['drawdown_max_pct']:>6.1f}% {moyenne:>+7.2f} +-{incert:>5.2f}  {verdict}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--paires", type=int, default=40)
    ap.add_argument("--bougies", type=int, default=900)
    ap.add_argument("--capital", type=float, default=3300.0)
    ap.add_argument("--decalage", type=int, default=0,
                    help="reculer de N bougies : mesure HORS ECHANTILLON")
    ap.add_argument("--formation", type=int, default=28)
    ap.add_argument("--detention", type=int, default=5)
    ap.add_argument("--seuil", type=float, default=0.0)
    ap.add_argument("--base", default="robot.demo2.json")
    ap.add_argument("--bride", action="store_true",
                    help="garder max_per_correlation_group tel qu'il est "
                         "dans la config (par defaut on le retire)")
    ap.add_argument("--pourquoi", action="store_true",
                    help="detailler les motifs de refus d'entree")
    args = ap.parse_args()

    symboles = univers(args.paires)
    base = BotConfig.load(args.base)

    # Le temoin : exactement ce qui tourne sur la demo 2 aujourd'hui.
    temoin = copy.deepcopy(base)

    # LA LIMITE PAR FAMILLE EST RETIREE DES DEUX COTES.
    #
    # `robot.demo2.json` porte `max_per_correlation_group: 1` -- c'est
    # l'experience de la veille, pas la methode. La laisser armee ferait
    # comparer « momentum bride » a « canal bride » et attribuerait a la
    # methode ce qui vient de la bride. On la retire des deux cotes ;
    # `--bride` la remet pour qui veut mesurer la bride elle-meme.
    #
    # 99, PAS 0. `check_exposure` teste
    # `same_group >= max_per_correlation_group` : a zero il refuse TOUTE
    # entree -- « aucune position », pas « aucune limite ». Premier jet de
    # ce fichier : ecrit a zero, la mesure a rendu 4 trades que j'ai
    # failli lire comme un resultat de la methode.
    if not args.bride:
        temoin.risk.max_per_correlation_group = 99

    # Le candidat : MEME risque, MEMES frais, MEME univers. Seule la
    # facon d'entrer et de sortir change -- c'est tout l'interet.
    cand = copy.deepcopy(base)
    cand.strategy.famille = "momentum"
    cand.strategy.momentum_formation = args.formation
    cand.strategy.momentum_seuil_pct = args.seuil
    cand.strategy.momentum_detention = args.detention
    cand.trade.detention_max_jours = float(args.detention)
    cand.trade.time_stop_minutes = 0.0   # exclu par la sortie a date fixe
    # Pas de pyramide : le papier n'en a pas, et en ajouter une ferait
    # mesurer autre chose que la methode publiee.
    cand.risk.pyramide_max = 0
    cand.risk.reserve_pyramide_pct = 0.0
    if not args.bride:
        cand.risk.max_per_correlation_group = 99

    for nom, cfg in (("temoin", temoin), ("candidat", cand)):
        soucis = cfg.validate()
        if soucis:
            print(f"configuration {nom} refusee :", file=sys.stderr)
            for s in soucis:
                print(f"  - {s}", file=sys.stderr)
            return 2

    periode = "HORS ECHANTILLON" if args.decalage else "sur la periode recente"
    print(f"{len(symboles)} paires, {args.bougies} bougies, UN compte de "
          f"{args.capital:.0f} EUR, {periode}\n")
    print(f"  {'methode':<28} {'trades':>6} {'perdantes':>10} "
          f"{'resultat':>9} {'rendem.':>8} {'recul':>7} {'/trade':>8}"
          f" {'incert.':>7}  verdict")
    print("  " + "-" * 108)

    for nom, cfg in (
        (f"canal 10 j (en service)", temoin),
        (f"momentum {args.formation}j / {args.detention}j", cand),
    ):
        res = BacktestPortefeuille(cfg).run(
            symboles, bars=args.bougies, start_balance=args.capital,
            decalage=args.decalage)
        print(ligne(nom, res))
        if args.pourquoi:
            # POURQUOI SI PEU DE TRADES ? Un resultat mesure sur 4 trades
            # ne dit rien ; le motif de refus, lui, dit tout de suite si
            # c'est la methode qui ne trouve rien ou une barriere qui
            # refuse tout en silence. C'est le piege recense trois fois
            # dans le CLAUDE.md.
            motifs = {}
            for r in res.par_instrument.values():
                for cle, n in getattr(r, "rejections", {}).items():
                    motifs[cle] = motifs.get(cle, 0) + n
            for cle, n in sorted(motifs.items(), key=lambda kv: -kv[1])[:8]:
                print(f"        refus {n:>7} x  {cle}")
            if res.ecartes:
                print(f"        {len(res.ecartes)} paires ecartees "
                      f"(donnees insuffisantes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
