#!/usr/bin/env python3
"""Compare plusieurs strategies sur l'historique, et les classe.

POURQUOI CET OUTIL EXISTE

Pendant deux jours, les reglages ont ete essayes EN ARGENT REEL : chaque
essai coutait des euros, prenait des heures, et ne donnait qu'un seul
echantillon. Le 28 aout au soir : 72 trades, 2,8 % de reussite, aucune
position fermee en positif.

Le moteur de rejeu du projet permet de faire l'inverse — essayer vingt
configurations en quelques minutes, sur des annees d'historique, sans
engager un centime. C'est la seule facon honnete de repondre a « est-ce
que ce systeme fonctionne ? ».

CE QUE CET OUTIL DIT, ET CE QU'IL NE DIT PAS

Il mesure ce qu'une configuration AURAIT fait sur le passe. Il ne promet
rien sur l'avenir. Un backtest ne reproduit ni les elargissements de
spread sur annonce, ni le glissement reel, ni les ordres refuses — il est
donc toujours un peu plus optimiste que la realite.

Une regle a ne pas oublier : sous 30 trades, un resultat ne veut rien
dire. L'outil le signale au lieu de laisser croire a une decouverte.

    python3 comparer.py                       les variantes livrees
    python3 comparer.py --bars 2000           plus d'historique
    python3 comparer.py --symbols BTCUSD,ETHUSD,SOLUSD
"""
from __future__ import annotations

import argparse
import copy
import logging
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gold_bot.backtest import Backtester
from gold_bot.settings import BotConfig

# Les cryptos les plus liquides de l'univers : spreads les plus serres,
# donc le terrain le PLUS favorable. Ce qui echoue ici echouera partout.
SYMBOLES = ["BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "ADAUSD",
            "AVAXUSD", "LINKUSD", "DOTUSD"]

MINUTES = {"M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440}


def variante(nom: str, **reglages) -> tuple[str, dict]:
    return nom, reglages


# Chaque variante ne change QUE ce qui est nomme : le reste vient de la
# configuration en service, pour que la comparaison porte sur une seule
# difference a la fois.
VARIANTES = [
    variante("M15 tel quel"),
    variante("M15 sans bougies obligatoires", require_candle_confirmation=False),
    variante("M15 score exigeant", min_score=0.55),
    variante("H4", entry_tf="H4", trigger_tf="H1", context_tf="H4", bias_tf="D1"),
    variante("H4 sans bougies", entry_tf="H4", trigger_tf="H1", context_tf="H4",
             bias_tf="D1", require_candle_confirmation=False),
    variante("D1", entry_tf="D1", trigger_tf="H4", context_tf="D1", bias_tf="D1"),
    variante("D1 sans bougies", entry_tf="D1", trigger_tf="H4", context_tf="D1",
             bias_tf="D1", require_candle_confirmation=False),
]


def config_pour(base: BotConfig, reglages: dict) -> BotConfig:
    cfg = copy.deepcopy(base)
    for cle, valeur in reglages.items():
        cible = cfg.trade if hasattr(cfg.trade, cle) else cfg.strategy
        setattr(cible, cle, valeur)
    # Le stop temporel doit suivre l'unite de temps, sinon on compare une
    # strategie D1 a qui on laisse trois heures pour se former.
    depart = MINUTES.get(base.strategy.entry_tf, 15)
    arrivee = MINUTES.get(cfg.strategy.entry_tf, depart)
    cfg.trade.time_stop_minutes = base.trade.time_stop_minutes / depart * arrivee
    return cfg


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="robot.bitvavo.json")
    ap.add_argument("--bars", type=int, default=1500)
    ap.add_argument("--symbols", default="")
    ap.add_argument("--capital", type=float, default=186.0)
    ap.add_argument("--spread-x", type=float, default=1.0,
                    help="multiplie le spread suppose : 1 = modele, 3 = pessimiste")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.WARNING,
                        format="%(levelname)s %(name)s %(message)s")
    if not args.verbose:
        logging.getLogger("gold_bot").setLevel(logging.ERROR)

    # LE SPREAD EST LE POINT FAIBLE DU REJEU.
    #
    # Le modele suppose 0,05 % du prix pour toutes les cryptos. Les
    # journaux du 28 aout montrent des spreads reels de 2 a 20 % de l'ATR,
    # soit 0,06 a 1,2 % du prix selon l'instrument : le modele est juste
    # sur les plus liquides et beaucoup trop optimiste ailleurs.
    #
    # Un avantage qui disparait quand on double le spread n'est pas un
    # avantage, c'est une hypothese. Ce reglage permet de le verifier.
    if args.spread_x != 1.0:
        import gold_bot.backtest as _bt
        _origine = _bt.spread_estime
        _bt.spread_estime = lambda inst, prix: _origine(inst, prix) * args.spread_x

    base = BotConfig.load(args.config)
    symboles = ([s.strip().upper() for s in args.symbols.split(",") if s.strip()]
                or SYMBOLES)

    print("=" * 78)
    print(f"  COMPARAISON DE STRATEGIES — {len(symboles)} instruments, "
          f"{args.bars} bougies, capital {args.capital:.0f} EUR")
    print("=" * 78)
    print(f"  Frais supposes : {base.risk.commission_pct*100:.2f} % par cote "
          f"(tarif normal, hors promotion)")
    print(f"  Spread suppose : modele x{args.spread_x:g}"
          + ("   <- test de robustesse" if args.spread_x != 1.0 else ""))
    print("  Chaque variante ne change qu'une chose par rapport a la config en service.")
    print(f"  Instruments : {', '.join(symboles)}\n")

    resultats = []
    for nom, reglages in VARIANTES:
        cfg = config_pour(base, reglages)
        debut = time.time()
        trades, gagnants, somme_r, profit, dd = 0, 0, 0.0, 0.0, 0.0
        echecs = []
        for sym in symboles:
            try:
                res = Backtester(cfg).run(sym, bars=args.bars,
                                          start_balance=args.capital)
            except Exception as exc:  # noqa: BLE001
                echecs.append(f"{sym}: {str(exc)[:40]}")
                continue
            reels = [t for t in res.trades if not t.partial]
            trades += len(reels)
            gagnants += sum(1 for t in reels if t.profit > 0)
            somme_r += sum(t.r_multiple for t in reels)
            profit += res.end_balance - res.start_balance
            dd = max(dd, res.stats().get("drawdown_max", 0.0) or 0.0)
        resultats.append({
            "nom": nom, "trades": trades, "gagnants": gagnants,
            "reussite": gagnants / trades * 100 if trades else 0.0,
            "esperance": somme_r / trades if trades else 0.0,
            "profit": profit, "drawdown": dd,
            "secondes": time.time() - debut, "echecs": echecs,
        })
        etat = f"{trades:>4} trades" if trades else " aucun trade"
        print(f"  {nom:<34} {etat}   {time.time()-debut:>5.0f}s")

    resultats.sort(key=lambda r: (r["esperance"], r["profit"]), reverse=True)

    print("\n" + "=" * 78)
    print("  CLASSEMENT — par esperance en R (le seul chiffre qui se compare)")
    print("=" * 78)
    print(f"  {'variante':<34}{'trades':>7}{'reussite':>10}"
          f"{'esperance':>11}{'profit':>10}{'recul':>9}")
    for r in resultats:
        fiable = "" if r["trades"] >= 30 else "  (trop peu)"
        print(f"  {r['nom']:<34}{r['trades']:>7}{r['reussite']:>9.1f}%"
              f"{r['esperance']:>+11.3f}{r['profit']:>+10.2f}"
              f"{-r['drawdown']:>9.2f}{fiable}")

    solides = [r for r in resultats if r["trades"] >= 30]
    print("\n" + "-" * 78)
    if not solides:
        print("  Aucune variante n'atteint 30 trades : rien de concluant.")
        print("  Relance avec --bars 4000, ou avec plus d'instruments.")
    else:
        best = solides[0]
        print(f"  Meilleure sur {best['trades']} trades : {best['nom']}")
        print(f"     esperance {best['esperance']:+.3f} R par trade, "
              f"reussite {best['reussite']:.1f} %")
        if best["esperance"] <= 0:
            print("\n  AUCUNE VARIANTE N'EST GAGNANTE SUR L'HISTORIQUE.")
            print("  Ce n'est pas un reglage a corriger : c'est la strategie")
            print("  elle-meme qui ne trouve pas d'avantage sur ces marches.")
    for r in resultats:
        if r["echecs"]:
            print(f"\n  {r['nom']} — donnees manquantes : {'; '.join(r['echecs'][:3])}")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
