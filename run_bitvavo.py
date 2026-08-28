#!/usr/bin/env python3
"""Point d'entrée Bitvavo marge / compte leveraged."""
from __future__ import annotations

import logging
import os
import time

import gold_bot.engine as engine_module
from gold_bot.brokers import BitvavoConfig, BitvavoMarginBroker
from gold_bot.scalping_engine import ContinuousScalpingEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _bitvavo_quote_currency(broker: str) -> str:
    if broker == "bitvavo":
        return BitvavoConfig.from_env().quote_asset
    return ""


engine_module._devise_du_lieu_d_execution = _bitvavo_quote_currency


class BitvavoTradingEngine(ContinuousScalpingEngine):
    """Moteur Bitvavo marge : scalping continu + pyramiding confirme."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            self.broker.sync()
            account = self.broker.account()
            self.risk.sync_account(account.equity, account.balance, account.currency)
            if (self.store.state.halted
                    and "drawdown maximal atteint" in (self.store.state.halt_reason or "")
                    and self.risk.account.drawdown_pct() < self.config.risk.max_drawdown_pct):
                self.risk.resume()
                self.store.state.halted = False
                self.store.state.halt_reason = ""
                self.store.save()
                logger.warning(
                    "REPRISE CONTROLEE : ancien arret drawdown leve, "
                    "drawdown actuel %.1f%% < seuil %.1f%% ; sommet historique conserve",
                    self.risk.account.drawdown_pct(),
                    self.config.risk.max_drawdown_pct,
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("reprise drawdown non effectuee : %s", str(exc)[:160])

    def _build_broker(self):
        bv = BitvavoConfig.from_env()
        bv.dry_run = bool(self.config.engine.dry_run)
        broker = BitvavoMarginBroker(bv)
        if not broker.connect():
            raise RuntimeError(
                "préflight Bitvavo marge impossible : "
                + (getattr(broker, "_last_error", "connexion refusée") or "connexion refusée")
            )
        self._filtrer_univers_sur_le_broker(broker)
        for inst in self.universe:
            broker.register_instrument(inst)
        return broker

    def run_cycle(self) -> None:
        started = time.monotonic()
        before = self.store.state.cycles
        account = self.broker.account()
        positions = self.broker.positions()
        logger.info(
            "CYCLE START #%d — capital %.2f %s — %d instrument(s) actifs — positions %d — mode %s",
            before + 1, account.equity, account.currency, len(self.universe),
            len(positions), getattr(self.broker, "mode", "inconnu"),
        )

        super().run_cycle()
        logger.info(
            "CYCLE END #%d — durée %.1fs — positions %d — trades ouverts %d",
            self.store.state.cycles, time.monotonic() - started,
            len(self.broker.positions()), self.store.state.trades_opened,
        )


def main() -> int:
    os.environ["GB_ENGINE_BROKER"] = "bitvavo"
    os.environ["GB_ENGINE_OFFLINE"] = "0"
    # Recherche rapide : on veut pouvoir revalider une continuation haussière
    # sans attendre plusieurs minutes entre deux décisions.
    os.environ["GB_ENGINE_IDLE_POLL_SECONDS"] = "5"
    os.environ["GB_ENGINE_POLL_SECONDS"] = "5"
    os.environ.setdefault("BITVAVO_MARGIN_ENABLED", "1")
    os.environ.setdefault("BITVAVO_MARGIN_LEVERAGE", "10")
    BitvavoTradingEngine().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
