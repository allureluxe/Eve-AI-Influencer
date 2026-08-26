#!/usr/bin/env python3
"""Lance la strategie du robot sur Pionex USDT-M Futures.

Cette instance est independante de Bitvavo. Les secrets restent dans
l'environnement PIONEX_API_KEY / PIONEX_API_SECRET.

IMPORTANT : ce lanceur est volontairement ARME EN REEL. Il ne place aucun
ordre pendant son preflight, mais une fois engine.run() lance, les ordres
valides sont envoyes a Pionex Futures.
"""
from __future__ import annotations

import os

import gold_bot.engine as engine_module
from gold_bot.brokers import PionexFuturesBroker, PionexFuturesConfig
from gold_bot.engine import TradingEngine

_ORIGINAL_DEVise = engine_module._devise_du_lieu_d_execution


def _pionex_quote_currency(broker: str) -> str:
    if broker == "pionex":
        return PionexFuturesConfig.from_env().quote_asset
    return _ORIGINAL_DEVise(broker)


# Le registre de donnees doit travailler dans la meme devise que le compte
# Futures Pionex. On conserve le comportement des autres instances.
engine_module._devise_du_lieu_d_execution = _pionex_quote_currency


class PionexTradingEngine(TradingEngine):
    """Meme strategie et moteur, avec execution Pionex Futures."""

    def _build_broker(self):
        cfg = self.config.engine
        px = PionexFuturesConfig.from_env()

        # Ce lanceur est le point d'entree LIVE : on ne laisse pas une vieille
        # valeur dry_run dans robot.json transformer silencieusement le robot
        # en simulation. Une erreur de cles/permissions fait echouer le
        # preflight au lieu de basculer vers un faux compte.
        px.dry_run = False
        self.config.engine.dry_run = False

        broker = PionexFuturesBroker(px)
        if hasattr(broker, "supports"):
            self._filtrer_univers_sur_le_broker(broker)
        for inst in self.universe:
            broker.register_instrument(inst)
        return broker


def main() -> int:
    # Instance dediee : les etats et journaux utilisent la cle "pionex".
    os.environ["GB_ENGINE_BROKER"] = "pionex"
    os.environ["GB_ENGINE_OFFLINE"] = "0"

    # Aucun mode simulation : les credentials doivent etre presents et
    # autoriser la lecture + le trading Futures. Le broker effectuera le
    # controle des contrats, du compte, du mode de position et du solde avant
    # toute ouverture de position.
    engine = PionexTradingEngine()
    engine.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
