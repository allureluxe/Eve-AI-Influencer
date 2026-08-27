#!/usr/bin/env python3
"""Controle Coinbase complet sans envoyer d'ordre."""
from __future__ import annotations
import os
import sys


def main() -> int:
    print("=== COINBASE PREFLIGHT / ZERO ORDER ===")
    key = (os.getenv("COINBASE_API_KEY") or os.getenv("COINBASE_KEY_NAME") or "").strip()
    secret = (os.getenv("COINBASE_API_SECRET") or os.getenv("COINBASE_PRIVATE_KEY") or "").strip()
    print("API key name :", "PRESENT" if key else "ABSENT")
    print("Private key  :", "PRESENT" if secret else "ABSENT")
    if not key or not secret:
        print("RESULTAT: EN ATTENTE DES CLES")
        return 2
    try:
        from coinbase import jwt_generator  # noqa: F401
        from gold_bot.brokers import CoinbaseBroker, CoinbaseConfig
    except Exception as exc:
        print("DEPENDANCES: KO", exc)
        return 3
    cfg = CoinbaseConfig.from_env()
    cfg.dry_run = False
    broker = CoinbaseBroker(cfg)
    ok = broker.connect()
    print("AUTHENTIFICATION :", "OK" if ok else "KO")
    if not ok:
        print("DETAIL :", getattr(broker, "_last_error", "connexion refusee"))
        return 4
    try:
        account = broker.account()
        print("COMPTE : OK")
        print("Devise :", account.currency)
        print("Solde disponible :", account.balance)
        print("Mode test : AUCUN ORDRE ENVOYE")
        print("RESULTAT : COINBASE PRETE")
        return 0
    except Exception as exc:
        print("LECTURE COMPTE : KO", exc)
        return 5

if __name__ == "__main__":
    raise SystemExit(main())
