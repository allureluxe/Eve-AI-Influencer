from __future__ import annotations

import json
import logging
import os
from typing import Optional

from .apprentissage import alimenter_depuis_journal
from .core import Side
from .engine import TradingEngine
from .risk import RiskManager
from .scanner import Scanner
from .state import StateStore, TradeJournal
from .universe import Instrument, Universe
from .brokers.ibkr import IBKRBroker

logger = logging.getLogger(__name__)

FX = {
    "EURUSD","GBPUSD","USDJPY","AUDUSD","USDCAD","USDCHF","NZDUSD",
    "EURGBP","EURJPY","EURCHF","EURAUD","EURCAD","EURNZD","GBPJPY",
    "GBPAUD","GBPCAD","GBPNZD","AUDJPY","AUDCAD","AUDCHF","AUDNZD",
    "CADJPY","CADCHF","CHFJPY","NZDJPY","NZDCAD","NZDCHF","USDSGD",
    "USDNOK","USDSEK","USDHKD","EURPLN","EURHUF","USDPLN","USDHUF",
}


def _specs(symbols: list[str]) -> dict[str, dict]:
    out = {}
    for s in symbols:
        s = s.upper()
        if s in FX:
            out[s] = {
                "secType": "CASH", "pair": s, "exchange": "IDEALPRO",
                "currency": s[3:], "contract_size": 1.0,
                "min_lot": 1000.0, "lot_step": 1000.0,
            }
        else:
            out[s] = {
                "secType": "STK", "symbol": s, "exchange": "SMART",
                "currency": "USD", "contract_size": 1.0,
                "min_lot": 0.001, "lot_step": 0.001,
            }
    return out


def _instruments(symbols: list[str]) -> list[Instrument]:
    items = []
    for s in symbols:
        s = s.upper()
        if s in FX:
            items.append(Instrument(
                s, "forex", 5 if "JPY" not in s else 3, 1.0,
                1000.0, 1000.0, 50_000_000.0, 0.0,
                0.00008 if "JPY" not in s else 0.008,
                0.00040 if "JPY" not in s else 0.040,
                priority=1.0, quote_currency=s[3:],
                correlation_group="fx_usd" if "USD" in s else "fx_cross",
            ))
        else:
            items.append(Instrument(
                s, "stock", 2, 1.0, 0.001, 0.001, 1_000_000.0,
                0.0, 0.01, 0.05, sessions=((13, 21),),
                priority=0.8, quote_currency="USD", correlation_group="stocks",
            ))
    return items


class DualScalpingEngine(TradingEngine):
    """Moteur dual dédié au petit capital.

    Bitvavo et IBKR ont des profils distincts. Ici le calibrage financier
    n'autorise jamais le vieux fallback M5 -> H1 : la fréquence est une
    contrainte du produit demandé, pas une conséquence arbitraire du capital.
    """

    def __init__(self, config=None, notifier=None):
        cfg = config
        if cfg is None:
            from .settings import BotConfig
            cfg = BotConfig.load()
        requested = cfg.engine.broker
        if requested == "ibkr":
            # settings.py de cette branche ne connait pas encore ibkr dans
            # validate(); on laisse le constructeur de base préparer les
            # modules puis on remplace uniquement le lieu d'exécution.
            cfg.engine.broker = "paper"
            super().__init__(cfg, notifier=notifier)
            cfg.engine.broker = "ibkr"
            symbols = [s.upper() for s in cfg.engine.symbols]
            os.environ["IBKR_CONTRACTS"] = json.dumps(_specs(symbols), separators=(",", ":"))
            self.broker = IBKRBroker()
            self.universe = Universe(_instruments(symbols))
            self.scanner = Scanner(
                self.registry, self.universe, self.strategy, self.news,
                cfg.strategy.history, max_workers=cfg.engine.scan_workers,
            )
            for inst in self.universe:
                try:
                    self.broker.register_instrument(inst)
                except Exception as exc:
                    logger.debug("contrat IBKR %s non resolu au preflight: %s", inst.symbol, str(exc)[:100])
            self.store = StateStore(instance="ibkr")
            self.journal = TradeJournal(instance="ibkr")
            alimenter_depuis_journal(self.poids, self.journal.path)
        else:
            super().__init__(cfg, notifier=notifier)
            # Même catalogue dynamique côté Bitvavo : le broker garde le
            # filtrage réel et les règles de marché de la plateforme.

        self.config.engine.broker = requested
        self._micro_profile()

    def _micro_profile(self) -> None:
        cfg = self.config
        # Aucun changement de timeframe automatique par le calibrage de base.
        # Les frais doivent être couverts par le mouvement attendu, pas par
        # un passage silencieux en H1.
        if cfg.engine.broker == "bitvavo":
            cfg.strategy.entry_tf = "M5"
            cfg.strategy.trigger_tf = "M5"
            cfg.strategy.context_tf = "M15"
            cfg.strategy.bias_tf = "H1"
            cfg.strategy.min_confirmations = 2
            cfg.strategy.min_score = 0.32
            cfg.strategy.min_rr = 1.35
            cfg.risk.max_positions = 6
            cfg.risk.max_capital_engaged_pct = 80.0
            cfg.risk.max_total_risk_pct = 3.0
            cfg.trade.time_stop_minutes = 45.0
        else:
            cfg.strategy.entry_tf = "M5"
            cfg.strategy.trigger_tf = "M5"
            cfg.strategy.context_tf = "M15"
            cfg.strategy.bias_tf = "H1"
            cfg.strategy.min_confirmations = 2
            cfg.strategy.min_score = 0.30
            cfg.strategy.min_rr = 1.30
            cfg.risk.max_positions = 6
            cfg.risk.max_capital_engaged_pct = 70.0
            cfg.risk.max_total_risk_pct = 2.5
            cfg.trade.time_stop_minutes = 40.0
        self.strategy.config = cfg.strategy
        self.trade_manager.config = cfg.trade
        self.risk.config = cfg.risk

    def _calibrer_sur_le_capital(self) -> None:
        """Calibrage scalping réel: taille, risque et capacité, sans fallback H1."""
        equity = float(self.broker.account().equity or 0.0)
        if equity <= 0:
            return
        if self.config.engine.broker == "bitvavo":
            ticket = 5.0
            fee = float(getattr(getattr(self.broker, "config", None), "fee_rate", 0.0025) or 0.0025)
            target_stop = 0.009
            max_cost = 0.75
        else:
            ticket = 10.0
            fee = float(self.config.risk.commission_pct or 0.0005)
            target_stop = 0.006
            max_cost = 0.55

        engageable = equity * self.config.risk.max_capital_engaged_pct / 100.0
        capacity = max(1, min(self.config.risk.max_positions, int(engageable // ticket)))
        self._ticket_minimum = ticket
        self.frais_reels = fee
        self.calibrage = type("ScalpCalibration", (), {
            "ticket_minimum": ticket,
            "risk_pct": self.config.risk.base_risk_pct,
            "unites": ("M5", "M15"),
            "unite_conseillee": "M5",
            "viable": equity >= ticket,
            "resume": lambda self: [
                f"capital {equity:.2f}",
                f"ticket minimum cible {ticket:.2f}",
                f"frais cote {fee*100:.3f} %",
                f"stop scalping cible {target_stop*100:.2f} %",
                f"positions simultanees tenables {capacity}",
                f"cout/risque maximum {max_cost*100:.0f} %",
            ],
        })()
        self._promo_en_cours = "micro-scalping"
        logger.info("calibrage scalping: capital %.2f | ticket %.2f | stop cible %.2f%% | positions %d", equity, ticket, target_stop*100, capacity)

    def _look_for_entry(self) -> None:
        """Permet une nouvelle entrée à chaque cycle tant que le risque le permet."""
        positions = self.broker.positions()
        allowed, why = self.risk.can_trade(positions)
        if not allowed:
            logger.debug("entree bloquee: %s", why)
            return
        if len(positions) >= self.config.risk.max_positions:
            return
        result = self.scanner.scan()
        if result.best is None:
            return
        self._execute(result.best)
