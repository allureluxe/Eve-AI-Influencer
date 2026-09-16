#!/usr/bin/env python3
"""Diagnostic : une position affichee comme ouverte est-elle reellement
protegee sur Bitvavo -- ou deja vendue sans que le robot le sache ?

    python3 verifier_positions_orphelines.py ZETAUSD ZILUSD

Trouve le 16 sept. : ZETAUSD restait affiche "ouvert depuis 63h" par
`etat.py` alors qu'un stop-limit REEL l'avait deja vendu chez Bitvavo
plus d'une journee avant (le robot avait perdu sa trace au fil de
plusieurs redemarrages). Ce script lit directement les avoirs et les
ordres reels du compte -- lecture seule, aucun ordre envoye -- pour
trancher : l'avoir existe-t-il encore, et un ordre est-il encore en
carnet ? Utile a chaque fois qu'une position "tenue depuis X h" parait
suspecte dans `etat.py`.
"""
from __future__ import annotations

import datetime as _dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def charger_env(chemin: str = ".env") -> None:
    if not os.path.exists(chemin):
        return
    with open(chemin, "r", encoding="utf-8") as fh:
        for ligne in fh:
            ligne = ligne.strip()
            if not ligne or ligne.startswith("#") or "=" not in ligne:
                continue
            cle, _, valeur = ligne.partition("=")
            os.environ.setdefault(cle.strip(), valeur.strip())


def main() -> int:
    symboles = sys.argv[1:]
    if not symboles:
        print("usage : python3 verifier_positions_orphelines.py SYMBOLE [SYMBOLE ...]")
        print("   ex : python3 verifier_positions_orphelines.py ZETAUSD ZILUSD")
        return 1

    charger_env()
    from gold_bot.brokers.bitvavo import BitvavoBroker, BitvavoConfig
    from gold_bot.universe import ACTIFS_PAR_SYMBOLE

    config = BitvavoConfig.from_env()
    if not (config.api_key and config.api_secret):
        print("cles Bitvavo absentes -- rien a verifier")
        return 1
    broker = BitvavoBroker(config)

    for symbole in symboles:
        symbole = symbole.upper()
        actif = ACTIFS_PAR_SYMBOLE.get(symbole, symbole.removesuffix("USD"))
        print(f"\n=== {symbole} ({actif}) ===")

        soldes = broker._appel("GET", "/balance", params={"symbol": actif})
        if not soldes or all(
                float(s.get("available", 0) or 0) + float(s.get("inOrder", 0) or 0) <= 0
                for s in soldes):
            print(f"  avoir reel : AUCUN -- rien detenu, la position est deja fermee")
        for s in soldes:
            print(f"  avoir reel : {s['available']} disponible + {s['inOrder']} en ordre")

        marche = f"{actif}-{config.quote_asset}"
        ordres = broker._appel("GET", "/orders", params={"market": marche})
        if not ordres:
            print(f"  ordres     : aucun ordre en carnet sur {marche}")
        for o in sorted(ordres, key=lambda x: x.get("updated", 0), reverse=True):
            maj = o.get("updated")
            quand = _dt.datetime.fromtimestamp(maj / 1000, tz=_dt.timezone.utc) if maj else "?"
            print(f"  ordre {quand} : {o.get('side')} {o.get('orderType')} "
                  f"quantite {o.get('amount')} declenchement "
                  f"{o.get('triggerPrice') or o.get('price')} statut {o.get('status')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
