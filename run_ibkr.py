#!/usr/bin/env python3
"""Runner IBKR: branche le moteur existant sur le broker IBKR hardened."""
from __future__ import annotations

import sys

from gold_bot.brokers.ibkr_hardened import HardenedIBKRBroker
from gold_bot.engine import TradingEngine


# The historical engine already knows how to validate/configure "ibkr", but
# its generic broker factory predates the IBKR adapter. Keep the change local
# to this runner so the existing Bitvavo/Pionex/Paper paths remain untouched.
_original_build_broker = TradingEngine._build_broker


def _build_broker(self):
    if self.config.engine.broker == "ibkr":
        broker = HardenedIBKRBroker()
        if hasattr(broker, "supports"):
            self._filtrer_univers_sur_le_broker(broker)
        for inst in self.universe:
            if hasattr(broker, "register_instrument"):
                broker.register_instrument(inst)
        return broker
    return _original_build_broker(self)


TradingEngine._build_broker = _build_broker


if __name__ == "__main__":
    from run_bot import main
    # run_bot accepts the configuration file normally; the wrapper only
    # replaces the broker factory above.
    raise SystemExit(main())
