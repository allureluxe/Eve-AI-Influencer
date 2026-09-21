#!/usr/bin/env python3
"""Croiser nos deux methodes : qui apporte quoi, l'entree ou la sortie ?

Demande de l'operateur le 21 septembre : « fais un test en melangeant
nos 2 methodes », sur six mois.

LE CARRE, ET POURQUOI IL EST OBLIGATOIRE
========================================

Chaque methode a une ENTREE et une SORTIE. Les comparer en bloc ne dit
pas laquelle des deux moities fait la difference -- et le CLAUDE.md
raconte deja une mesure gachee pour cette raison exacte (le stop temporel
du 6 septembre, ou le delai ET le critere avaient bouge ensemble ; tout
le gain venait du delai, et on s'appretait a armer l'autre).

On croise donc les quatre combinaisons :

                     sortie : stop suiveur     sortie : 5 jours
    entree cassure        A (en service)             C
    entree momentum            B                     D (demo 2)

A et D sont nos deux methodes telles qu'elles tournent. B et C sont les
melanges. Si C bat A, le gain vient de la SORTIE ; si B bat A, il vient
de l'ENTREE ; si aucun des deux ne bouge, les deux moities ne valent que
prises ensemble.

    E : les deux ENTREES reunies -- une cassure n'est prise que si la
        crypto monte aussi sur la fenetre longue. Ce n'est plus un
        croisement mais une CONJONCTION : moins de trades, en principe
        mieux choisis.

    python3 melanger_methodes.py --paires 25 --bougies 180
    python3 melanger_methodes.py --seulement C     # une seule, memoire
"""
from __future__ import annotations

import argparse
import copy
import math
import sys

from gold_bot.backtest_portefeuille import BacktestPortefeuille
from gold_bot.settings import BotConfig


def univers(n: int) -> list[str]:
    from gold_bot.universe import Universe
    return [i.symbol for i in Universe() if i.asset_class == "crypto"][:n]


def _sortie_date_fixe(cfg, jours: float) -> None:
    """La sortie du momentum : au Ne jour, sans condition."""
    cfg.trade.detention_max_jours = float(jours)
    cfg.trade.time_stop_minutes = 0.0


def _sortie_suiveur(cfg, base) -> None:
    """La sortie de notre canal : stop suiveur + stop temporel."""
    cfg.trade.detention_max_jours = 0.0
    cfg.trade.time_stop_minutes = base.trade.time_stop_minutes


def variantes(base: BotConfig, args) -> list[tuple[str, str, BotConfig]]:
    sortie = []

    def neuve():
        c = copy.deepcopy(base)
        # La bride « une position par famille » n'est pas une methode :
        # elle vient de l'experience de la veille. 99, pas 0 -- a zero le
        # controle d'exposition refuse TOUTE entree.
        c.risk.max_per_correlation_group = 99
        return c

    # A — ce qui tourne sur la demo 1
    a = neuve()
    a.strategy.famille = "donchian"
    _sortie_suiveur(a, base)
    sortie.append(("A", "cassure + stop suiveur (demo 1)", a))

    # B — entree momentum, sortie de la maison
    b = neuve()
    b.strategy.famille = "momentum"
    b.strategy.momentum_formation = args.formation
    _sortie_suiveur(b, base)
    b.risk.pyramide_max = 0
    b.risk.reserve_pyramide_pct = 0.0
    sortie.append(("B", "momentum + stop suiveur", b))

    # C — notre entree, sortie a date fixe
    c = neuve()
    c.strategy.famille = "donchian"
    _sortie_date_fixe(c, args.detention)
    sortie.append(("C", f"cassure + sortie a {args.detention:.0f} j", c))

    # D — ce qui tourne sur la demo 2
    d = neuve()
    d.strategy.famille = "momentum"
    d.strategy.momentum_formation = args.formation
    _sortie_date_fixe(d, args.detention)
    d.risk.pyramide_max = 0
    d.risk.reserve_pyramide_pct = 0.0
    sortie.append(("D", "momentum + sortie a date fixe (demo 2)", d))

    # E — les deux ENTREES exigees ensemble
    e = neuve()
    e.strategy.famille = "donchian"
    e.strategy.donchian_tendance_longue = True
    e.strategy.donchian_momentum_min_pct = args.plancher
    e.strategy.donchian_momentum_fenetre = args.formation
    _sortie_suiveur(e, base)
    sortie.append(("E", "cassure ET tendance longue", e))

    # F — E plus la sortie a date fixe. Les deux ameliorations cumulees.
    f = neuve()
    f.strategy.famille = "donchian"
    f.strategy.donchian_tendance_longue = True
    f.strategy.donchian_momentum_min_pct = args.plancher
    f.strategy.donchian_momentum_fenetre = args.formation
    _sortie_date_fixe(f, args.detention)
    sortie.append(("F", "cassure ET tendance + sortie fixe", f))

    # G — notre methode, plus la coupe sur retournement EN PERTE.
    #
    # Elle se mesure SEULE, a partir de A : c'est le seul moyen de savoir
    # ce qu'elle vaut. Cumulee d'emblee avec E et la sortie fixe, on ne
    # saurait pas laquelle des trois a fait la difference -- la lecon du
    # 6 septembre, ecrite dans le CLAUDE.md.
    g = neuve()
    g.strategy.famille = "donchian"
    _sortie_suiveur(g, base)
    g.trade.reversal_exit_en_perte = True
    g.trade.reversal_exit_perte_r = args.perte_r
    g.trade.reversal_exit_perte_score = args.perte_score
    sortie.append(("G", f"cassure + coupe en perte ({args.perte_r:+.2f}R)", g))

    # H — tout ensemble, une fois que chaque piece est jugee separement.
    h = neuve()
    h.strategy.famille = "donchian"
    h.strategy.donchian_tendance_longue = True
    h.strategy.donchian_momentum_min_pct = args.plancher
    h.strategy.donchian_momentum_fenetre = args.formation
    _sortie_date_fixe(h, args.detention)
    h.trade.reversal_exit_en_perte = True
    h.trade.reversal_exit_perte_r = args.perte_r
    h.trade.reversal_exit_perte_score = args.perte_score
    sortie.append(("H", "tendance + sortie fixe + coupe en perte", h))

    return sortie


def ligne(code: str, nom: str, res) -> str:
    s = res.stats()
    t = s.get("trades", 0)
    if not t:
        return f"  {code}  {nom:<38} {'aucun trade':>12}"
    perdantes = t - round(s["taux_reussite_pct"] / 100 * t)
    profits = [x.profit for x in res.trades if not x.partial]
    moyenne = sum(profits) / len(profits)
    var = sum((p - moyenne) ** 2 for p in profits) / max(1, len(profits) - 1)
    incert = 2 * math.sqrt(var / len(profits))
    verdict = ("BENEFICE" if moyenne - incert > 0
               else "PERTE" if moyenne + incert < 0
               else "indiscernable")
    etage_max = max((s.get("par_etage") or {1: None}))
    return (f"  {code}  {nom:<38} {t:>5} {perdantes:>4} ({perdantes/t*100:>3.0f}%) "
            f"{s['resultat']:>+8.0f} {s['rendement_pct']:>+7.1f}% "
            f"{s['drawdown_max_pct']:>6.1f}% {moyenne:>+6.2f}+-{incert:<5.2f} "
            f"{etage_max:>2}  {verdict}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--paires", type=int, default=25)
    # PARLER EN MOIS TRADES, PAS EN BOUGIES CHARGEES.
    #
    # `--bougies 180` ne donne PAS six mois de trading : le rejeu brule
    # les 150 premieres en prechauffage (les indicateurs doivent se
    # remplir) et en refuse moins de 200. Demander 180 rend « aucun
    # trade » -- ce qui ressemble a une strategie sans avantage alors que
    # c'est une fenetre trop courte. Premier essai du 21 septembre : les
    # 25 paires ont toutes ete ecartees sur « historique insuffisant ».
    ap.add_argument("--mois", type=float, default=6.0,
                    help="mois REELLEMENT trades (prechauffage en plus)")
    ap.add_argument("--bougies", type=int, default=0,
                    help="surcharge --mois, en bougies chargees (brut)")
    ap.add_argument("--capital", type=float, default=3300.0)
    ap.add_argument("--decalage", type=int, default=0)
    ap.add_argument("--formation", type=int, default=28)
    ap.add_argument("--detention", type=float, default=5.0)
    ap.add_argument("--plancher", type=float, default=0.0,
                    help="hausse minimale sur la fenetre longue, en %%")
    ap.add_argument("--perte-r", type=float, default=-0.30, dest="perte_r",
                    help="sous ce R, une position en perte peut etre coupee")
    ap.add_argument("--perte-score", type=float, default=-0.60,
                    dest="perte_score",
                    help="dynamique exigee pour couper en perte")
    ap.add_argument("--base", default="robot.demo.json")
    ap.add_argument("--seulement", default="",
                    help="ne mesurer que ces codes, ex. « C » ou « BC »")
    args = ap.parse_args()

    PRECHAUFFE = 150   # `warmup` dans backtest.py
    if not args.bougies:
        args.bougies = PRECHAUFFE + int(round(args.mois * 30))
    tradees = max(0, args.bougies - PRECHAUFFE)

    symboles = univers(args.paires)
    base = BotConfig.load(args.base)
    toutes = variantes(base, args)

    for code, nom, cfg in toutes:
        soucis = cfg.validate()
        if soucis:
            print(f"variante {code} refusee : {soucis}", file=sys.stderr)
            return 2

    if not args.seulement:
        print(f"{len(symboles)} paires, {tradees} bougies tradees "
              f"(~{tradees / 30.0:.1f} mois) + {PRECHAUFFE} de prechauffage, "
              f"UN compte de {args.capital:.0f} EUR\n")
        print(f"      {'variante':<38} {'trad':>5} {'perdantes':>10} "
              f"{'resultat':>8} {'rendem':>8} {'recul':>7} {'par trade':>13} "
              f"{'et':>2}  verdict")
        print("  " + "-" * 118)

    for code, nom, cfg in toutes:
        if args.seulement and code not in args.seulement.upper():
            continue
        res = BacktestPortefeuille(cfg).run(
            symboles, bars=args.bougies, start_balance=args.capital,
            decalage=args.decalage)
        print(ligne(code, nom, res))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
