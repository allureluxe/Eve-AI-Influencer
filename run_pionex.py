#!/usr/bin/env python3
"""Lance la meme strategie du robot sur Pionex, independamment de Bitvavo.

Usage:
  python3 run_pionex.py

Les journaux et l'etat sont separes via instance="pionex" dans TradingEngine.
Les cles restent dans l'environnement : PIONEX_API_KEY / PIONEX_API_SECRET.
"""
from __future__ import annotations

import os

import gold_bot.engine as engine_module
from gold_bot.brokers import PionexBroker, PionexConfig
from gold_bot.engine import TradingEngine


# Le moteur historique sait imposer la devise de Bitvavo. Pionex est USDT par
# defaut : on lui injecte la devise choisie afin d'eviter un fallback EUR/USD
# incoherent dans les donnees crypto.
def _pionex_quote_currency(broker: str) -> str:
    if broker == "pionex":
        return PionexConfig.from_env().quote_asset
    return engine_module._devise_du_lieu_d_execution(broker)


engine_module._devise_du_lieu_d_execution = _pionex_quote_currency


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
