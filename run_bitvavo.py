#!/usr/bin/env python3
"""Point d'entrée dédié au moteur Bitvavo spot."""
from __future__ import annotations

import logging
import os
import time

import gold_bot.engine as engine_module
from gold_bot.brokers import BitvavoBroker, BitvavoConfig
from gold_bot.engine import TradingEngine


# Le service systemd peut avoir un environnement de logging différent du shell.
# Configurer explicitement le niveau ici rend chaque cycle observable sans
# modifier les garde-fous ni les règles de risque.
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

    def run_cycle(self) -> None:
        """Exécute un cycle et rend son état visible dans journalctl."""
        started = time.monotonic()
        before = self.store.state.cycles
        logger.info(
            "CYCLE START #%d — capital %.2f %s — %d instrument(s) actifs",
            before + 1,
            self.broker.account().equity,
            self.broker.account().currency,
            len(self.universe),
        )
        super().run_cycle()
        logger.info(
            "CYCLE END #%d — durée %.1fs — positions %d — trades ouverts %d",
            self.store.state.cycles,
            time.monotonic() - started,
            len(self.broker.positions()),
            self.store.state.trades_opened,
        )


def main() -> int:
    os.environ["GB_ENGINE_BROKER"] = "bitvavo"
    os.environ["GB_ENGINE_OFFLINE"] = "0"
    # Pour le scalping demandé : même sans position, le moteur doit repasser
    # par l'analyse toutes les 20 secondes. Cela évite le basculement silencieux
    # vers une cadence de 5 minutes lorsque aucun marché n'est considéré ouvert.
    os.environ["GB_ENGINE_IDLE_POLL_SECONDS"] = "20"
    os.environ["GB_ENGINE_POLL_SECONDS"] = "20"
    BitvavoTradingEngine().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
