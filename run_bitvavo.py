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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Un ancien arrêt par drawdown doit rester protecteur, mais ne doit
        # pas rester bloqué après modification/relèvement contrôlé du seuil.
        # On ne réinitialise JAMAIS le sommet historique : le drawdown réel
        # reste donc intact. La reprise n'est autorisée que si le compte est
        # actuellement sous le seuil configuré.
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
        """Exécute un cycle avec diagnostic explicite des blocages d'entrée."""
        started = time.monotonic()
        before = self.store.state.cycles
        account = self.broker.account()
        positions = self.broker.positions()
        logger.info(
            "CYCLE START #%d — capital %.2f %s — %d instrument(s) actifs — positions %d",
            before + 1,
            account.equity,
            account.currency,
            len(self.universe),
            len(positions),
        )

        # Diagnostic AVANT le cycle complet : il expose immédiatement la
        # barrière qui empêchait jusque-là le scanner d'apparaître dans les
        # logs (pause, quota, perte, positions, délai, etc.). Il ne contourne
        # aucune protection et n'envoie aucun ordre.
        self.broker.sync()
        account = self.broker.account()
        self.risk.sync_account(account.equity, account.balance, account.currency)
        positions = self.broker.positions()
        allowed, why = self.risk.can_trade(positions)
        objective_stop, objective_why = self.objectives.should_stop_trading()
        if not allowed:
            logger.info(
                "ENTREE BLOQUEE — raison=%s — capital %.2f %s — positions %d — trades_jour %d — pnl_jour %.2f%% — pnl_semaine %.2f%% — pertes_consecutives %d",
                why,
                account.equity,
                account.currency,
                len(positions),
                self.risk.account.trades_today,
                self.risk.account.daily_pnl_pct(),
                self.risk.account.weekly_pnl_pct(),
                self.risk.account.consecutive_losses,
            )
        elif objective_stop:
            logger.info("ENTREE BLOQUEE — objectif : %s", objective_why)
        else:
            logger.info(
                "ENTREE AUTORISEE — scanner %d instrument(s) — objectif %.2f — réalisé %.2f",
                len(self.universe),
                self.objectives.target,
                self.objectives.state.realized_this_week,
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
