#!/usr/bin/env python3
"""Pourquoi le robot n'a-t-il pris aucune position ?

    python3 pourquoi_pas_de_trade.py --config robot.bitvavo.json

Fait UN seul cycle de scan, sans jamais passer d'ordre, et repond a la seule
question qui compte quand le compte ne bouge pas : QU'EST-CE QUI A REFUSE, et
combien de fois.

Un robot qui ne trade pas et un robot qui trade mal se corrigent a l'oppose
l'un de l'autre. Deviner lequel des deux on a sous les yeux coute des jours.
Ce script le dit en trente secondes, en nommant le filtre fautif et en
montrant de combien il s'en est fallu.
"""
from __future__ import annotations

import argparse
import collections
import logging
import os
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent
sys.path.insert(0, str(RACINE))

from gold_bot.core import Side  # noqa: E402
from gold_bot.dual_scalping_engine import DualScalpingEngine  # noqa: E402
from gold_bot.settings import BotConfig  # noqa: E402

GRAS, FIN, JAUNE, VERT, ROUGE = "\033[1m", "\033[0m", "\033[33m", "\033[32m", "\033[31m"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--config", default=os.getenv("GB_CONFIG", "robot.bitvavo.json"))
    p.add_argument("--tout", action="store_true",
                   help="detailler chaque instrument, pas seulement le resume")
    args = p.parse_args()

    logging.basicConfig(level=logging.WARNING,
                        format="%(levelname)-7s %(name)-22s %(message)s")

    cfg = BotConfig.load(args.config)
    # AUCUN ordre ne doit partir d'un diagnostic.
    cfg.engine.dry_run = True
    problemes = cfg.validate()
    if problemes:
        for msg in problemes:
            print(f"{ROUGE}configuration : {msg}{FIN}")
        return 2

    moteur = DualScalpingEngine(cfg)
    if not moteur.start():
        print(f"{ROUGE}Le moteur n'a pas pu demarrer (voir les messages ci-dessus).{FIN}")
        return 1

    positions = moteur.broker.positions()
    compte = moteur.broker.account()

    print(f"\n{GRAS}Etat au moment du scan{FIN}")
    print(f"  capital           : {compte.equity:.2f} {compte.currency}")
    print(f"  liquidites libres : {compte.margin_free:.2f} {compte.currency}")
    print(f"  positions ouvertes: {len(positions)}")
    print(f"  unite d'entree    : {cfg.strategy.entry_tf}"
          f"  (mode {cfg.strategy.mode}, {cfg.strategy.min_confirmations} confirmation(s) mini,"
          f" score mini {cfg.strategy.min_score})")

    # --- Le robot s'autorise-t-il seulement a chercher ? ---
    autorise, motif = moteur.risk.can_trade(positions)
    print(f"\n{GRAS}1. Le robot a-t-il le droit de chercher ?{FIN}")
    if autorise:
        print(f"  {VERT}oui{FIN}")
    else:
        print(f"  {ROUGE}NON — {motif}{FIN}")
        print(f"\n  {GRAS}C'est ici que tout s'arrete.{FIN} Aucun scan n'a lieu tant que")
        print("  cette condition tient : ce n'est pas la strategie qui bloque.")
        return 0

    arret, pourquoi = moteur.objectives.should_stop_trading()
    if arret:
        print(f"  {ROUGE}mais la gestion d'objectif suspend la recherche : {pourquoi}{FIN}")
        return 0

    # --- Le scan lui-meme ---
    print(f"\n{GRAS}2. Que dit le scan ?{FIN}")
    sens = None if getattr(moteur.broker, "supports_short", True) else {Side.BUY}
    if sens is not None:
        print(f"  {JAUNE}Ce lieu d'execution ne permet QUE l'achat : toute alerte de")
        print(f"  vente est ecartee avant meme d'etre evaluee.{FIN}")

    resultat = moteur.scanner.scan(
        score_bonus=moteur.objectives.score_threshold_bonus(),
        exclude={p.symbol for p in positions},
        allowed_sides=sens,
    )
    print(f"  {resultat.summary()}")

    # --- Le comptage des refus : le coeur du diagnostic ---
    causes: collections.Counter = collections.Counter()
    marges: dict[str, list[float]] = collections.defaultdict(list)
    valides = []

    for ev in resultat.evaluations:
        if ev.valid:
            valides.append(ev)
            continue
        rates = ev.failed_gates()
        if rates:
            for g in rates:
                causes[f"filtre : {g.name}"] += 1
        elif ev.side is None:
            causes["aucun sens degage (ni achat ni vente)"] += 1
        elif ev.mode == "quorum" and ev.confirmed < ev.required:
            causes[f"quorum : {ev.confirmed}/{ev.required} confirmations"] += 1
            marges["quorum"].append(ev.required - ev.confirmed)
        elif ev.score < ev.threshold:
            causes["score sous le seuil"] += 1
            marges["score"].append(ev.threshold - ev.score)
        else:
            causes["refus non classe"] += 1

    for sym, err in resultat.errors.items():
        tete = err.split(":")[0].strip()
        causes[f"ecarte avant evaluation : {tete}"] += 1

    print(f"\n{GRAS}3. Ce qui a refuse, et combien de fois{FIN}")
    if not causes:
        print(f"  {VERT}rien : aucun instrument n'a ete refuse.{FIN}")
    total = sum(causes.values())
    for cause, n in causes.most_common():
        part = n / total * 100 if total else 0
        barre = "#" * int(part / 3)
        print(f"  {n:4d}  ({part:4.1f} %)  {barre:<34s} {cause}")

    if marges.get("score"):
        moy = sum(marges["score"]) / len(marges["score"])
        print(f"\n  score : il manquait {moy:.3f} en moyenne "
              f"(seuil {cfg.strategy.min_score}). "
              f"{'Le seuil est la vraie barriere.' if moy < 0.08 else 'Les signaux sont loin du compte, baisser le seuil ne suffirait pas.'}")
    if marges.get("quorum"):
        moy = sum(marges["quorum"]) / len(marges["quorum"])
        print(f"\n  quorum : il manquait {moy:.1f} confirmation(s) en moyenne "
              f"(exigees : {cfg.strategy.min_confirmations}).")

    # --- Et si un signal etait valide, passerait-il le dimensionnement ? ---
    print(f"\n{GRAS}4. Les signaux valides survivent-ils au dimensionnement ?{FIN}")
    if not valides:
        print("  aucun signal valide a ce cycle : rien a dimensionner.")
        print(f"  {JAUNE}Le blocage est donc en amont (section 3), pas dans l'argent.{FIN}")
    else:
        for ev in sorted(valides, key=lambda e: -e.priority_score)[:10]:
            inst = moteur.universe.get(ev.symbol)
            d = moteur.risk.size_position(
                inst, ev.side, ev.entry, ev.stop_loss, ev.take_profit,
                open_positions=positions, universe_lookup=moteur.universe.get,
                extra_multiplier=moteur.objectives.risk_multiplier()[0],
                spread=ev.spread, available_cash=compte.margin_free)
            if d.allowed:
                print(f"  {VERT}OK {FIN} {ev.symbol:10s} {d.lots} lot(s), "
                      f"risque {d.risk_amount:.2f} {compte.currency}, "
                      f"cout {d.cost_ratio_pct:.0f} % du risque")
            else:
                print(f"  {ROUGE}NON{FIN} {ev.symbol:10s} {d.reason}")

    if args.tout:
        print(f"\n{GRAS}5. Detail par instrument{FIN}")
        for ligne in moteur.scanner.report(resultat, verbose=True):
            print(f"  {ligne}")

    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
