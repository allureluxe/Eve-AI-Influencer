#!/usr/bin/env python3
"""Preflight Pionex USDT-M Futures sans aucun ordre.

Ce verifier ne place jamais d'ordre. Il valide :
- imports du broker Futures ;
- credentials presents ;
- mode reel ;
- catalogue des contrats PERP ;
- acces au compte Futures et solde USDT ;
- position mode et positions ouvertes ;
- acces au carnet du premier contrat tradable.

Usage sur le VPS :
    python3 verifier_pionex.py
"""
from __future__ import annotations

import os
import sys

from gold_bot.brokers import PionexFuturesBroker, PionexFuturesConfig


def env_file(path: str = ".env") -> None:
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


def ok(msg: str) -> None:
    print(f"[OK]   {msg}")


def stop(msg: str) -> int:
    print(f"[STOP] {msg}")
    return 2


def main() -> int:
    env_file()
    cfg = PionexFuturesConfig.from_env()

    print("===== PIONEX FUTURES PREFLIGHT =====")
    print(f"quote       : {cfg.quote_asset}")
    print(f"dry_run     : {cfg.dry_run}")
    print(f"leverage    : {cfg.leverage}x")
    print(f"margin_mode : {cfg.margin_mode}")
    print(f"position_mode: {cfg.position_mode}")

    if cfg.dry_run:
        return stop("PIONEX_DRY_RUN est actif : le service ne doit pas etre lance en reel.")
    if not cfg.api_key or not cfg.api_secret:
        return stop("PIONEX_API_KEY / PIONEX_API_SECRET absents.")
    ok("credentials presentes et mode reel")

    broker = PionexFuturesBroker(cfg)

    try:
        broker.apply_market_rules(None)
    except Exception as exc:
        return stop(f"catalogue Futures inaccessible : {exc}")

    if not broker._rules:
        return stop("aucun contrat Futures USDT-M en etat exploitable.")
    ok(f"catalogue Futures charge : {len(broker._rules)} contrat(s)")

    try:
        if not broker.connect():
            return stop("connexion Futures refusee")
        account = broker.account()
    except Exception as exc:
        return stop(f"compte Futures inaccessible : {exc}")

    if account.equity <= 0:
        return stop(f"equity Futures nulle ou negative : {account.equity:.8f} {account.currency}")
    ok(f"compte Futures accessible : equity={account.equity:.8f} {account.currency}, disponible={account.margin_free:.8f}")

    try:
        positions = broker.positions()
    except Exception as exc:
        return stop(f"lecture des positions impossible : {exc}")
    ok(f"positions Futures lues : {len(positions)}")

    symbol = next(iter(broker._rules))
    try:
        bid, ask = broker._book(symbol)
    except Exception as exc:
        return stop(f"carnet Futures inaccessible pour {symbol}: {exc}")
    if bid <= 0 or ask <= 0 or ask < bid:
        return stop(f"bid/ask invalide pour {symbol}: {bid}/{ask}")
    ok(f"market data OK : {symbol} bid={bid} ask={ask}")

    print("===== PREFLIGHT REUSSI =====")
    print("Aucun ordre n'a ete envoye.")
    print("Le service peut passer au moteur de strategie en mode REEL.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
