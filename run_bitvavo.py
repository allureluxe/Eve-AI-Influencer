#!/usr/bin/env python3
"""Point d'entrée dédié au moteur Bitvavo spot."""
from __future__ import annotations

import os

import gold_bot.engine as engine_module
from gold_bot.brokers import BitvavoBroker, BitvavoConfig
from gold_bot.engine import TradingEngine


def _bitvavo_quote_currency(broker: str) -> str:
    if broker == "bitvavo":
        return BitvavoConfig.from_env().quote_asset
    return ""


engine_module._devise_du_lieu_d_execution = _bitvavo_quote_currency


class BitvavoTradingEngine(TradingEngine):
    """Moteur verrouillé sur Bitvavo spot."""

    def _build_broker(self):
        bv = BitvavoConfig.from_env()
        bv.dry_run = bool(self.config.engine.dry_run)
        broker = BitvavoBroker(bv)

        # connect() est le préflight officiel du broker : authentification,
        # compte et chargement des marchés/règles. Aucun ordre n'est envoyé.
        if not broker.connect():
            raise RuntimeError(
                "préflight Bitvavo impossible : " +
                (getattr(broker, "_last_error", "connexion refusée") or "connexion refusée")
            )

        self._filtrer_univers_sur_le_broker(broker)
        for inst in self.universe:
            broker.register_instrument(inst)
        return broker


def main() -> int:
    os.environ["GB_ENGINE_BROKER"] = "bitvavo"
    os.environ["GB_ENGINE_OFFLINE"] = "0"
    BitvavoTradingEngine().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
