#!/usr/bin/env python3
"""Point d'entree dedie au moteur Coinbase Advanced Trade spot."""
from __future__ import annotations
import os
import gold_bot.engine as engine_module
from gold_bot.brokers import CoinbaseBroker, CoinbaseConfig
from gold_bot.engine import TradingEngine


def _coinbase_quote_currency(broker: str) -> str:
    return CoinbaseConfig.from_env().quote_asset if broker == "coinbase" else ""

engine_module._devise_du_lieu_d_execution = _coinbase_quote_currency

class CoinbaseTradingEngine(TradingEngine):
    def _build_broker(self):
        cfg = CoinbaseConfig.from_env()
        cfg.dry_run = bool(self.config.engine.dry_run)
        broker = CoinbaseBroker(cfg)
        if not broker.connect():
            raise RuntimeError("preflight Coinbase impossible: " + (getattr(broker, "_last_error", "connexion refusee") or "connexion refusee"))
        self._filtrer_univers_sur_le_broker(broker)
        for inst in self.universe:
            broker.register_instrument(inst)
        return broker

def main() -> int:
    os.environ["GB_ENGINE_BROKER"] = "coinbase"
    os.environ["GB_ENGINE_OFFLINE"] = "0"
    CoinbaseTradingEngine().run()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
