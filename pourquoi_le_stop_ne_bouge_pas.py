#!/usr/bin/env python3
"""Pourquoi le stop suiveur d'une position ne remonte-t-il pas ?

    python3 pourquoi_le_stop_ne_bouge_pas.py

POURQUOI CET OUTIL EXISTE. Le 9 septembre 2026, le stop suiveur a cesse
de remonter sur dix positions, et il a fallu TROIS corrections pour en
venir a bout. Les deux premieres ont echoue pour la meme raison : j'ai
raisonne sur le code au lieu de mesurer ce qu'il calculait vraiment.
L'operateur, lui, voyait simplement que les stops ne bougeaient pas.

Cet outil rejoue la LOGIQUE REELLE — memes indicateurs, meme ATR, meme
`TradeManager` que le robot en service — et affiche chaque terme de la
decision. Il n'estime rien. Aucun ordre n'est envoye.

Ce qu'il faut lire :

  progres ATR   la progression depuis l'entree, en ATR. C'est ELLE qui
                arme le cliquet — pas le R, dont le denominateur grossit
                a chaque etage de pyramide et empeche l'armement.
  arme          le cliquet est-il arme ? S'il ne l'est pas alors que la
                position a manifestement progresse, c'est le bug de
                septembre qui revient.
  suiveur       le niveau que le stop suiveur reclame.
  verdict       « monte » si le stop doit remonter. « deja plus haut »
                est NORMAL : un stop suiveur ne redescend jamais.
"""
from __future__ import annotations

import os
import sys

RACINE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RACINE)

from gold_bot.env import charger_env                        # noqa: E402

charger_env()

from gold_bot.trade_manager import ActionType         # noqa: E402
from gold_bot.engine import TradingEngine                   # noqa: E402

VERT, ROUGE, JAUNE, GRIS, FIN = "\033[32m", "\033[31m", "\033[33m", "\033[90m", "\033[0m"


def main() -> int:
    moteur = TradingEngine()
    # Les positions vivent dans la memoire du PROCESSUS du robot. Un
    # moteur neuf repart a vide : on rejoue donc la meme restauration
    # qu'au demarrage, sinon l'outil ne verrait rien a diagnostiquer.
    moteur._restore_positions()
    positions = moteur.broker.positions()
    if not positions:
        print("Aucune position ouverte.")
        return 0

    cfg = moteur.config
    tm = moteur.trade_manager.config
    print(f"\nstop suiveur : {tm.trail_atr_mult} ATR sous le plus-haut, "
          f"arme a {tm.trail_start_r} R "
          f"(= {tm.trail_start_r * tm.atr_stop_mult:.2f} ATR de progression)\n")
    print(f"  {'crypto':10}{'entree':>11}{'prix':>11}{'ATR':>10}"
          f"{'progres ATR':>13}{'arme':>7}{'stop':>11}{'suiveur':>11}  verdict")
    print("  " + "-" * 96)

    for pos in positions:
        instrument = moteur.universe.get(pos.symbol)
        if instrument is None:
            continue
        ctx = moteur.scanner.context(pos.symbol)
        try:
            moteur.scanner.refresh_symbol(instrument)
        except Exception as exc:                            # noqa: BLE001
            print(f"  {pos.symbol:10} donnees indisponibles : {str(exc)[:40]}")
            continue
        ind = ctx.indicators.get(cfg.strategy.entry_tf)
        tick = moteur.registry.tick(pos.symbol, instrument.asset_class)
        if ind is None or not ind.ready or tick is None:
            print(f"  {pos.symbol:10} {GRIS}indicateurs pas prets{FIN}")
            continue

        atr = ind.atr.value or 0.0
        prix = tick.exit_price_for(pos.side)
        pos.track(prix)
        sign = pos.side.sign
        progres = sign * (pos.max_favorable - pos.entry_price) / atr if atr else 0.0
        seuil = tm.trail_start_r * tm.atr_stop_mult

        # On appelle la VRAIE methode : c'est elle qui arme le cliquet.
        etages = [p for p in positions
                  if p.symbol == pos.symbol and p.side is pos.side]
        actions = moteur.trade_manager.manage(
            pos, tick, ind, chart=ctx.chart(cfg.strategy.entry_tf,
                                            instrument.round_step),
            digits=instrument.digits, etages=etages)

        suiveur = pos.max_favorable - sign * tm.trail_atr_mult * atr
        bouge = next((a for a in actions if a.type is ActionType.MODIFY_STOP), None)
        if bouge is not None:
            verdict = f"{VERT}MONTE a {bouge.price}{FIN}"
        elif not pos.trail_arme:
            verdict = (f"{ROUGE}CLIQUET NON ARME{FIN}" if progres >= seuil
                       else f"{GRIS}pas encore assez progresse{FIN}")
        elif sign * (suiveur - pos.stop_loss) <= 0:
            verdict = f"{GRIS}deja plus haut — normal{FIN}"
        else:
            verdict = f"{JAUNE}arme mais pas applique — A CREUSER{FIN}"

        print(f"  {pos.symbol.replace('USD',''):10}{pos.entry_price:>11.5f}"
              f"{prix:>11.5f}{atr:>10.5f}{progres:>13.2f}"
              f"{('oui' if pos.trail_arme else 'NON'):>7}"
              f"{pos.stop_loss:>11.5f}{suiveur:>11.5f}  {verdict}")

    print(f"\n{GRIS}  « deja plus haut » est le cas NORMAL : un stop suiveur ne"
          f" redescend jamais.\n  Ce qui doit alerter, c'est « CLIQUET NON ARME »"
          f" ou « arme mais pas applique ».{FIN}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
