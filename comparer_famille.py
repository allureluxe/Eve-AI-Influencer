#!/usr/bin/env python3
"""Backtest walk-forward : famille « tendance » contre « reversion ».

Demande de l'operateur le 31 aout. On mesure le mode reversion (achat
quand le prix decroche sous sa SMA de N x ATR, sortie sur bande) contre
le mode en service, AVANT tout armement.

Regles fixees :
  - paires liquides en EUR, 6 mois de M30 (Bitvavo, pagine : les
    fournisseurs du depot plafonnent a ~30 jours) ;
  - frais Bitvavo TAKER des deux cotes (0,25 %), jamais maker ;
  - risque 0,6 % — le plafond reel, pas 2 % : le pourcentage etire la
    courbe, il ne change pas l'expectancy PAR TRADE ;
  - metrique : expectancy NETTE de frais en R (gold_bot.state.TradeJournal.r_net)
    et nombre de trades. Sous 100 trades, le resultat ne veut rien dire ;
  - WALK-FORWARD : 3 premiers mois = ajustement (in-sample), 3 derniers =
    jamais regardes (out-of-sample). Expectancy donnee separement. Si
    l'OOS s'effondre, la reversion est du sur-mesure sur le passe.

    python3 comparer_famille.py
    python3 comparer_famille.py --mois 6 --paires BTC,ETH,SOL
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gold_bot.core import Candle  # noqa: E402
from gold_bot.settings import BotConfig  # noqa: E402
from gold_bot.backtest import Backtester  # noqa: E402
from gold_bot.state import TradeJournal  # noqa: E402

PAIRES_EUR = {
    "BTC": ("BTCUSD", "BTC-EUR"), "ETH": ("ETHUSD", "ETH-EUR"),
    "SOL": ("SOLUSD", "SOL-EUR"), "XRP": ("XRPUSD", "XRP-EUR"),
    "ADA": ("ADAUSD", "ADA-EUR"), "LINK": ("LINKUSD", "LINK-EUR"),
    "DOT": ("DOTUSD", "DOT-EUR"),
}
INTERVALLE = {"M30": ("30m", 1800), "H1": ("1h", 3600), "H4": ("4h", 14400)}
# Prechauffage : bougies AVANT le debut de la fenetre pour amorcer les
# indicateurs des unites superieures (et la SMA 50 en M30).
PRECHAUFFE = {"M30": 60 * 86400, "H1": 30 * 86400, "H4": 120 * 86400}


def fetch_bitvavo(marche: str, tf: str, debut_ms: int, fin_ms: int) -> list[Candle]:
    """Pagine les bougies Bitvavo entre debut et fin (ms UTC).

    Bitvavo rend <= 1440 bougies par requete. On recule fenetre par
    fenetre du plus recent au plus ancien, puis on trie."""
    iv, secs = INTERVALLE[tf]
    pas_ms = secs * 1000
    fenetre = 1440 * pas_ms
    par_ts: dict[int, Candle] = {}
    fin = fin_ms
    while fin > debut_ms:
        deb = max(debut_ms, fin - fenetre)
        url = (f"https://api.bitvavo.com/v2/{marche}/candles?interval={iv}"
               f"&start={deb}&end={fin}&limit=1440")
        lignes = []
        for essai in range(5):
            try:
                lignes = json.load(urllib.request.urlopen(url, timeout=30))
                break
            except Exception as exc:  # noqa: BLE001
                if essai == 4:
                    print(f"    ! {marche} {tf} : {str(exc)[:80]}")
                time.sleep(2 + essai)
        if not lignes:
            break
        for r in lignes:
            t = int(r[0])
            par_ts[t] = Candle(t / 1000.0, float(r[1]), float(r[2]),
                               float(r[3]), float(r[4]), float(r[5]))
        plus_ancien = min(int(r[0]) for r in lignes)
        if plus_ancien >= fin:      # pas de progres -> on arrete
            break
        fin = plus_ancien - pas_ms
        time.sleep(0.35)
    return [par_ts[k] for k in sorted(par_ts)]


def config_mode(chemin: str, famille: str, extra: dict | None = None) -> BotConfig:
    c = BotConfig.load(chemin)
    c.strategy.famille = famille
    c.strategy.entry_tf = "M30"
    c.strategy.context_tf = "H1"
    c.strategy.bias_tf = "H4"
    c.risk.base_risk_pct = 0.6
    c.risk.min_risk_pct = min(c.risk.min_risk_pct, 0.6)
    c.risk.max_risk_pct = max(c.risk.max_risk_pct, 0.6)
    c.risk.commission_pct = 0.0025          # Bitvavo taker, deux cotes
    c.risk.max_daily_trades = 0             # 0 = illimite
    c.risk.max_consecutive_losses = 10**9   # jamais de pause dans le rejeu de mesure
    c.risk.daily_loss_limit_pct = 90.0
    c.risk.weekly_loss_limit_pct = 95.0
    c.risk.max_drawdown_pct = 99.0
    c.engine.broker = "bitvavo"             # comptant : achat seul
    c.engine.offline = False
    # Reglages propres a une variante. `pyramide_stop_commun` vit dans le
    # gestionnaire de trade (c'est une regle de SORTIE), les autres
    # `pyramide_*` dans le risque (regles d'ENTREE) : le prefixe seul ne
    # suffit pas a router, on cherche ou l'attribut existe.
    for cle, valeur in (extra or {}).items():
        cible = c.trade if hasattr(c.trade, cle) else c.risk
        setattr(cible, cle, valeur)
    return c


# Ce qu'on mesure : (nom affiche, famille de strategie, reglages en plus).
#
# « tenir » : le M30 entre pareil mais n'encaisse plus a 2R — objectif 6R,
# stop suiveur desserre a 2,2 ATR, pas de prise partielle. C'est la seule
# modif qui ait battu le temoin sur les deux groupes de cryptos.
#
# Les deux modes pyramide sont dessus, PAS tout seuls : mesure le 1er
# sept., la pyramide seule ne s'ouvre presque jamais parce que la position
# de base meurt a 2R avant qu'un 2e signal ait le temps d'apparaitre. Il
# lui faut d'abord de la place pour construire.
TENIR = {"tp_r_multiple": 6.0, "trail_atr_mult": 2.2,
         "partial_enabled": False, "max_extensions": 12}
PYRAMIDE = {"pyramide_max": 4, "pyramide_fraction_risque": 1.0}

# Delai de carence : interdit de RACHETER un symbole qu'on vient de
# quitter. Mesure des 1er-2 sept. : dix entrees sur UNIUSD en 48 h pour
# 0,64 EUR, esperance brute +0,135 R contre nette -0,105 R — la rotation
# mange des entrees qui gagnent. Il ne bride jamais la pyramide (celle-ci
# ajoute un etage a une position ENCORE OUVERTE), et la derniere ligne
# le verifie sur les chiffres.
CARENCE = {"cooldown_apres_sortie_minutes": 240.0}

MODES: list[tuple[str, str, dict]] = [
    ("tendance", "tendance", {}),
    ("reversion", "reversion", {}),
    ("tenir", "tendance", TENIR),
    ("tenir+pyr", "tendance", {**TENIR, **PYRAMIDE}),
    ("tendance+carence", "tendance", CARENCE),
    ("tenir+carence", "tendance", {**TENIR, **CARENCE}),
    ("tenir+pyr+carence", "tendance", {**TENIR, **PYRAMIDE, **CARENCE}),
]


def bloc_stats(trades: list) -> dict:
    reels = [t for t in trades if not t.partial]
    if not reels:
        return {"trades": 0, "reussite": 0.0, "R_net": None, "R_brut": None, "eur": 0.0}
    nets = [r for r in (TradeJournal.r_net(t) for t in reels) if r is not None]
    gagnants = [t for t in reels if t.profit > 0]
    return {
        "trades": len(reels),
        "reussite": round(100 * len(gagnants) / len(reels), 1),
        "R_net": round(sum(nets) / len(nets), 3) if nets else None,
        "R_brut": round(sum(t.r_multiple for t in reels) / len(reels), 3),
        "eur": round(sum(t.profit for t in reels), 2),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="robot.bitvavo.json")
    ap.add_argument("--mois", type=int, default=6)
    ap.add_argument("--paires", default=",".join(PAIRES_EUR))
    ap.add_argument("--capital", type=float, default=1000.0)
    args = ap.parse_args()

    paires = [p.strip().upper() for p in args.paires.split(",") if p.strip()]
    fin_ms = int(dt.datetime.now(dt.timezone.utc).timestamp() * 1000)
    debut_ms = fin_ms - args.mois * 30 * 86400 * 1000
    milieu = dt.datetime.fromtimestamp((debut_ms + fin_ms) / 2000, dt.timezone.utc).timestamp()
    d0 = dt.datetime.fromtimestamp(debut_ms / 1000, dt.timezone.utc).date()
    d1 = dt.datetime.fromtimestamp(fin_ms / 1000, dt.timezone.utc).date()

    print("=" * 78)
    print(f"  BACKTEST FAMILLE — {args.mois} mois M30, {d0} -> {d1}")
    print(f"  Paires : {', '.join(paires)}")
    print(f"  Frais  : Bitvavo taker 0,25 % x2  |  risque 0,6 %  |  achat seul")
    print(f"  Walk-forward : in-sample {d0} -> {dt.date.fromtimestamp(milieu)} "
          f"| out-of-sample {dt.date.fromtimestamp(milieu)} -> {d1}")
    print("=" * 78)

    # 1. Telecharger les series une seule fois (partagees par les 2 modes)
    series_par_paire: dict[str, dict[str, list[Candle]]] = {}
    for p in paires:
        if p not in PAIRES_EUR:
            print(f"  ! paire inconnue ignoree : {p}")
            continue
        interne, marche = PAIRES_EUR[p]
        s: dict[str, list[Candle]] = {}
        for tf in ("M30", "H1", "H4"):
            deb = debut_ms - PRECHAUFFE[tf] * 1000
            c = fetch_bitvavo(marche, tf, deb, fin_ms)
            s[tf] = c
            jours = (c[-1].ts - c[0].ts) / 86400 if c else 0
            print(f"  {marche:9} {tf:3} : {len(c):5} bougies ({jours:.0f} j)")
        series_par_paire[interne] = s

    # 2. Rejouer chaque mode
    resultats: dict[str, dict] = {}
    for nom, famille, extra in MODES:
        cfg = config_mode(args.config, famille, extra)
        bt = Backtester(cfg, autorise_vente=False)
        is_trades, oos_trades = [], []
        detail = []
        for interne, s in series_par_paire.items():
            try:
                r = bt.run(interne, series=s, start_balance=args.capital)
            except Exception as exc:  # noqa: BLE001
                print(f"  ! {nom}/{interne} : {str(exc)[:100]}")
                continue
            reels = [t for t in r.trades if not t.partial]
            detail.append((interne, len(reels)))
            for t in reels:
                (is_trades if t.closed_at < milieu else oos_trades).append(t)
        resultats[nom] = {
            "in_sample": bloc_stats(is_trades),
            "out_of_sample": bloc_stats(oos_trades),
            "total": bloc_stats(is_trades + oos_trades),
            "par_paire": detail,
        }

    # 3. Rapport
    print("\n" + "=" * 78)
    print("  RESULTATS — expectancy NETTE de frais, en R")
    print("=" * 78)
    entete = f"  {'mode':10} {'bloc':14} {'trades':>7} {'reussite':>9} {'R net':>8} {'R brut':>8} {'EUR':>9}"
    for nom, _, _ in MODES:
        print(f"\n  --- {nom.upper()} ---")
        print(entete)
        for cle, libelle in (("in_sample", "in-sample 3m"),
                             ("out_of_sample", "OOS 3m"),
                             ("total", "total 6m")):
            b = resultats[nom][cle]
            rn = f"{b['R_net']:+.3f}" if b["R_net"] is not None else "   n/a"
            rb = f"{b['R_brut']:+.3f}" if b["R_brut"] is not None else "   n/a"
            print(f"  {'':10} {libelle:14} {b['trades']:>7} {b['reussite']:>8.1f}% "
                  f"{rn:>8} {rb:>8} {b['eur']:>+9.2f}")
        pp = ", ".join(f"{s}:{n}" for s, n in resultats[nom]["par_paire"])
        print(f"  {'':10} par paire : {pp}")

    print("\n" + "-" * 78)
    print("  LECTURE")
    for nom, _, _ in MODES:
        tot = resultats[nom]["total"]["trades"]
        oos = resultats[nom]["out_of_sample"]
        is_ = resultats[nom]["in_sample"]
        if tot < 100:
            print(f"  {nom:10}: {tot} trades — SOUS 100, le resultat ne veut rien dire.")
            continue
        if oos["R_net"] is None or is_["R_net"] is None:
            print(f"  {nom:10}: bloc sans R net calculable.")
            continue
        total_r = resultats[nom]["total"]["R_net"]
        if total_r is not None and total_r <= 0:
            verdict = "PAS D'AVANTAGE : negatif net de frais sur 6 mois"
        elif oos["R_net"] <= 0:
            verdict = "OOS negatif -> sur-mesure sur le passe"
        elif oos["R_net"] < 0.10:
            verdict = "OOS a peine positif -> les frais mangent l'avantage"
        elif is_["R_net"] - oos["R_net"] >= 0.15:
            verdict = "OOS degrade nettement -> fragile"
        else:
            verdict = "OOS tient"
        print(f"  {nom:10}: in-sample {is_['R_net']:+.3f} R | OOS {oos['R_net']:+.3f} R "
              f"| total {total_r:+.3f} R ({tot} trades) -> {verdict}")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
