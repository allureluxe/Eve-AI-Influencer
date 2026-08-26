#!/usr/bin/env python3
"""Point d'entrée dédié au moteur Bitvavo spot.

Le script verrouille le lieu d'exécution sur Bitvavo, refuse le mode offline,
laisse le dry-run gouverné par la configuration et effectue un préflight
lecture seule avant de lancer la boucle.
"""
from __future__ import annotations

import logging
import os

import gold_bot.engine as engine_module
from gold_bot.brokers import BitvavoBroker, BitvavoConfig
from gold_bot.engine import TradingEngine

logger = logging.getLogger(__name__)


def _bitvavo_quote_currency(broker: str) -> str:
    if broker == "bitvavo":
        return BitvavoConfig.from_env().quote_asset
    return ""


engine_module._devise_du_lieu_d_execution = _bitvavo_quote_currency


class BitvavoTradingEngine(TradingEngine):
    """Moteur avec Bitvavo comme unique lieu d'exécution."""

    def _build_broker(self):
        bv = BitvavoConfig.from_env()
        # La configuration globale reste la source de vérité du mode.
        bv.dry_run = bool(self.config.engine.dry_run)
        broker = BitvavoBroker(bv)

        # Charge les marchés réels avant de filtrer l'univers. Cela évite de
        # scanner des actifs inexistants ou non cotables en EUR.
        try:
            broker.refresh_markets()
        except Exception as exc:
            raise RuntimeError(f"préflight Bitvavo impossible : {exc}") from exc

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
