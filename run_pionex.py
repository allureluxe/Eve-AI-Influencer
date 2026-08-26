#!/usr/bin/env python3
"""Point d'entree live Pionex Futures."""
from __future__ import annotations

import logging
import os

import gold_bot.engine as engine_module
from gold_bot.brokers import HardenedPionexFuturesBroker, PionexFuturesConfig
from gold_bot.core import Side
from gold_bot.engine import TradingEngine

_ORIGINAL_DEVise = engine_module._devise_du_lieu_d_execution
logger = logging.getLogger(__name__)


def _pionex_quote_currency(broker: str) -> str:
    if broker == "pionex":
        return PionexFuturesConfig.from_env().quote_asset
    return _ORIGINAL_DEVise(broker)


engine_module._devise_du_lieu_d_execution = _pionex_quote_currency


class PionexTradingEngine(TradingEngine):
    """Moteur autonome avec le broker Pionex Futures durci."""

    def _build_broker(self):
        px = PionexFuturesConfig.from_env()
        px.dry_run = False
        self.config.engine.dry_run = False
        broker = HardenedPionexFuturesBroker(px)
        self._filtrer_univers_sur_le_broker(broker)
        for inst in self.universe:
            broker.register_instrument(inst)
        return broker

    def _emergency_protect_positions(self, positions) -> None:
        for pos in list(positions):
            if pos.stop_loss <= 0 and pos.take_profit <= 0:
                continue
            instrument = self.universe.get(pos.symbol)
            if instrument is None:
                continue
            try:
                tick = self.registry.tick(pos.symbol, instrument.asset_class)
            except Exception as exc:  # noqa: BLE001
                logger.warning("protection %s : tick indisponible : %s", pos.symbol, str(exc)[:120])
                continue
            if tick is None:
                continue
            exit_price = tick.exit_price_for(pos.side)
            stop_hit = ((pos.side is Side.BUY and pos.stop_loss > 0 and exit_price <= pos.stop_loss) or
                        (pos.side is Side.SELL and pos.stop_loss > 0 and exit_price >= pos.stop_loss))
            target_hit = ((pos.side is Side.BUY and pos.take_profit > 0 and exit_price >= pos.take_profit) or
                          (pos.side is Side.SELL and pos.take_profit > 0 and exit_price <= pos.take_profit))
            if not stop_hit and not target_hit:
                continue
            reason = "stop loss d'urgence" if stop_hit else "take profit d'urgence"
            try:
                trade = self.broker.close_position(pos.id, None, reason)
                if trade:
                    self._on_trade_closed(trade)
                    logger.warning("PROTECTION URGENCE %s %s @ %.8f (%s)", pos.side.value, pos.symbol, exit_price, reason)
            except Exception as exc:  # noqa: BLE001
                logger.error("PROTECTION URGENCE ECHEC %s %s : %s", pos.side.value, pos.symbol, str(exc)[:300])

    def _manage_positions(self, positions) -> None:
        self._emergency_protect_positions(positions)
        super()._manage_positions(self.broker.positions())


def main() -> int:
    os.environ["GB_ENGINE_BROKER"] = "pionex"
    os.environ["GB_ENGINE_OFFLINE"] = "0"
    PionexTradingEngine().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
