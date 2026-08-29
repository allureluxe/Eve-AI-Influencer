#!/usr/bin/env python3
"""Combien de temps pour aller de votre capital a votre cible ?

    python3 plan_croissance.py --cible 3000

Repond avec les chiffres du journal REEL, pas avec des hypotheses. Quand
le journal est vide, montre ce que chaque hypothese d'esperance donnerait
— et laisse voir laquelle est plausible.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent
sys.path.insert(0, str(RACINE))

from gold_bot.croissance import (ECHANTILLON_MINIMAL, PALIERS, diagnostiquer,
                                 drawdown_probable, projeter)
from gold_bot.settings import BotConfig
from gold_bot.state import TradeJournal

GRAS, FIN, VERT, JAUNE, ROUGE = "\033[1m", "\033[0m", "\033[32m", "\033[33m", "\033[31m"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--config", default=os.getenv("GB_CONFIG", "robot.bitvavo.json"))
    p.add_argument("--capital", type=float, default=None,
                   help="capital de depart (defaut : lu dans le journal/etat)")
    p.add_argument("--cible", type=float, default=3000.0)
    p.add_argument("--jours", type=float, default=0.0,
                   help="fenetre d'analyse du journal, en jours (0 = tout)")
    args = p.parse_args()

    cfg = BotConfig.load(args.config)
    journal = TradeJournal(instance=cfg.engine.broker)
    journal.load()
    depuis = time.time() - args.jours * 86400 if args.jours > 0 else 0.0
    stats = journal.stats(since=depuis)

    capital = args.capital
    if capital is None:
        capital = 186.0
        print(f"{JAUNE}capital non fourni : hypothese de {capital:.0f} EUR "
              f"(--capital pour corriger){FIN}")

    # Cadence reelle : trades termines / jours ecoules depuis le premier.
    trades_par_jour = 0.0
    if journal.trades:
        premier = min(t.closed_at for t in journal.trades)
        jours = max(1.0, (time.time() - premier) / 86400)
        trades_par_jour = len([t for t in journal.trades if not t.partial]) / jours

    print(f"\n{GRAS}Ce que dit votre journal{FIN}")
    if not stats.get("trades"):
        print(f"  {ROUGE}aucun trade termine.{FIN} L'esperance est INCONNUE — "
              "et c'est la seule chose qui")
        print("  determine le temps pour atteindre la cible.")
    else:
        print(f"  trades termines   : {stats['trades']}")
        print(f"  taux de reussite  : {stats['taux_reussite_pct']:.1f} %")
        print(f"  esperance         : {stats['esperance_R']:+.3f} R par trade")
        print(f"  facteur de profit : {stats.get('facteur_profit')}")
        print(f"  cadence mesuree   : {trades_par_jour:.1f} trade(s) par jour")

    if trades_par_jour <= 0:
        trades_par_jour = 6.0
        print(f"  {JAUNE}cadence inconnue : hypothese de {trades_par_jour:.0f} "
              f"trades/jour (H1, {cfg.risk.max_positions} places){FIN}")

    diag = diagnostiquer(capital, args.cible, stats, trades_par_jour)

    print(f"\n{GRAS}Palier actuel : {diag.palier.nom.upper()}{FIN}"
          f"  —  risque autorise {diag.palier.risque_pct} % par trade")
    print(f"  {diag.palier.commentaire}")
    if diag.palier_suivant:
        print(f"\n  Pour passer a « {diag.palier_suivant.nom} » "
              f"({diag.palier_suivant.risque_pct} % par trade), il manque :")
        for m in diag.manques or ["rien : le palier est atteint"]:
            print(f"    - {m}")

    if not diag.echantillon_suffisant():
        print(f"\n  {JAUNE}Moins de {ECHANTILLON_MINIMAL} trades : toute esperance "
              f"calculee ici est du bruit.{FIN}")
    elif not diag.esperance_fiable():
        print(f"\n  {JAUNE}L'esperance mesuree n'est pas encore distinguable du "
              f"hasard.{FIN}")
        print(f"  (il faudrait depasser {2/ (diag.trades ** 0.5):+.3f} R "
              f"sur {diag.trades} trades)")

    print(f"\n{GRAS}Temps pour aller de {capital:.0f} EUR a {args.cible:.0f} EUR{FIN}")
    jours = diag.jours_jusqu_a_la_cible()
    if jours is None:
        print(f"  {ROUGE}HORS D'ATTEINTE a l'esperance actuelle.{FIN}")
        print("  Une esperance nulle ou negative ne rend pas la cible lointaine :")
        print("  elle la rend inaccessible. Augmenter le risque ou la cadence")
        print("  ne ferait qu'atteindre zero plus vite.")
    else:
        print(f"  {VERT}~{jours:.0f} jours{FIN} "
              f"({jours/30:.1f} mois) au palier « {diag.palier.nom} »")

    print(f"\n{GRAS}Ce que donnerait chaque esperance{FIN}"
          f"  (cadence {trades_par_jour:.1f}/jour)")
    print(f"  {'esperance':>10s}", end="")
    for pal in PALIERS:
        print(f" {pal.risque_pct:>10.1f} %", end="")
    print("     <- risque par trade")
    for esp in (-0.10, 0.00, 0.05, 0.10, 0.20, 0.30):
        print(f"  {esp:>+9.2f} R", end="")
        for pal in PALIERS:
            j = projeter(capital, args.cible, pal.risque_pct, esp, trades_par_jour)
            print(f" {'jamais' if j is None else f'{j:>9.0f}j':>12s}", end="")
        print()

    print(f"\n{GRAS}Le prix a payer : la serie noire{FIN}")
    reussite = stats.get("taux_reussite_pct") or 45.0
    for pal in PALIERS:
        dd = drawdown_probable(pal.risque_pct, reussite)
        print(f"  palier {pal.nom:<13s} risque {pal.risque_pct:.1f} % -> "
              f"serie typique de {dd['serie_attendue']:.0f} pertes "
              f"= {dd['perte_pct']:.0f} % du capital")
    print(f"  (a {reussite:.0f} % de reussite, sur 200 trades ; la moitie du "
          "temps ce sera pire)")

    print(f"\n{GRAS}Ce qu'il faut retenir{FIN}")
    print("  Le risque, la cadence et le levier AMPLIFIENT le signe de")
    print("  l'esperance. Ils ne le changent pas. Tant que l'esperance n'est")
    print("  pas etablie sur un echantillon reel, la seule strategie qui")
    print(f"  fasse grandir un compte est celle qui l'empeche de mourir.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
