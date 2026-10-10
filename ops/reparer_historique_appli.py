#!/usr/bin/env python3
"""Remet l'HISTORIQUE des clôtures réelles de l'application d'accord avec le robot.

Trouvé le 10 oct. 2026 (l'opérateur : « les positions clôturées ne
s'affichent pas bien ») : depuis le 1er octobre, 45 trades réels sur 92
n'étaient pas dans l'application, et 6 avaient leur clôture écrite sur la
ligne d'un trade PRÉCÉDENT de la même crypto (prix d'achat et date faux).
Cause : la file de publication figée derrière une demande refusée, et
deux formats de référence. Corrigé dans `gold_bot/signal_publisher.py`.

La vérité est le journal du robot (`data/trades.jsonl`). Pour chaque trade
clos depuis --depuis :
  - la ligne de l'application OUVERTE au même moment (± 10 min, ou même
    prix d'achat) reçoit la clôture exacte : date, résultat, bénéfice ;
  - s'il n'y en a pas, une ligne close est créée (« SYM~ouverture:1 »).
Une ligne close « étage 1 » qui ne correspond à aucun trade est annulée
(bénéfice 0) : c'est une clôture écrite sur la mauvaise ligne.

    python3 ops/reparer_historique_appli.py               # montre seulement
    python3 ops/reparer_historique_appli.py --confirmer   # applique

N'envoie AUCUN ordre : ne touche qu'à l'affichage (table `signals`, compte réel).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))
os.chdir(RACINE)

from gold_bot.env import charger_env  # noqa: E402

charger_env()

from gold_bot.signal_publisher import SignalPublisher, _iso  # noqa: E402

TOLERANCE_OUVERTURE = 600.0


def _ts(iso: str | None) -> float:
    if not iso:
        return 0.0
    return dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


def _jour(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts).strftime("%d/%m %H:%M")


def principal() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--depuis", default="2026-10-01")
    p.add_argument("--confirmer", action="store_true")
    a = p.parse_args()

    pub = SignalPublisher.depuis_env()
    if pub.client is None or pub.est_demo:
        print("publieur inactif ou en démo : rien à faire")
        return 1
    depuis = dt.datetime.fromisoformat(a.depuis).timestamp()

    lignes = pub.client._appel(
        "GET", "signals?select=reference,pair,status,published_at,closed_at,"
               "profit_eur,entry_price&is_demo=eq.false"
               f"&published_at=gte.{_iso(depuis - 5 * 86400)}")
    trades = [json.loads(l) for l in open("data/trades.jsonl") if l.strip()]
    trades = [t for t in trades if (t.get("closed_at") or 0) >= depuis
              and not t.get("partial")]

    prises: set[str] = set()
    corrections, creations = [], []
    for t in sorted(trades, key=lambda t: t["opened_at"]):
        paire = t["symbol"][:-3] + "/EUR"
        entree = float(t["entry_price"])
        sens = 1.0 if str(t.get("side", "BUY")).upper().startswith(("B", "A")) else -1.0
        res_pct = sens * (float(t["exit_price"]) - entree) / entree * 100.0 if entree else 0.0
        corps = {"status": "closed_tp" if t["profit"] >= 0 else "closed_sl",
                 "closed_at": _iso(t["closed_at"]),
                 "result_pct": round(res_pct, 3),
                 "profit_eur": round(float(t["profit"]), 2)}

        def candidate(l):
            if l["pair"] != paire or l["reference"] in prises:
                return False
            if l["reference"].rsplit(":", 1)[-1] != "1":
                return False
            proche = abs(_ts(l["published_at"]) - t["opened_at"]) <= TOLERANCE_OUVERTURE
            meme_prix = abs(float(l["entry_price"] or 0) - entree) <= entree * 0.001
            return proche or meme_prix
        cands = sorted([l for l in lignes if candidate(l)],
                       key=lambda l: abs(_ts(l["published_at"]) - t["opened_at"]))
        if cands:
            l = cands[0]
            prises.add(l["reference"])
            deja = (l["status"] == corps["status"]
                    and abs(_ts(l["closed_at"]) - t["closed_at"]) < 120
                    and l.get("profit_eur") is not None
                    and abs(float(l["profit_eur"]) - corps["profit_eur"]) < 0.015)
            if not deja:
                corrections.append((l["reference"], corps, t))
        else:
            ref = f"{t['symbol']}~{int(t['opened_at'])}:1"
            ligne = {
                "reference": ref, "pair": paire,
                "side": "buy" if sens > 0 else "sell",
                "entry_price": round(entree, 8),
                "stop_loss": round(float(t.get("stop_loss") or entree), 8),
                "rationale": f"Clôture reconstituée depuis le journal du robot : {t.get('reason', '')}.",
                "conviction": 0, "macro_flag": False,
                "published_at": _iso(t["opened_at"]),
                "is_demo": False, "compte": "reel",
                "volume": float(t.get("volume") or 0),
                **corps,
            }
            creations.append((ligne, t))

    # Lignes closes etage 1 depuis --depuis, sans trade : clotures mal placees.
    orphelines = [l for l in lignes
                  if l["reference"] not in prises
                  and l["reference"].rsplit(":", 1)[-1] == "1"
                  and l["status"] in ("closed_tp", "closed_sl")
                  and _ts(l["closed_at"]) >= depuis]

    for ref, corps, t in corrections:
        print(f"  CORRIGE  {t['symbol'][:-3] + '/EUR':12} {ref:28} {_jour(t['opened_at'])} -> "
              f"{_jour(t['closed_at'])}  {corps['profit_eur']:+.2f} EUR")
    for ligne, t in creations:
        print(f"  AJOUTE   {ligne['pair']:12} {ligne['reference']:28} {_jour(t['opened_at'])} -> "
              f"{_jour(t['closed_at'])}  {ligne['profit_eur']:+.2f} EUR")
    for l in orphelines:
        print(f"  ANNULE   {l['pair']:12} {l['reference']:28} (aucun trade du robot ne lui correspond, "
              f"affichait {l.get('profit_eur')} EUR)")
    total = sum(t["profit"] for t in trades)
    print(f"\n{len(trades)} trades du robot depuis le {a.depuis}, total {total:+.2f} EUR ; "
          f"{len(corrections)} à corriger, {len(creations)} à ajouter, {len(orphelines)} à annuler.")
    if not a.confirmer:
        print("Relancer avec --confirmer pour appliquer.")
        return 0

    for ref, corps, _ in corrections:
        pub.client.modifier("signals", f"reference=eq.{ref}", corps)
    for ligne, _ in creations:
        pub.client.inserer("signals", ligne)
    for l in orphelines:
        pub.client.modifier("signals", f"reference=eq.{l['reference']}",
                            {"status": "cancelled", "result_pct": 0.0, "profit_eur": 0.0})
    print("Appliqué.")
    return 0


if __name__ == "__main__":
    sys.exit(principal())
