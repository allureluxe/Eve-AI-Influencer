#!/usr/bin/env python3
"""Lance la meme strategie du robot sur Pionex Futures, independamment de Bitvavo.

Usage:
  python3 run_pionex.py

Le compte, l'etat et le journal sont separes de Bitvavo via instance="pionex".
Les cles restent dans l'environnement : PIONEX_API_KEY / PIONEX_API_SECRET.
"""
from __future__ import annotations

import os

import gold_bot.engine as engine_module
from gold_bot.brokers import PionexFuturesBroker, PionexFuturesConfig
from gold_bot.engine import TradingEngine


def _pionex_quote_currency(broker: str) -> str:
    if broker == "pionex":
        return PionexFuturesConfig.from_env().quote_asset
    return engine_module._devise_du_lieu_d_execution(broker)


# Le registre de donnees doit travailler dans la meme devise que le compte
# Futures Pionex. On conserve le comportement Bitvavo pour l'autre instance.
engine_module._devise_du_lieu_d_execution = _pionex_quote_currency


class PionexTradingEngine(TradingEngine):
    """Meme strategie et moteur, mais execution sur Pionex USDT-M Futures."""

    def _build_broker(self):
        cfg = self.config.engine
        px = PionexFuturesConfig.from_env()
        if cfg.dry_run:
            px.dry_run = True
        broker = PionexFuturesBroker(px)
        if hasattr(broker, "supports"):
            self._filtrer_univers_sur_le_broker(broker)
        for inst in self.universe:
            broker.register_instrument(inst)
        return broker


def main() -> int:
    # Cette instance est volontairement independante du robot Bitvavo.
    os.environ["GB_ENGINE_BROKER"] = "pionex"
    engine = PionexTradingEngine()
    engine.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
