#!/usr/bin/env python3
"""Lance la meme strategie du robot sur Pionex, independamment de Bitvavo.

Usage:
  GB_ENGINE_BROKER=pionex python3 run_pionex.py

Les journaux et l'etat sont separes via instance=\"pionex\" dans TradingEngine.
Les cles restent dans l'environnement : PIONEX_API_KEY / PIONEX_API_SECRET.
"""
from __future__ import annotations

import os

from gold_bot.brokers import PionexBroker, PionexConfig
from gold_bot.engine import TradingEngine


class PionexTradingEngine(TradingEngine):
    """Meme moteur/strategie, mais broker Pionex."""

    def _build_broker(self):
        cfg = self.config.engine
        px = PionexConfig.from_env()
        if cfg.dry_run:
            px.dry_run = True
        broker = PionexBroker(px)
        if hasattr(broker, "supports"):
            self._filtrer_univers_sur_le_broker(broker)
        for inst in self.universe:
            broker.register_instrument(inst)
        return broker


def main() -> int:
    os.environ["GB_ENGINE_BROKER"] = "pionex"
    engine = PionexTradingEngine()
    engine.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
