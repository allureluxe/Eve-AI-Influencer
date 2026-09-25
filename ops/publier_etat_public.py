#!/usr/bin/env python3
"""Publie le capital reel et la variation du jour, pour l'ecran d'accueil.

POURQUOI CE SCRIPT EXISTE A PART. Le robot calcule deja ces chiffres en
memoire (`RiskManager.daily_pnl_pct`), mais seulement dans le processus
en cours -- rien ne les ecrit sur disque, et l'application n'a aucun
moyen de les lire. Plutot que de faire dependre l'app du processus du
robot, ce script lit le compte Bitvavo directement (comme les outils de
diagnostic du depot) et republie une valeur independante.

Le "debut de journee" est mesure ici, pas emprunte au robot : un
fichier local retient le capital au premier passage de la journee
(UTC), et la variation se calcule contre cette reference. Comme
`chien_de_garde.py --recaler`, un depot ou un retrait en cours de
journee fera bouger ce pourcentage de facon visible -- assume, personne
ne pretend ici distinguer un mouvement de tresorerie d'un trade.

Lance par cron toutes les 5 minutes.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.request

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from gold_bot.env import charger_env  # noqa: E402

charger_env()

from gold_bot.brokers.bitvavo import BitvavoBroker  # noqa: E402

FICHIER_REFERENCE = os.path.join(RACINE, "data", "etat_public_jour.json")


def _capital_actuel() -> float:
    b = BitvavoBroker()
    b.connect()
    soldes = b._appel("GET", "/balance")
    total = 0.0
    non_eur = []
    for s in soldes:
        montant = float(s["available"]) + float(s["inOrder"])
        if montant <= 0:
            continue
        if s["symbol"] == "EUR":
            total += montant
        else:
            non_eur.append((s["symbol"], montant))
    if non_eur:
        marche = b._appel("GET", "/ticker/price")
        prix = {m["market"]: float(m["price"]) for m in marche}
        for symbole, montant in non_eur:
            p = prix.get(f"{symbole}-EUR")
            if p:
                total += montant * p
    return total


def _reference_du_jour(capital_actuel: float) -> float:
    """Capital de reference pour aujourd'hui. Cree la reference si absente."""
    aujourd_hui = dt.datetime.now(dt.timezone.utc).date().isoformat()
    donnees = {}
    try:
        with open(FICHIER_REFERENCE, "r", encoding="utf-8") as f:
            donnees = json.load(f)
    except (OSError, json.JSONDecodeError):
        pass

    if donnees.get("date") != aujourd_hui:
        donnees = {"date": aujourd_hui, "capital": capital_actuel}
        os.makedirs(os.path.dirname(FICHIER_REFERENCE), exist_ok=True)
        with open(FICHIER_REFERENCE, "w", encoding="utf-8") as f:
            json.dump(donnees, f)
    return float(donnees["capital"])


def _publier(capital: float, variation_pct: float) -> None:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    cle = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not url or not cle:
        print("SUPABASE_URL ou SUPABASE_SERVICE_KEY absent, rien publie")
        return
    corps = json.dumps({
        "id": "robot",
        "capital_eur": round(capital, 2),
        "variation_jour_pct": round(variation_pct, 3),
    }).encode()
    requete = urllib.request.Request(
        f"{url}/rest/v1/etat_public",
        method="POST", data=corps,
        headers={
            "apikey": cle, "Authorization": f"Bearer {cle}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        })
    try:
        with urllib.request.urlopen(requete, timeout=15):
            pass
        print(f"publie : {capital:.2f} EUR, jour {variation_pct:+.2f} %")
    except urllib.error.HTTPError as exc:
        print(f"echec HTTP {exc.code} : {exc.read()[:300]}")


def main() -> int:
    capital = _capital_actuel()
    reference = _reference_du_jour(capital)
    # UNE REFERENCE MINUSCULE NE PRODUIT PAS UN POURCENTAGE, ELLE PRODUIT
    # UNE ABSURDITE. Le 25 septembre, la reference valait quelques
    # millioniemes d'euro (reste des retraits du 16) et le depot de
    # 120 EUR donnait **+1 108 353 435 753 %**. C'est arithmetiquement
    # exact et cela ne veut rien dire.
    #
    # En dessous d'un euro de reference, la comparaison n'a pas de sens :
    # on annonce 0 plutot qu'un nombre qui ferait douter de tout le
    # reste de l'ecran.
    if reference >= 1.0:
        variation = (capital - reference) / reference * 100.0
    else:
        variation = 0.0
    # LA COLONNE REFUSE AU-DELA DE 999,999 — ET L'ECHEC EST SILENCIEUX.
    #
    # `variation_jour_pct` est un numeric(6,3) : au-dela de 1 000 %,
    # PostgREST rejette la ligne ENTIERE avec un 22003, donc le CAPITAL
    # n'est pas ecrit non plus. La table est restee bloquee a 0 EUR du
    # 14 au 25 septembre pendant que la tache echouait toutes les cinq
    # minutes dans son journal.
    #
    # Ce cas n'est pas exotique : il suffit que la reference du jour soit
    # minuscule. Le 16, l'operateur a tout retire — reference proche de
    # zero, puis un depot de 120 EUR le 25, et la variation part a
    # plusieurs milliers de pour cent. Arithmetiquement correcte, et
    # refusee par la base.
    #
    # On borne donc l'affichage au lieu de perdre la ligne. Un
    # « +999,9 % » est faux de peu ; un capital a zero est faux de tout.
    if variation > 999.0:
        log_borne = variation
        variation = 999.0
        print(f"variation bornee : {log_borne:+.0f} % -> +999 % "
              "(la colonne refuse au-dela, voir le commentaire)")
    elif variation < -999.0:
        variation = -999.0
    _publier(capital, variation)
    return 0


if __name__ == "__main__":
    sys.exit(main())
