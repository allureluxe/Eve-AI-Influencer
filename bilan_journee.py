#!/usr/bin/env python3
"""Le bilan de la journee : ce qui s'est ferme, ce qui reste ouvert, et si ca tient.

    python3 bilan_journee.py
    python3 bilan_journee.py --jours 7        # la semaine
    python3 bilan_journee.py --sans-positions # sans interroger la plateforme

Ecrit parce que « est-ce qu'on est sur la bonne voie ? » ne se lit dans
aucun journal. Un profit positif sur cinq trades ne prouve rien, et un
profit negatif sur cinq trades ne condamne rien non plus : c'est
l'esperance en R, comparee au SEUIL DE RENTABILITE impose par les frais,
qui tranche — et seulement quand l'echantillon est assez grand.

Ce script ne dit donc jamais « ca marche » sur trop peu de trades. Il dit
combien il en manque.
"""
from __future__ import annotations

import argparse
import datetime as dt
import math
import os
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent
sys.path.insert(0, str(RACINE))

from gold_bot.croissance import (ECHANTILLON_MINIMAL, Diagnostic,  # noqa: E402
                                 palier_courant, palier_suivant)
from gold_bot.env import charger_env  # noqa: E402
from gold_bot.runtime_context import instance_key  # noqa: E402
from gold_bot.settings import BotConfig  # noqa: E402
from gold_bot.state import TradeJournal  # noqa: E402

charger_env()

GRAS, FIN = "\033[1m", "\033[0m"
VERT, ROUGE, JAUNE, GRIS = "\033[32m", "\033[31m", "\033[33m", "\033[90m"


def seuil_de_rentabilite(cfg: BotConfig) -> tuple[float, float]:
    """Taux de reussite minimal pour une esperance nulle, et le cout en R.

    Le stop vaut `atr_stop_mult` ATR, soit 1 R par construction. Des frais
    de `cout` en fraction du prix pesent donc `cout / (atr_stop_mult x ATR)`
    en R — c'est le rapport que `max_cost_ratio_pct` plafonne, et le
    plancher de volatilite garantit qu'on ne le depasse pas.

    Avec un objectif a T fois le risque :

        esperance nulle  <=>  p x T = (1 - p) x 1 + cout_R
                         <=>  p = (1 + cout_R) / (1 + T)
    """
    cout_r = cfg.risk.max_cost_ratio_pct / 100.0
    cible = cfg.trade.tp_r_multiple
    return (1.0 + cout_r) / (1.0 + cible) * 100.0, cout_r


def broker_pour_rapport(cfg: BotConfig):
    """Connexion lecture seule au broker configure."""
    if cfg.engine.broker not in ("bitvavo", "bitvavo_margin"):
        return None
    if cfg.engine.broker == "bitvavo_margin":
        from gold_bot.brokers.bitvavo_margin import BitvavoMarginBroker
        broker = BitvavoMarginBroker()
    else:
        from gold_bot.brokers.bitvavo import BitvavoBroker
        broker = BitvavoBroker()
    if not broker.connect():
        return None
    broker.sync()
    return broker


def positions_ouvertes(cfg: BotConfig):
    """Ce que le compte detient encore. Aucune commande passee."""
    broker = broker_pour_rapport(cfg)
    if broker is None:
        return [], type("Compte", (), {"equity": 0.0, "currency": cfg.engine.currency, "margin_free": 0.0})()
    return broker.positions(), broker.account()


def transactions_reelles(cfg: BotConfig, depuis: float):
    broker = broker_pour_rapport(cfg)
    if broker is None or not hasattr(broker, "recent_transactions"):
        return []
    return broker.recent_transactions(depuis)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.getenv("GB_CONFIG", "robot.bitvavo.json"))
    ap.add_argument("--jours", type=float, default=1.0,
                    help="fenetre analysee, en jours (1 = aujourd'hui)")
    ap.add_argument("--sans-positions", action="store_true", dest="sans_positions",
                    help="ne pas interroger la plateforme")
    args = ap.parse_args()

    cfg = BotConfig.load(args.config)
    cle = instance_key(cfg)
    journal = TradeJournal(instance=cle)

    if args.jours <= 1.0:
        minuit = dt.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        depuis, titre = minuit.timestamp(), "AUJOURD'HUI"
    else:
        depuis = time.time() - args.jours * 86400
        titre = f"{args.jours:.0f} DERNIERS JOURS"

    depuis_24h = time.time() - 86400
    tx_24h = transactions_reelles(cfg, depuis_24h)
    tx_periode = [t for t in tx_24h if t.timestamp >= depuis] if args.jours <= 1.0 else transactions_reelles(cfg, depuis)

    print(f"\n{GRAS}{'=' * 74}{FIN}")
    print(f"{GRAS}  BILAN — {titre}{FIN}")
    print(f"{GRAS}{'=' * 74}{FIN}\n")
    print(f"  instance journalisee : {cle}")
    print(f"  journal : {journal.path}")
    print(f"  depuis minuit : {len([t for t in tx_24h if t.timestamp >= minuit]) if args.jours <= 1.0 else 'n/a'} transaction(s) broker")
    print(f"  sur 24h       : {len(tx_24h)} transaction(s) broker\n")

    if tx_periode:
        print(f"{GRAS}  TRANSACTIONS BITVAVO{FIN}")
        print(f"  {'heure':>5}  {'sens':<6} {'symbole':<10} {'montant':>12} {'prix':>12} {'frais':>9}")
        for tx in sorted(tx_periode, key=lambda x: x.timestamp):
            heure = dt.datetime.fromtimestamp(tx.timestamp).strftime("%H:%M")
            sens = "achat" if tx.side.value == "BUY" else "vente"
            print(f"  {heure:>5}  {sens:<6} {tx.symbol:<10} {tx.quote_amount:>11.2f} "
                  f"{tx.price:>12.6f} {tx.fee:>8.4f}")
        print()

    # ---------------------------------------------------------------
    # 1. Ce qui s'est ferme
    # ---------------------------------------------------------------
    fermes = [t for t in journal.trades if t.closed_at >= depuis]
    complets = [t for t in fermes if not t.partial]
    partielles = [t for t in fermes if t.partial]

    if not fermes:
        print(f"{GRIS}  Aucun trade ferme sur la periode.{FIN}\n")
    else:
        print(f"{GRAS}  TRADES JOURNALISES{FIN}")
        print(f"  {'heure':>5}  {'symbole':<10} {'R':>7} {'profit':>9}  "
              f"{'plus haut':>9}  {'ordre sortie':<14} motif")
        for t in sorted(fermes, key=lambda x: x.closed_at):
            heure = dt.datetime.fromtimestamp(t.closed_at).strftime("%H:%M")
            couleur = VERT if t.profit > 0 else ROUGE
            marque = " (partielle)" if t.partial else ""
            # Le plus haut atteint dit si le trade est mort d'une mauvaise
            # ENTREE (il n'est jamais alle nulle part) ou d'une mauvaise
            # PROTECTION (il est monte puis retombe). Les deux se corrigent
            # a l'oppose, et rien d'autre ne les distingue.
            print(f"  {heure:>5}  {t.symbol:<10} {couleur}{t.r_multiple:>+7.2f}"
                  f" {t.profit:>+8.2f}{FIN}  {t.max_favorable_r:>+9.2f}"
                  f"  {str(t.exit_order_id or '-')[:14]:<14} {t.reason[:28]}{marque}")
        print()

    # ---------------------------------------------------------------
    # 2. Ce qui reste ouvert
    # ---------------------------------------------------------------
    if not args.sans_positions:
        try:
            ouvertes, compte = positions_ouvertes(cfg)
            print(f"{GRAS}  POSITIONS OUVERTES{FIN}")
            if not ouvertes:
                print(f"  {GRIS}aucune{FIN}")
            for p in ouvertes:
                age = (time.time() - p.opened_at) / 60.0
                verrou = p.locked_r()
                etat = (f"{VERT}protege a {verrou:+.2f}R{FIN}" if verrou >= 0
                        else f"{JAUNE}risque {verrou:+.2f}R{FIN}")
                print(f"  {p.symbol:<10} entree {p.entry_price:<12.6f} "
                      f"stop {p.stop_loss:<12.6f} objectif {p.take_profit:<12.6f}")
                print(f"  {'':<10} {etat}, ouverte depuis {age:.0f} min, "
                      f"{p.tp_extensions} extension(s)")
            print(f"\n  capital : {GRAS}{compte.equity:.2f} {compte.currency}{FIN} "
                  f"(disponible {compte.margin_free:.2f})\n")
        except Exception as exc:  # noqa: BLE001
            print(f"  {JAUNE}plateforme injoignable : {str(exc)[:90]}{FIN}\n")

    # ---------------------------------------------------------------
    # 3. Est-ce qu'on est sur la bonne voie ?
    # ---------------------------------------------------------------
    print(f"{GRAS}  EST-CE QU'ON EST SUR LA BONNE VOIE ?{FIN}")
    seuil, cout_r = seuil_de_rentabilite(cfg)
    print(f"  Les frais valent {cout_r * 100:.0f} % du risque a ce reglage, et "
          f"l'objectif vaut {cfg.trade.tp_r_multiple:.1f} R.")
    print(f"  Il faut donc gagner {GRAS}{seuil:.1f} %{FIN} des trades pour "
          f"seulement rentrer dans ses frais.\n")

    if not complets:
        print(f"  {GRIS}Aucun trade complet sur la periode : rien a juger.{FIN}")
        print(f"  {GRIS}Un trade qui n'a pas eu lieu n'est ni un succes ni un "
              f"echec.{FIN}\n")
        return 0

    stats = journal.stats(since=depuis)
    taux = stats["taux_reussite_pct"]
    esperance = stats["esperance_R"]
    esperance_nette = stats.get("esperance_R_nette")
    esperance_nette = esperance if esperance_nette is None else esperance_nette
    n = stats["trades"]

    couleur = VERT if taux >= seuil else ROUGE
    print(f"  mesure sur la periode : {couleur}{taux:.1f} % de reussite{FIN} "
          f"sur {n} trade(s)")
    # LES DEUX CHIFFRES, ET SEUL LE SECOND COMPTE.
    #
    # La colonne R du tableau ci-dessus se calcule sur les prix : elle
    # ignore la commission. L'ecart entre les deux vaut le rapport
    # frais/risque, soit pres d'un demi-R par trade au M30. Afficher le
    # brut seul donnerait un avantage imaginaire.
    print(f"  esperance BRUTE (prix seuls)  : {esperance:+.3f} R")
    print(f"  esperance {GRAS}NETTE de frais{FIN}       : "
          f"{couleur}{GRAS}{esperance_nette:+.3f} R{FIN}   <- le seul chiffre qui compte")
    print(f"  profit net : {stats['profit_net']:+.2f} {cfg.engine.currency}"
          + (f", {len(partielles)} prise(s) partielle(s)" if partielles else ""))
    if tx_periode and not fermes:
        print(f"  {JAUNE}ATTENTION : Bitvavo montre {len(tx_periode)} transaction(s) "
              f"mais le journal local n'a rien sur la meme periode.{FIN}")

    # L'INCERTITUDE, ET C'EST ELLE QUI DOIT PARLER EN PREMIER.
    #
    # Avec un ecart-type de ~1 R par trade, l'erreur type vaut 1/sqrt(n).
    # Sur 11 trades elle vaut 0,30 R : une esperance de +0,20 R et une de
    # -0,20 R sont alors indiscernables. Annoncer « ca marche » ou « ca ne
    # marche pas » a ce stade, c'est lire du bruit.
    incertitude = 1.0 / math.sqrt(n)
    print(f"\n  incertitude a {n} trades : {GRAS}±{incertitude:.2f} R{FIN} "
          f"(soit {esperance_nette - 2 * incertitude:+.2f} a "
          f"{esperance_nette + 2 * incertitude:+.2f} R en net)")

    palier = palier_courant(n, esperance_nette, 0.0)
    diag = Diagnostic(capital=0.0, cible=0.0, trades=n,
                      esperance_r=esperance_nette,
                      taux_reussite_pct=taux, trades_par_jour=0.0,
                      palier=palier, palier_suivant=palier_suivant(palier))
    if diag.esperance_fiable():
        verdict = (f"{VERT}L'AVANTAGE EST ETABLI{FIN}" if esperance_nette > 0
                   else f"{ROUGE}LA PERTE EST ETABLIE — il faut changer quelque chose{FIN}")
        print(f"\n  {GRAS}{verdict}{FIN}")
    else:
        manque = max(0, ECHANTILLON_MINIMAL - n)
        print(f"\n  {JAUNE}ECHANTILLON TROP PETIT POUR CONCLURE.{FIN}")
        print(f"  Il manque environ {GRAS}{manque} trades{FIN} pour que le "
              f"chiffre veuille dire quelque chose.")
        print(f"  {GRIS}Ni le profit ni la perte du jour ne prouvent quoi que "
              f"ce soit a ce stade.{FIN}")

    # Le plus haut atteint separe deux maladies opposees.
    if complets:
        perdants = [t for t in complets if t.profit <= 0]
        if perdants:
            haut_moyen = sum(t.max_favorable_r for t in perdants) / len(perdants)
            print(f"\n  {GRAS}Les {len(perdants)} perdant(s) sont montes en "
                  f"moyenne a {haut_moyen:+.2f} R avant de retomber.{FIN}")
            if haut_moyen >= 0.8:
                print(f"  {JAUNE}-> ils allaient quelque part : c'est la "
                      f"PROTECTION qui les a laisses filer.{FIN}")
            else:
                print(f"  {GRIS}-> ils n'allaient nulle part : c'est l'ENTREE "
                      f"qui ne vaut rien, aucun reglage de stop n'y changera "
                      f"quoi que ce soit.{FIN}")
    par_symbole = journal.by_symbol(since=depuis)
    if par_symbole:
        print(f"\n{GRAS}  PAR ACTIF{FIN}")
        print(f"  {'symbole':<10}{'trades':>8}{'reussite':>11}{'profit':>12}{'R net':>9}{'duree':>9}  raison")
        for sym, row in sorted(par_symbole.items(), key=lambda kv: -kv[1]["profit_net"]):
            r_net = row["esperance_R_nette"] if row["esperance_R_nette"] is not None else 0.0
            print(f"  {sym:<10}{row['trades']:>8}{row['taux_reussite_pct']:>10.1f}%"
                  f"{row['profit_net']:>12.2f}{r_net:>9.2f}{row['duree_moyenne_min']:>8.0f}m  "
                  f"{row['raison_sortie_top'][:24]}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
