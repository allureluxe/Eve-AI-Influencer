#!/usr/bin/env python3
"""Remet les positions RÉELLES de l'application d'accord avec le compte Bitvavo.

Trouvé le 9 oct. 2026 (l'opérateur : « sur l'application il n'y est pas
mentionné ») : l'application ne reçoit que des ÉVÉNEMENTS — une ouverture,
une clôture — au moment où ils arrivent. Un événement raté (redémarrage,
vente à la main, panne réseau) reste faux pour toujours :

    BNT, XLM   affichées depuis le 29 sept., vendues depuis longtemps
    PARTI, ZK  détenues sur le compte, absentes de l'application

La vérité est le compte Bitvavo. Ce script :
  - CLÔT (statut « cancelled », résultat inconnu donc 0) toute ligne active
    dont la crypto n'est plus détenue ;
  - PUBLIE les étages manquants d'une crypto détenue, à partir de la
    mémoire du robot (data/state.json : prix d'achat, stop, étages).

    python3 ops/resynchroniser_appli_reel.py              # montre seulement
    python3 ops/resynchroniser_appli_reel.py --confirmer  # applique

Il n'envoie AUCUN ordre : il ne touche qu'à l'affichage (table `signals`).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))
os.chdir(RACINE)

from gold_bot.env import charger_env  # noqa: E402

charger_env()

from gold_bot.signal_publisher import SignalPublie, SignalPublisher  # noqa: E402

#: sous ce montant, un reste d'avoir est de la poussière, pas une position
POUSSIERE_EUR = 1.0


def _bitvavo(chemin: str):
    cle, secret = os.environ["BITVAVO_API_KEY"], os.environ["BITVAVO_API_SECRET"]
    ts = str(int(time.time() * 1000))
    sig = hmac.new(secret.encode(), (ts + "GET/v2" + chemin).encode(),
                   hashlib.sha256).hexdigest()
    req = urllib.request.Request("https://api.bitvavo.com/v2" + chemin, headers={
        "Bitvavo-Access-Key": cle, "Bitvavo-Access-Signature": sig,
        "Bitvavo-Access-Timestamp": ts, "Bitvavo-Access-Window": "10000"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def actifs_detenus() -> dict[str, float]:
    """{actif: valeur en EUR} pour tout ce qui dépasse la poussière."""
    with urllib.request.urlopen("https://api.bitvavo.com/v2/ticker/price", timeout=30) as r:
        prix = {p["market"]: float(p["price"]) for p in json.load(r) if p.get("price")}
    detenus = {}
    for x in _bitvavo("/balance"):
        if x["symbol"] == "EUR":
            continue
        valeur = (float(x["available"]) + float(x["inOrder"])) * prix.get(x["symbol"] + "-EUR", 0)
        if valeur >= POUSSIERE_EUR:
            detenus[x["symbol"]] = valeur
    return detenus


def lignes_actives() -> list[dict]:
    url = os.environ["SUPABASE_URL"].rstrip("/")
    cle = os.environ["SUPABASE_SERVICE_KEY"]
    q = urllib.parse.urlencode({
        "select": "reference,pair,published_at", "status": "eq.active",
        "is_demo": "eq.false", "compte": "eq.reel"})
    req = urllib.request.Request(f"{url}/rest/v1/signals?{q}",
                                 headers={"apikey": cle, "Authorization": "Bearer " + cle})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def memoire_du_robot() -> dict[str, dict]:
    etat = json.loads((RACINE / "data" / "state.json").read_text())
    return {m["symbol"]: m for m in (etat.get("position_meta") or {}).values()
            if float(m.get("volume") or 0) > 0}


def main() -> int:
    confirmer = "--confirmer" in sys.argv
    detenus = actifs_detenus()
    lignes = lignes_actives()
    memoire = memoire_du_robot()
    pub = SignalPublisher.depuis_env(
        fichier_file=Path("data/signaux_en_attente_resync.jsonl"), est_demo=False)

    print(f"Compte Bitvavo : {', '.join(f'{a} {v:.2f} €' for a, v in sorted(detenus.items()))}")
    print(f"Application    : {len(lignes)} ligne(s) active(s)\n")

    actions = 0
    # 1. Fantômes : la ligne vit encore, la crypto n'est plus là.
    for ligne in lignes:
        actif = ligne["pair"].split("/")[0]
        if actif not in detenus:
            actions += 1
            print(f"  FANTÔME   {ligne['pair']:12} {ligne['reference']:40} -> clôture (cancelled)")
            if confirmer:
                pub.publier_cloture(ligne["reference"], "cancelled", time.time(), 0.0,
                                    profit_eur=0.0)

    # 2. Manquants : la crypto est détenue, un ou plusieurs étages absents.
    # Present = une ligne ACTIVE de cette crypto a cet etage, quel que soit
    # le format de reference (ancien « ZKUSD:1 » ou unique « ZKUSD~...:1 »).
    presents = {(l["reference"].split("~")[0].split(":")[0], l["reference"].rsplit(":", 1)[-1])
                for l in lignes}
    for actif in sorted(detenus):
        symbole = f"{actif}USD"
        m = memoire.get(symbole)
        if m is None:
            print(f"  ?         {actif:12} détenu mais inconnu du robot : rien publié")
            continue
        for etage in range(1, int(m.get("etages") or 1) + 1):
            if (symbole, str(etage)) in presents:
                continue
            # Toujours le format UNIQUE : l'ancien « ZKUSD:1 » appartient
            # souvent a une ligne FERMEE d'un trade precedent, et Supabase
            # refuse le doublon (c'est le defaut qui les a fait disparaitre).
            ref = f"{symbole}~{int(float(m.get('opened_at') or time.time()))}:{etage}"
            actions += 1
            print(f"  MANQUANT  {actif + '/EUR':12} {ref:40} -> publication "
                  f"(achat {m['entry_price']}, stop {m['stop_loss']})")
            if confirmer:
                pub.publier_ouverture(SignalPublie(
                    reference=ref, pair=f"{actif}/EUR", side="buy",
                    entry_price=float(m["entry_price"]), stop_loss=float(m["initial_stop"] or m["stop_loss"]),
                    volume=float(m["volume"]), compte="reel",
                    rationale="Position reprise par la resynchronisation avec le compte Bitvavo."))
                if float(m.get("stop_loss") or 0) and m.get("stop_loss") != m.get("initial_stop"):
                    pub.publier_suivi(ref, float(m["stop_loss"]))

    if not actions:
        print("  Tout est d'accord : rien à faire.")
    elif not confirmer:
        print(f"\n{actions} correction(s). Relancer avec --confirmer pour les appliquer.")
    else:
        print(f"\n{actions} correction(s) envoyée(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
