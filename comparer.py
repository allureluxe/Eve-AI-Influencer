#!/usr/bin/env python3
"""Compare plusieurs strategies sur l'historique, et les classe.

POURQUOI CET OUTIL EXISTE

Pendant deux jours, les reglages ont ete essayes EN ARGENT REEL : chaque
essai coutait des euros, prenait des heures, et ne donnait qu'un seul
echantillon. Le 28 aout au soir : 72 trades, 2,8 % de reussite, aucune
position fermee en positif par le robot.

Le moteur de rejeu du projet permet de faire l'inverse — essayer vingt
configurations en quelques minutes, sur des annees d'historique, sans
engager un centime. C'est la seule facon honnete de repondre a « est-ce
que ce systeme fonctionne ? ».

CE QUE CET OUTIL DIT, ET CE QU'IL NE DIT PAS

Il mesure ce qu'une configuration AURAIT fait sur le passe. Il ne promet
rien sur l'avenir. Un backtest ne reproduit ni les elargissements de
spread sur annonce, ni le glissement reel, ni les ordres refuses — il est
donc toujours un peu plus optimiste que la realite.

Il ne mesure PAS non plus le nombre de positions simultanees : le rejeu
traite un instrument a la fois et n'en tient qu'une a la fois. Le plafond
`risk.max_positions` ne peut donc pas etre teste ici — il se raisonne, il
ne se mesure pas. L'outil le rappelle en fin de rapport plutot que de
laisser croire le contraire.

Une regle a ne pas oublier : sous 30 trades, un resultat ne veut rien
dire. L'outil le signale au lieu de laisser croire a une decouverte.

    python3 comparer.py                       les variantes livrees
    python3 comparer.py --bars 2000           plus d'historique
    python3 comparer.py --symbols BTCUSD,ETHUSD,SOLUSD
    python3 comparer.py --spread-x 3          test de robustesse
"""
from __future__ import annotations

import argparse
import copy
import logging
import os
import statistics
import sys
import time
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gold_bot.backtest import Backtester
from gold_bot.settings import BotConfig
from gold_bot.sorties import (CATEGORIES, categorie_de_sortie,  # noqa: F401
                              duree_lisible, repartition)

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
H1 = dict(entry_tf="H1", trigger_tf="M15", context_tf="H4", bias_tf="D1",
          require_candle_confirmation=False)

# « Rapide » = les trois leviers qui font qu'un trade se termine tot et
# encaisse quelque chose, au lieu de courir apres un objectif qui recule :
#   - objectif plus proche             (on vise moins loin)
#   - prise partielle a 1 R            (on encaisse une part en chemin)
#   - pas d'extension d'objectif       (l'objectif cesse de fuir)
RAPIDE = dict(tp_r_multiple=1.5, partial_enabled=True, extend_enabled=False)

VARIANTES = [
    variante("en service (H4, telle quelle)"),

    # --- un levier a la fois, pour savoir lequel agit ---
    variante("+ prise partielle a 1 R", partial_enabled=True),
    variante("+ objectif fixe (sans extension)", extend_enabled=False),
    variante("+ objectif plus proche (1,5 R)", tp_r_multiple=1.5),
    variante("+ trailing plus serre", trail_start_r=0.8, trail_atr_mult=0.8),

    # --- les trois leviers ensemble ---
    variante("rapide (1,5 R + partielle + fixe)", **RAPIDE),
    variante("rapide + stop temporel 24 h", **RAPIDE, stop_temporel_bougies=6),
    variante("rapide, objectif 1,2 R", tp_r_multiple=1.2,
             partial_enabled=True, extend_enabled=False),

    # --- une unite de temps plus rapide : le cout decide ---
    variante("H1 — plafond 15 %", **H1, plafond_cout=15.0),
    variante("H1 rapide — plafond 15 %", **H1, **RAPIDE, plafond_cout=15.0),
]


def config_pour(base: BotConfig, reglages: dict) -> BotConfig:
    cfg = copy.deepcopy(base)
    bougies_stop = None
    for cle, valeur in reglages.items():
        # Le plafond de cout vit dans trois sections et doit rester
        # coherent : le desaccorder ferait filtrer a un endroit ce qu'un
        # autre laisse passer.
        if cle == "plafond_cout":
            cfg.risk.max_cost_ratio_pct = valeur
            cfg.strategy.max_cost_ratio_pct = valeur
            cfg.trade.max_cost_ratio_pct = valeur
            continue
        if cle == "stop_temporel_bougies":
            bougies_stop = valeur
            continue
        cible = cfg.trade if hasattr(cfg.trade, cle) else cfg.strategy
        setattr(cible, cle, valeur)

    # Le stop temporel doit suivre l'unite de temps, sinon on compare une
    # strategie H1 a qui on laisse deux jours pour se former.
    depart = MINUTES.get(base.strategy.entry_tf, 15)
    arrivee = MINUTES.get(cfg.strategy.entry_tf, depart)
    cfg.trade.time_stop_minutes = base.trade.time_stop_minutes / depart * arrivee
    # Une variante peut l'exprimer en bougies : c'est la seule unite qui
    # garde le meme sens quand l'unite de temps change.
    if bougies_stop is not None:
        cfg.trade.time_stop_minutes = float(bougies_stop * arrivee)
    return cfg


def resumer(trades: list, partielles: int, profit: float, dd: float,
            echecs: Optional[list[str]] = None) -> dict:
    """Resume une liste de trades termines. Sans reseau : testable.

    `trades` ne contient QUE des trades complets — les prises partielles
    sont comptees a part, sinon un trade coupe en deux compterait double
    et diluerait l'esperance par un demi-trade qui n'existe pas.
    """
    echecs = echecs or []
    n = len(trades)
    if not n:
        return {"trades": 0, "profit": profit, "echecs": echecs,
                "partielles": partielles, "drawdown": dd}

    gagnants = [t for t in trades if t.profit > 0]
    # Un `if t.closed_at and t.opened_at` parait equivalent et ne l'est
    # pas : un horodatage a zero est faux au sens booleen, et le trade
    # disparaissait du calcul sans rien signaler. On teste ce qu'on veut
    # vraiment savoir — que la duree ait un sens.
    durees = [(t.closed_at - t.opened_at) / 3600.0 for t in trades
              if t.closed_at is not None and t.opened_at is not None
              and t.closed_at >= t.opened_at]
    sorties = repartition(trades)

    return {
        "trades": n,
        "gagnants": len(gagnants),
        "reussite": len(gagnants) / n * 100,
        "esperance": sum(t.r_multiple for t in trades) / n,
        "profit": profit,
        "drawdown": dd,
        "partielles": partielles,
        "duree_mediane": statistics.median(durees) if durees else 0.0,
        # Jusqu'ou le trade est monte en notre faveur, et ce qu'on en a
        # garde. L'ecart entre les deux, c'est le benefice rendu au marche.
        "r_favorable": sum(t.max_favorable_r for t in trades) / n,
        "sorties": sorties,
        "echecs": echecs,
    }


def mesurer(cfg: BotConfig, symboles: list[str], bars: int,
            capital: float) -> dict:
    """Rejoue une configuration sur tous les instruments et resume."""
    trades: list = []
    partielles = 0
    profit, dd = 0.0, 0.0
    echecs: list[str] = []
    for sym in symboles:
        try:
            res = Backtester(cfg).run(sym, bars=bars, start_balance=capital)
        except Exception as exc:  # noqa: BLE001
            echecs.append(f"{sym}: {str(exc)[:40]}")
            continue
        trades.extend([t for t in res.trades if not t.partial])
        partielles += sum(1 for t in res.trades if t.partial)
        profit += res.end_balance - res.start_balance
        dd = max(dd, res.stats().get("drawdown_max", 0.0) or 0.0)
    return resumer(trades, partielles, profit, dd, echecs)


def rapport(resultats: list[dict]) -> None:
    """Imprime les trois tableaux. Separe de la mesure pour etre testable."""
    resultats.sort(key=lambda r: (r.get("esperance", -9), r["profit"]),
                   reverse=True)
    solides = [r for r in resultats if r["trades"] >= 30]

    # ------------------------------------------------------------------
    print("\n" + "=" * 92)
    print("  1. CLASSEMENT — par esperance en R (le seul chiffre qui se compare)")
    print("=" * 92)
    print(f"  {'variante':<38}{'trades':>7}{'reussite':>10}"
          f"{'esperance':>11}{'profit':>10}{'recul':>9}")
    for r in resultats:
        if not r["trades"]:
            print(f"  {r['nom']:<38}{'aucun trade':>47}")
            continue
        fiable = "" if r["trades"] >= 30 else "  (trop peu)"
        print(f"  {r['nom']:<38}{r['trades']:>7}{r['reussite']:>9.1f}%"
              f"{r['esperance']:>+11.3f}{r['profit']:>+10.2f}"
              f"{-r['drawdown']:>9.2f}{fiable}")

    # ------------------------------------------------------------------
    print("\n" + "=" * 92)
    print("  2. COMMENT LES TRADES SE TERMINENT (en % des trades)")
    print("=" * 92)
    print("  « stop suiveur » = le stop a ete touche APRES avoir ete remonte :")
    print("  c'est une fermeture en GAIN, pas une perte. C'est la difference")
    print("  que le journal ne montre pas et qui fait croire que rien ne gagne.\n")
    print(f"  {'variante':<38}{'objectif':>10}{'stop suiv.':>12}"
          f"{'stop init.':>12}{'temporel':>10}{'retourn.':>10}")
    for r in resultats:
        if not r["trades"]:
            continue
        n = r["trades"]
        s = r["sorties"]
        print(f"  {r['nom']:<38}"
              f"{s['objectif']/n*100:>9.0f}%{s['stop suiveur']/n*100:>11.0f}%"
              f"{s['stop initial']/n*100:>11.0f}%{s['temporel']/n*100:>9.0f}%"
              f"{s['retournement']/n*100:>9.0f}%")

    # ------------------------------------------------------------------
    print("\n" + "=" * 92)
    print("  3. VITESSE, BENEFICE PRIS, ET BENEFICE RENDU")
    print("=" * 92)
    print("  « monte a » = le meilleur point atteint en notre faveur, en R.")
    print("  « garde »   = ce que la fermeture a reellement encaisse.")
    print("  L'ecart entre les deux est le benefice rendu au marche : c'est")
    print("  lui qu'une prise partielle ou un objectif plus proche recupere.\n")
    print(f"  {'variante':<38}{'duree med.':>12}{'ferme en gain':>15}"
          f"{'monte a':>10}{'garde':>9}{'rendu':>9}{'partielles':>12}")
    for r in resultats:
        if not r["trades"]:
            continue
        rendu = r["r_favorable"] - r["esperance"]
        print(f"  {r['nom']:<38}{duree_lisible(r['duree_mediane']):>12}"
              f"{r['reussite']:>14.0f}%{r['r_favorable']:>10.2f}"
              f"{r['esperance']:>+9.2f}{rendu:>9.2f}{r['partielles']:>12}")

    # ------------------------------------------------------------------
    print("\n" + "-" * 92)
    if not solides:
        print("  Aucune variante n'atteint 30 trades : rien de concluant.")
        print("  Relance avec --bars 4000, ou avec plus d'instruments.")
    else:
        best = solides[0]
        print(f"  Meilleure sur {best['trades']} trades : {best['nom']}")
        print(f"     esperance {best['esperance']:+.3f} R par trade, "
              f"reussite {best['reussite']:.1f} %, "
              f"duree mediane {duree_lisible(best['duree_mediane'])}")
        if best["esperance"] <= 0:
            print("\n  AUCUNE VARIANTE N'EST GAGNANTE SUR L'HISTORIQUE.")
            print("  Ce n'est pas un reglage a corriger : c'est la strategie")
            print("  elle-meme qui ne trouve pas d'avantage sur ces marches.")

        # La variante la plus rapide qui reste gagnante : c'est la question
        # posee (« des trades rapides »), et elle merite sa propre reponse.
        gagnantes = [r for r in solides if r["esperance"] > 0]
        if gagnantes:
            rapide = min(gagnantes, key=lambda r: r["duree_mediane"])
            if rapide["nom"] != best["nom"]:
                print(f"\n  La plus rapide qui reste gagnante : {rapide['nom']}")
                print(f"     {duree_lisible(rapide['duree_mediane'])} par trade, "
                      f"esperance {rapide['esperance']:+.3f} R, "
                      f"reussite {rapide['reussite']:.1f} %")

    print("\n  CE QUE CE RAPPORT NE MESURE PAS")
    print("  Le rejeu traite un instrument a la fois et n'en tient qu'une")
    print("  position a la fois. `risk.max_positions` et")
    print("  `max_per_correlation_group` n'ont donc AUCUN effet ici : les")
    print("  chiffres ci-dessus sont ceux d'une position isolee. Ouvrir plus")
    print("  de positions multiplie le nombre de trades — et le recul aussi.")

    for r in resultats:
        if r["echecs"]:
            print(f"\n  {r['nom']} — donnees manquantes : {'; '.join(r['echecs'][:3])}")
    print("=" * 92)


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

    print("=" * 92)
    print(f"  COMPARAISON DE STRATEGIES — {len(symboles)} instruments, "
          f"{args.bars} bougies, capital {args.capital:.0f} EUR")
    print("=" * 92)
    print(f"  Frais supposes : {base.risk.commission_pct*100:.2f} % par cote "
          f"(tarif normal, hors promotion)")
    print(f"  Spread suppose : modele x{args.spread_x:g}"
          + ("   <- test de robustesse" if args.spread_x != 1.0 else ""))
    print(f"  Reference      : {base.strategy.entry_tf}, objectif "
          f"{base.trade.tp_r_multiple:.1f} R, prise partielle "
          f"{'oui' if base.trade.partial_enabled else 'non'}, extension "
          f"{'oui' if base.trade.extend_enabled else 'non'}")
    print("  Chaque variante ne change qu'une chose par rapport a la config en service.")
    print(f"  Instruments : {', '.join(symboles)}\n")

    resultats = []
    for nom, reglages in VARIANTES:
        cfg = config_pour(base, reglages)
        debut = time.time()
        r = mesurer(cfg, symboles, args.bars, args.capital)
        r["nom"] = nom
        resultats.append(r)
        etat = f"{r['trades']:>4} trades" if r["trades"] else " aucun trade"
        print(f"  {nom:<38} {etat}   {time.time()-debut:>5.0f}s")

    rapport(resultats)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
