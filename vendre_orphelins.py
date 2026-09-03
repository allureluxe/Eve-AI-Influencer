#!/usr/bin/env python3
"""Vend au marche les avoirs que le robot ne suit PAS.

    python3 vendre_orphelins.py              # montre ce qui serait vendu
    python3 vendre_orphelins.py --executer   # passe les ordres

POURQUOI CE SCRIPT EXISTE

Au comptant, Bitvavo ne connait pas de « positions » : on detient des
actifs. Quand la strategie change — M30 quorum -> D1 Turtle le 3 septembre
— le moteur repart avec zero position, mais les cryptos achetees par
l'ancienne strategie, elles, sont toujours la.

Constate le 3 septembre : 72,64 EUR sur 159,64 (45 % du compte) detenus
sans stop, sans objectif et sans suivi. Si l'un d'eux decroche, personne
ne coupe. Et pendant le test du Turtle, leurs variations se melangent au
resultat de la strategie : dans une semaine on ne saurait plus ce qui
vient de quoi.

CE QU'IL NE FAIT PAS. Il ne touche a aucune position SUIVIE par le robot :
seuls les avoirs absents de son etat sont vendus. Il refuse aussi les
lignes sous le minimum de marche (5 EUR chez Bitvavo), qui seraient
rejetees de toute facon.
"""
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import replace

RACINE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RACINE)

from gold_bot.env import charger_env  # noqa: E402

charger_env()

from gold_bot.brokers.bitvavo import (BitvavoBroker, BitvavoConfig,  # noqa: E402
                                     formater)
from gold_bot.settings import BotConfig  # noqa: E402
from gold_bot.state import StateStore  # noqa: E402

GRAS, FIN, JAUNE, VERT, ROUGE = "\033[1m", "\033[0m", "\033[33m", "\033[32m", "\033[31m"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vendre", default="",
                    help="LISTE EXPLICITE des actifs a vendre, ex. BTC,LTC,ATOM")
    ap.add_argument("--executer", action="store_true",
                    help="passe reellement les ordres (sinon simple apercu)")
    args = ap.parse_args()

    cfg = BotConfig.load("robot.bitvavo.json")
    bv = BitvavoConfig.from_env()
    # L'apercu ne doit RIEN pouvoir envoyer.
    broker = BitvavoBroker(replace(bv, dry_run=not args.executer))
    if not broker.connect():
        print(f"{ROUGE}connexion Bitvavo refusee{FIN}")
        return 1
    broker.sync()

    quote = broker.config.quote_asset
    prix = broker._prix_du_marche()
    marches = {m["market"]: m for m in broker._appel("GET", "/markets")
               if isinstance(m, dict)}

    # Ce que le robot suit vraiment : en memoire ET dans l'etat sauvegarde,
    # car un redemarrage recent peut ne pas avoir encore repris ses positions.
    # RIEN N'EST VENDU PAR DEDUCTION, ET C'EST DELIBERE.
    #
    # La premiere version devinait les « orphelins » en croisant les avoirs
    # avec l'etat du robot. Elle a marque CELO et KAVA a vendre — les deux
    # premieres positions Turtle, ouvertes le matin meme. `position_meta`
    # garde 22 entrees dont des vieilles a volume nul : deduire qui est
    # suivi a partir de la n'est pas fiable, et l'erreur se paie en argent
    # reel.
    #
    # Desormais il faut NOMMER ce qu'on vend. L'oubli fait donc ne rien
    # vendre, au lieu de vendre ce qu'il ne fallait pas.
    a_vendre = {x.strip().upper() for x in args.vendre.split(",") if x.strip()}
    if not a_vendre:
        print(f"\n  {JAUNE}Aucun actif nomme.{FIN} Utilisez "
              f"{GRAS}--vendre BTC,LTC,ATOM{FIN}\n"
              f"  (rien n'est vendu par deduction : voir le commentaire du code)\n")

    print(f"\n{GRAS}Avoirs detenus{FIN}   (demande a la vente : "
          f"{', '.join(sorted(a_vendre)) or 'rien'})\n")
    print(f"  {'actif':6}{'quantite':>18}{'valeur':>10}{'min':>7}  etat")
    print("  " + "-" * 58)

    plan = []
    decimales_par_marche: dict[str, int] = {}
    for actif, quantite in sorted(broker._soldes.items()):
        if actif == quote:
            print(f"  {actif:6}{quantite:>18.2f}{quantite:>10.2f}{'':>7}  liquidites")
            continue
        marche = f"{actif}-{quote}"
        p = prix.get(marche, 0.0)
        valeur = quantite * p
        info = marches.get(marche, {})
        mini = float(info.get("minOrderInQuoteAsset", 5) or 5)
        decimales = int(info.get("baseDecimals", 8) or 8)
        pas = 10 ** -decimales
        qte = int(quantite / pas) * pas             # tronque au pas du marche

        if actif not in a_vendre:
            etat = f"{VERT}non demande - on ne touche pas{FIN}"
        elif qte * p < mini:
            etat = f"{JAUNE}sous le minimum ({mini:.0f} EUR) - invendable{FIN}"
        else:
            etat = f"{ROUGE}ORPHELIN -> a vendre{FIN}"
            plan.append((marche, round(qte, decimales), valeur))
            decimales_par_marche[marche] = decimales
        print(f"  {actif:6}{quantite:>18.8f}{valeur:>10.2f}{mini:>7.0f}  {etat}")

    if not plan:
        print(f"\n  {VERT}Rien a vendre.{FIN}\n")
        return 0

    total = sum(v for _, _, v in plan)
    print(f"\n{GRAS}  {len(plan)} ordre(s) au marche, ~{total:.2f} {quote} a recuperer{FIN}")

    if not args.executer:
        print(f"\n  {JAUNE}APERCU SEULEMENT — aucun ordre envoye.{FIN}")
        print(f"  Pour executer : {GRAS}python3 vendre_orphelins.py --executer{FIN}\n")
        return 0

    # Les avoirs sont bloques par leur propre stop (`inOrder`) : Bitvavo
    # refuse de vendre ce qui est deja engage dans un ordre. Il faut donc
    # annuler le stop AVANT de vendre. C'est aussi la preuve que ces
    # positions n'etaient pas « sans protection » : elles avaient chacune
    # un stop dormant chez la plateforme.
    try:
        ouverts = broker._appel("GET", "/ordersOpen")
    except Exception:  # noqa: BLE001
        ouverts = []
    a_annuler = {o["market"]: o["orderId"] for o in ouverts
                 if isinstance(o, dict) and o.get("market") in {m for m, _, _ in plan}}
    for marche, oid in a_annuler.items():
        try:
            # `operatorId` est exige sur DELETE aussi, pas seulement sur POST.
            broker._appel("DELETE", "/order",
                          params={"market": marche, "orderId": oid,
                                  "operatorId": broker.config.operator_id})
            print(f"  {JAUNE}stop annule{FIN} {marche}")
        except Exception as exc:  # noqa: BLE001
            print(f"  {ROUGE}stop NON annule{FIN} {marche} : {str(exc)[:80]}")
    if a_annuler:
        import time as _t
        _t.sleep(2)          # laisser la plateforme liberer les avoirs
        broker.sync()

    print()
    for marche, qte, valeur in plan:
        try:
            # `corps=` et non `body=` : la signature est en francais, et le
            # durcissement (`bitvavo_hardening`) enveloppe l'appel avec les
            # memes noms. `operatorId` est exige par Bitvavo sur tout ordre.
            r = broker._appel("POST", "/order", corps={
                "market": marche, "side": "sell", "orderType": "market",
                "operatorId": broker.config.operator_id,
                "amount": formater(qte, decimales_par_marche[marche])})
            ok = isinstance(r, dict) and r.get("orderId")
            print(f"  {VERT if ok else ROUGE}{'OK ' if ok else 'ECHEC'}{FIN} "
                  f"{marche:12} {qte:.8f}  (~{valeur:.2f} {quote})"
                  f"{'' if ok else '  ' + str(r)[:100]}")
        except Exception as exc:  # noqa: BLE001
            print(f"  {ROUGE}ECHEC{FIN} {marche:12} {str(exc)[:100]}")

    broker.sync()
    print(f"\n{GRAS}  Liquidites apres vente : "
          f"{broker.account().margin_free:.2f} {quote}{FIN}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
