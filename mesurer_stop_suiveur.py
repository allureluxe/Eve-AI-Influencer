#!/usr/bin/env python3
"""Le coussin du stop suiveur est-il trop large ?

DEMANDE DE L'OPERATEUR, 22 septembre 2026, deux fois de suite :

    « 70 900 stop et cours actuel 74 900, c'est enorme sur le BTC. Pour
    redescendre de 4 000 on perd tout le benef. »

    « Pour moi le stop il devrait monter a chaque fois que la position
    elle monte. [...] Et 4 000 entre les deux c'est enorme, c'est
    beaucoup trop. »

DEUX CHOSES DANS CETTE DEMANDE, ET UNE SEULE EST UN DEFAUT
==========================================================

1. « le stop doit monter a chaque fois que le prix monte » — IL LE FAIT
   DEJA. `trail = max_favorable - mult x ATR` se recalcule a chaque
   cycle depuis le PLUS HAUT ATTEINT, et le stop ne redescend jamais
   (cliquet). Ce n'est pas le mecanisme qui manque.

2. « 4 000 entre les deux c'est trop » — LA, c'est une vraie question,
   et elle n'a jamais ete mesuree sous cette forme. Sur la position BTC
   de la demo 2 le coussin vaut 2,77 ATR, soit 6 063 EUR sous le plus
   haut. Tant que le suiveur reste sous le point mort, c'est le point
   mort qui tient le stop — et il faudrait que le BTC atteigne 77 057
   pour que le suiveur reprenne la main.

CE QUI A DEJA ETE MESURE, ET QU'IL NE FAUT PAS REFAIRE
======================================================

Le 12 septembre, `trail_atr_mult` 2,2 contre 3,0 avec le canal 10 :
3,0 l'emporte. Et `micro_profit_enabled` — qui coupait les gagnants
entre 1 et 2 R — a ete mesure comme LE plus gros frein du robot.
9 trades sur 469 font 124 % du benefice : serrer, c'est les couper.

CE QUI N'A JAMAIS ETE MESURE
============================

Le bas de l'echelle. 2,2 et 3,0 ont ete compares ; 2,0, 1,5 et 1,0 ne
l'ont jamais ete. Et le SERRAGE APRES L'ABRI (`trail_serrage_apres_abri`,
0,5 aujourd'hui) n'a jamais ete pousse : c'est le reglage qui repond le
plus directement a la demande, puisqu'il ne touche QUE les positions
deja benaficiaires — exactement le cas qui fait rager l'operateur.

    python3 mesurer_stop_suiveur.py --paires 40 --bougies 700
    python3 mesurer_stop_suiveur.py --variante 3 --json /tmp/s.jsonl
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

# LE PLANCHER EST LE TROISIEME REGLAGE, ET IL EST DEMANDE NOMMEMENT
# =================================================================
#
# « resserrer jusqu'a un certain niveau max de resserrage pour pas
# faire fermer la position sur un petit retournement » : c'est
# `trail_min_atr_mult`, aujourd'hui a 0,8 ATR. Sans lui le multiple
# tend vers zero a mesure que la marge acquise grandit, et le moindre
# soubresaut sort la position.
#
# Les trois reglages forment un seul mecanisme et ne se mesurent pas
# separement : le coussin de DEPART, la vitesse a laquelle il se
# resserre une fois a l'abri, et le point ou il cesse de se resserrer.
#
# (nom, trail_atr_mult, trail_serrage_apres_abri, trail_min_atr_mult)
#
# Le serrage divise le multiple par (1 + serrage x abri_r) une fois le
# stop passe au-dessus du prix d'achat. A 0,5 et un abri de 0,17 R il ne
# retire que 8 % ; a 3,0 il en retirerait 34 %. C'est le levier qui agit
# uniquement sur les positions qui ne peuvent plus perdre.
VARIANTES = [
    ("3,0 ATR — EN SERVICE",              3.0, 0.5, 0.8),
    ("2,5 ATR",                           2.5, 0.5, 0.8),
    ("2,0 ATR",                           2.0, 0.5, 0.8),
    ("1,5 ATR",                           1.5, 0.5, 0.8),
    ("1,0 ATR",                           1.0, 0.5, 0.8),
    ("3,0 ATR + serrage fort (1,5)",      3.0, 1.5, 0.8),
    ("3,0 ATR + serrage tres fort (3,0)", 3.0, 3.0, 0.8),
    ("2,0 ATR + serrage fort (1,5)",      2.0, 1.5, 0.8),
    # LE MECANISME DEMANDE PAR L'OPERATEUR, dose de trois facons.
    # Coussin de depart reduit, serrage vif des l'abri, et un plancher
    # assez haut pour ne pas sortir sur un soubresaut.
    ("2,0 + serrage 3,0 + plancher 0,8",  2.0, 3.0, 0.8),
    ("2,0 + serrage 3,0 + plancher 1,2",  2.0, 3.0, 1.2),
    ("2,5 + serrage 3,0 + plancher 1,2",  2.5, 3.0, 1.2),
    ("2,0 + serrage 6,0 + plancher 1,2",  2.0, 6.0, 1.2),
]


def principal() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", default="robot.demo.json")
    p.add_argument("--paires", type=int, default=40)
    p.add_argument("--bougies", type=int, default=700)
    p.add_argument("--capital", type=float, default=3300.0)
    p.add_argument("--json", default="")
    # UNE VARIANTE PAR PROCESSUS — voir `mesurer_reserve.py` : huit
    # portefeuilles enchaines dans un seul processus se font tuer par
    # l'allocateur, qui ne rend pas la memoire entre deux passages.
    p.add_argument("--variante", type=int, default=-1)
    # HORS ECHANTILLON. Un reglage choisi sur une periode y parait
    # toujours bon ; c'est exactement ce qui s'est passe le 12 septembre,
    # quand 3,0 a battu 2,2 sur une seule fenetre. On recule donc de N
    # bougies pour rejouer sur une periode que le reglage n'a pas servi
    # a choisir.
    p.add_argument("--decalage", type=int, default=0)
    args = p.parse_args()

    logging.basicConfig(level=logging.ERROR)
    logging.getLogger("gold_bot").setLevel(logging.ERROR)

    base = BotConfig.load(args.config)
    registre = registre_pour(base)
    symboles = [i.symbol for i in Universe()
                if i.symbol.endswith("USD")][:args.paires]

    variantes = ([VARIANTES[args.variante]] if args.variante >= 0
                 else VARIANTES)
    if args.variante < 0:
        print(f"{len(symboles)} paires x {args.bougies} bougies, "
              f"capital {args.capital:.0f} EUR")
        print(f"  {'variante':<34}{'trades':>7}{'perdantes':>11}"
              f"{'resultat':>11}{'recul':>8}{'garde':>8}")
        print("  " + "-" * 79)

    lignes = []
    for nom, mult, serrage, plancher in variantes:
        cfg = BotConfig.load(args.config)
        cfg.trade.trail_atr_mult = mult
        cfg.trade.trail_serrage_apres_abri = serrage
        cfg.trade.trail_min_atr_mult = plancher
        t0 = time.time()
        r = BacktestPortefeuille(cfg, registry=registre).run(
            symboles, bars=args.bougies, start_balance=args.capital,
            decalage=args.decalage)
        s = r.stats()
        reels = [t for t in r.trades if not t.partial]
        perdantes = sum(1 for t in reels if t.profit <= 0)
        pct = perdantes / len(reels) * 100 if reels else 0.0
        # CE QUE L'OPERATEUR VEUT VRAIMENT SAVOIR : sur les trades
        # gagnants, quelle part du meilleur parcours a-t-on GARDEE ?
        # C'est ca, « rendre le benefice ». Un suiveur large la fait
        # baisser ; un suiveur serre la remonte mais coupe des trades.
        #
        # `max_favorable_r` porte le meilleur parcours en R, `r_multiple`
        # ce qu'on a reellement encaisse. Leur rapport est la part gardee.
        # On ne compte que les trades qui ONT progresse (pic > 0,5 R) :
        # sur ceux qui n'ont jamais rien donne, le rapport ne veut rien
        # dire et ferait du bruit.
        gardes = [max(0.0, t.r_multiple / t.max_favorable_r)
                  for t in reels if t.max_favorable_r > 0.5]
        garde = sum(gardes) / len(gardes) * 100 if gardes else 0.0
        lignes.append({
            "nom": nom, "trail_atr_mult": mult, "serrage": serrage, "plancher": plancher,
            "trades": len(reels), "perdantes": perdantes,
            "pct_perdantes": round(pct, 1),
            "resultat": s.get("resultat", 0.0),
            "recul_pct": s.get("drawdown_max_pct", 0.0),
            "garde_du_pic_pct": round(garde, 1),
            "decalage": args.decalage,
            "secondes": round(time.time() - t0),
        })
        print(f"  {nom:<34}{len(reels):>7}{perdantes:>6} ({pct:>3.0f}%)"
              f"{s.get('resultat', 0.0):>+11.0f}"
              f"{s.get('drawdown_max_pct', 0.0):>7.1f}%{garde:>7.0f}%")

    if args.json:
        mode = "a" if args.variante >= 0 else "w"
        with open(args.json, mode) as f:
            if args.variante >= 0:
                f.write(json.dumps(lignes[0], default=float) + "\n")
            else:
                json.dump(lignes, f, indent=1, default=float)
    if args.variante < 0:
        print()
        print("  « garde » = part du meilleur parcours reellement encaissee")
        print("  sur les trades gagnants. C'est le chiffre qui traduit")
        print("  « on rend tout le benefice ».")
    return 0


if __name__ == "__main__":
    sys.exit(principal())
