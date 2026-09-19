#!/usr/bin/env python3
"""Publie vers l'app les positions DEMO deja ouvertes, marquees is_demo.

    python3 publier_positions_demo_ouvertes.py [--pour de bon]

POURQUOI CE SCRIPT EXISTE. `SignalPublisher` ne publie qu'au MOMENT de
l'ouverture. Les positions ouvertes par la simulation pendant que la
publication Supabase etait coupee (le 18 sept., le temps de colmater la
fuite qui melangeait demo et reel -- voir run_demo.py) n'ont donc aucune
ligne en base : l'onglet Demo de l'application les montrait comme
inexistantes alors que le robot les tient toujours.

Il REUTILISE le vrai publieur (`SignalPublisher`, `SignalPublie`,
`paire_lisible`, `rediger_rationale`) plutot que de fabriquer le corps
JSON a la main : une ligne rattrapee doit etre indiscernable d'une ligne
publiee normalement, sinon l'ecart se paiera plus tard.

Une position dont la reference existe deja en base est IGNOREE
(`reference` porte un index unique) -- le script ne remplace ni
n'efface jamais rien, il complete seulement ce qui manque.

Sans `--pour-de-bon`, il ne fait qu'afficher ce qu'il publierait.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

RACINE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RACINE)

from gold_bot.env import charger_env  # noqa: E402

charger_env()

from gold_bot.signal_publisher import (  # noqa: E402
    SignalPublie, SignalPublisher, calculer_risk_reward, paire_lisible,
    rediger_rationale)

ETAT_DEMO = os.path.join(RACINE, "data", "state-demo.json")
# Capital virtuel de la simulation (robot.demo.json, start_balance) : il
# sert a reexprimer le risque en POURCENTAGE du capital, seule forme que
# la table `signals` connait (voir SignalPublie.position_size_pct).
CAPITAL_DEMO = 500.0
# Canal Donchian arme en demo (robot.demo.json, donchian_entrees) --
# uniquement pour rediger le texte d'explication, comme le fait le moteur.
CANAL_JOURS = 10


def _references_connues(publieur: SignalPublisher) -> set[str]:
    """Les `reference` deja presentes en base, quel que soit leur statut."""
    import urllib.request

    url = os.environ["SUPABASE_URL"].rstrip("/")
    cle = os.environ["SUPABASE_SERVICE_KEY"]
    requete = urllib.request.Request(
        f"{url}/rest/v1/signals?select=reference&reference=not.is.null",
        headers={"apikey": cle, "Authorization": f"Bearer {cle}"})
    with urllib.request.urlopen(requete, timeout=15) as r:
        return {l["reference"] for l in json.loads(r.read()) if l.get("reference")}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--pour-de-bon", action="store_true",
                   help="publie vraiment (sinon : simple apercu)")
    args = p.parse_args()

    with open(ETAT_DEMO, "r", encoding="utf-8") as f:
        etat = json.load(f)
    positions = etat.get("position_meta") or {}
    if not positions:
        print("aucune position ouverte cote demo, rien a publier")
        return 0

    # File d'attente DEDIEE : le nom par defaut
    # (`data/signaux_en_attente.jsonl`) est celui d'un robot sans suffixe
    # d'instance. Un rattrapage ponctuel ne doit jamais deposer ses
    # reliquats dans une file que le moteur pourrait relire.
    from pathlib import Path
    publieur = SignalPublisher.depuis_env(
        est_demo=True,
        fichier_file=Path("data/signaux_en_attente_rattrapage_demo.jsonl"))
    if not publieur.actif:
        print("pas de cle Supabase : publication impossible")
        return 2

    # On demande d'ABORD a la base ce qu'elle connait deja, au lieu de
    # tenter la publication et d'encaisser un 409 : au 3e refus d'affilee,
    # `SignalPublisher` se met en pause 5 minutes (protection normale
    # contre une base muette) et les references encore valides passent
    # alors a la trappe sans avoir ete essayees.
    deja = _references_connues(publieur)

    publies = 0
    for identifiant, meta in positions.items():
        etage = int(meta.get("etages", 1) or 1)
        reference = f"{identifiant}:{etage}"
        if reference in deja:
            print(f"deja en base, ignore : {paire_lisible(meta['symbol'], 'EUR')} "
                  f"({reference})")
            continue
        paire = paire_lisible(meta["symbol"], "EUR")
        entree = float(meta["entry_price"])
        stop = float(meta["stop_loss"])
        objectif = float(meta.get("take_profit") or 0) or None

        # Le risque en euros est EXACTEMENT ce que le simulateur a engage :
        # volume x distance au stop initial. Reexprime en pourcentage du
        # capital virtuel, c'est la valeur que le moteur aurait publiee.
        risque_eur = float(meta["volume"]) * abs(float(meta["initial_risk"]))
        risque_pct = risque_eur / CAPITAL_DEMO * 100.0

        signal = SignalPublie(
            reference=reference,
            pair=paire,
            side="buy" if str(meta["side"]).lower().startswith(("b", "a")) else "sell",
            entry_price=entree,
            stop_loss=stop,
            take_profit_1=objectif,
            risk_reward=calculer_risk_reward(entree, stop, objectif),
            position_size_pct=risque_pct,
            conviction=0,
            rationale=rediger_rationale(paire, CANAL_JOURS, etage=etage,
                                        graine=reference),
        )
        if not args.pour_de_bon:
            print(f"[apercu] {paire:12s} {signal.side:4s} entree {entree:<14.8g} "
                  f"stop {stop:<14.8g} risque {risque_pct:.3f} %")
            continue
        if publieur.publier_ouverture(signal):
            publies += 1
            print(f"publie : {paire} ({reference})")
        else:
            print(f"IGNORE : {paire} ({reference}) -- deja en base ou refuse")

    if args.pour_de_bon:
        print(f"\n{publies} position(s) publiee(s) sur {len(positions)}")
    else:
        print(f"\napercu seulement -- relancer avec --pour-de-bon "
              f"({len(positions)} position(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
