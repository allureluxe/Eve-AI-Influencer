#!/usr/bin/env python3
"""Leve un arret sur drawdown, DELIBEREMENT et jamais tout seul.

    python3 reinitialiser_arret.py                 montre l'etat, ne change rien
    python3 reinitialiser_arret.py --confirmer     recale le sommet et repart

POURQUOI CETTE COMMANDE N'EST PAS AUTOMATIQUE
---------------------------------------------
Le coupe-circuit de drawdown compare le capital au SOMMET historique du
compte. Quand il declenche, il a raison : de l'argent a ete perdu.

Mais ce sommet survit aux changements de strategie. Un compte tombe de
187 a 97 EUR avec une configuration remplacee depuis reste arrete a 48 %
de drawdown — et la nouvelle configuration, qui n'a rien perdu du tout,
ne peut jamais demarrer. Le robot se protege d'une strategie qui n'existe
plus.

Recaler le sommet est donc parfois legitime. Mais le faire AUTOMATIQUEMENT
au demarrage transformerait le coupe-circuit en decoration : il suffirait
d'un redemarrage pour effacer n'importe quelle perte. C'est exactement
l'erreur qu'un robot qui tourne seul ne doit pas pouvoir commettre.

D'ou cette commande separee, qui exige une confirmation explicite et
ecrit ce qu'elle a fait.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent
sys.path.insert(0, str(RACINE))

from gold_bot.env import charger_env  # noqa: E402
from gold_bot.settings import BotConfig  # noqa: E402
from gold_bot.state import StateStore  # noqa: E402

charger_env()

GRAS, FIN, VERT, JAUNE, ROUGE = "\033[1m", "\033[0m", "\033[32m", "\033[33m", "\033[31m"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="robot.bitvavo.json")
    p.add_argument("--capital", type=float, default=0.0,
                   help="capital reel actuel (defaut : le dernier connu)")
    p.add_argument("--confirmer", action="store_true",
                   help="applique reellement le recalage")
    args = p.parse_args()

    cfg = BotConfig.load(args.config)
    store = StateStore(instance=cfg.engine.broker)
    etat = store.load()

    sommet = float(etat.peak_equity or 0.0)
    capital = args.capital or float(etat.account_reference or 0.0)

    print(f"\n{GRAS}Etat memorise ({cfg.engine.broker}){FIN}")
    print(f"  sommet historique : {sommet:.2f}")
    print(f"  capital de reference : {capital:.2f}")
    if sommet > 0 and capital > 0:
        dd = max(0.0, (sommet - capital) / sommet * 100.0)
        print(f"  drawdown : {dd:.1f} %  (seuil d'arret : "
              f"{cfg.risk.max_drawdown_pct:.1f} %)")
    print(f"  arrete : {etat.halted}")
    if etat.halt_reason:
        print(f"  motif : {etat.halt_reason}")

    if not etat.halted and sommet <= capital:
        print(f"\n{VERT}Rien a faire : le robot n'est pas arrete.{FIN}\n")
        return 0

    if not args.confirmer:
        print(f"\n{JAUNE}{GRAS}Aucune modification.{FIN}")
        print("  Ce recalage efface la memoire d'une perte reelle. Ne le")
        print("  faites que si la configuration qui a perdu cet argent a")
        print("  effectivement ete remplacee — sinon vous rearmez un robot")
        print("  qui vient de prouver qu'il perd.\n")
        print(f"  Pour appliquer :")
        print(f"     python3 reinitialiser_arret.py --confirmer"
              + (f" --capital {capital:.2f}" if capital else "") + "\n")
        return 1

    if capital <= 0:
        print(f"\n{ROUGE}Capital inconnu : precisez --capital.{FIN}\n")
        return 2

    ancien = sommet
    etat.peak_equity = capital
    etat.account_reference = capital
    etat.halted = False
    etat.halt_reason = ""
    store.save()

    print(f"\n{VERT}{GRAS}Arret leve.{FIN}")
    print(f"  sommet recale de {ancien:.2f} a {capital:.2f}")
    print("  Le drawdown repart de zero : la prochaine serie de pertes")
    print(f"  declenchera de nouveau a {cfg.risk.max_drawdown_pct:.1f} %.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
