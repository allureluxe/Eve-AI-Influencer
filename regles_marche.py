#!/usr/bin/env python3
"""Ce que Bitvavo impose sur un marche, et ce que le robot enverrait.

Ecrit apres le refus du 23 aout sur LRC-EUR :

    [429] Field 'price' has too many decimal digits.

Le robot arrondit les prix au nombre de CHIFFRES SIGNIFICATIFS annonce par
`pricePrecision`. Le message de Bitvavo, lui, parle de DECIMALES. Les deux
notions ne coincident que pour les actifs autour de 1 : sur un actif a
0,0074 EUR, cinq chiffres significatifs font sept decimales.

Ce script ne devine rien : il lit la fiche du marche telle que la plateforme
la publie, et affiche a cote la chaine exacte que le robot enverrait. La
comparaison des deux dit ou est l'erreur, sans avoir a la supposer.

    python3 regles_marche.py                 # tous les marches detenus
    python3 regles_marche.py LRC BTC HBAR    # ces actifs seulement
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gold_bot.brokers.bitvavo import BitvavoBroker, BitvavoConfig, formater


def charger_env(chemin: str = ".env") -> None:
    if not os.path.exists(chemin):
        return
    with open(chemin, "r", encoding="utf-8") as fh:
        for ligne in fh:
            ligne = ligne.strip()
            if not ligne or ligne.startswith("#") or "=" not in ligne:
                continue
            cle, _, valeur = ligne.partition("=")
            os.environ.setdefault(cle.strip(), valeur.strip().strip('"').strip("'"))


def main() -> int:
    charger_env()
    demandes = [a.upper() for a in sys.argv[1:]]

    broker = BitvavoBroker(BitvavoConfig.from_env())
    marches = broker._appel("GET", "/markets", signe=False)
    prix = broker._prix_du_marche()
    devise = broker.config.quote_asset

    fiches = {m.get("market"): m for m in marches if isinstance(m, dict)}
    codes = [f"{a}-{devise}" for a in demandes] if demandes else sorted(
        c for c in fiches if c.endswith(f"-{devise}"))

    print("=" * 74)
    print("  REGLES DE PRIX — ce que Bitvavo publie, ce que le robot enverrait")
    print("=" * 74)

    for code in codes:
        fiche = fiches.get(code)
        if not fiche:
            print(f"\n{code} : marche inconnu")
            continue

        precision = int(fiche.get("pricePrecision", 5) or 5)
        cours = prix.get(code) or 0.0
        print(f"\n{code}   cours {cours:.10g}")
        print(f"   fiche publiee : {json.dumps(fiche, separators=(',', ':'))}")

        if not cours:
            continue

        # Exactement le chemin du robot : arrondi puis mise en forme.
        broker._regles.pop(code, None)
        broker._charger_regles()
        regle = broker._regles.get(code)
        if regle is None:
            print("   ce marche n'est pas dans l'univers du robot")
            continue

        stop = cours * 0.97
        limite = regle.arrondir_prix(stop * 0.998)
        declenchement = regle.arrondir_prix(stop)
        for nom, valeur in (("triggerAmount", declenchement), ("price", limite)):
            texte = formater(valeur)
            apres_virgule = len(texte.partition(".")[2])
            significatifs = len(texte.replace("-", "").replace(".", "").lstrip("0"))
            print(f"   {nom:<14} = {texte:<18} "
                  f"{significatifs} chiffre(s) significatif(s), "
                  f"{apres_virgule} decimale(s)")
        print(f"   pricePrecision annonce : {precision}")

    print("=" * 74)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
