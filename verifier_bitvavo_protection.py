#!/usr/bin/env python3
"""Controle lecture seule des TP/SL reels Bitvavo.

Ce script ne cree, ne modifie et ne supprime aucun ordre. Il verifie que les
ordres de sortie du bot presents sur Bitvavo contiennent bien un stop-loss ET
un take-profit pour chaque marche.

Usage:
    python3 verifier_bitvavo_protection.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gold_bot.brokers import BitvavoBroker, BitvavoConfig  # noqa: E402


def load_env(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def main() -> int:
    load_env()
    cfg = BitvavoConfig.from_env()
    # Force lecture seule au niveau du broker: ce verifier ne peut pas trader.
    cfg.dry_run = True
    broker = BitvavoBroker(cfg)

    print("=== CONTROLE PROTECTION BITVAVO ===")
    if not cfg.api_key or not cfg.api_secret:
        print("[STOP] BITVAVO_API_KEY / BITVAVO_API_SECRET absents")
        return 2
    if not broker.connect():
        print(f"[STOP] connexion: {broker._last_error}")
        return 2

    rows = broker._appel("GET", "/ordersOpen", params={})
    exits = []
    for row in rows if isinstance(rows, list) else []:
        if str(row.get("side", "")).lower() != "sell":
            continue
        if int(row.get("operatorId", cfg.operator_id) or 0) != cfg.operator_id:
            continue
        if str(row.get("orderType", "")) not in {"stopLoss", "stopLossLimit", "takeProfit", "takeProfitLimit"}:
            continue
        exits.append(row)

    if not exits:
        print("[INFO] Aucun TP/SL ouvert du bot actuellement.")
        return 0

    by_market: dict[str, list[dict]] = {}
    for row in exits:
        by_market.setdefault(str(row.get("market", "?")), []).append(row)

    failures = 0
    for market, orders in sorted(by_market.items()):
        sl = [o for o in orders if str(o.get("orderType")) in {"stopLoss", "stopLossLimit"}]
        tp = [o for o in orders if str(o.get("orderType")) in {"takeProfit", "takeProfitLimit"}]
        print(f"{market}: SL={len(sl)} TP={len(tp)}")
        for o in orders:
            print("  -", o.get("orderType"), "trigger=", o.get("triggerPrice") or o.get("triggerAmount"), "id=", o.get("orderId"))
        if len(sl) != 1 or len(tp) != 1:
            print("  [STOP] protection incomplete ou dupliquee")
            failures += 1
        else:
            print("  [OK] TP + SL reels presents sur Bitvavo")

    if failures:
        print("\n[STOP] Une ou plusieurs protections sont incompletes.")
        return 3
    print("\n[OK] Toutes les sorties ouvertes du bot ont un TP et un SL.")
    print("Aucun ordre n'a ete cree, modifie ou annule par ce controle.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
