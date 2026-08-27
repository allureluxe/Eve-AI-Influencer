"""Bitvavo Margin / Leveraged Account execution.

This broker is deliberately opt-in and refuses to trade unless the Bitvavo
account exposes the private leveraged-account endpoints. Bitvavo documents
margin positions through /positions and account health/net liquidation through
/netLiquidation; regular /order remains the trading endpoint.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Optional

from ..core import ClosedTrade, Position, Side
from ..universe import Instrument
from .base import AccountInfo, BrokerError
from .bitvavo import BitvavoBroker, BitvavoConfig, ACTIFS, formater

logger = logging.getLogger(__name__)


class BitvavoMarginBroker(BitvavoBroker):
    """Bitvavo leveraged-account broker: long + short, capped at configured leverage."""

    name = "bitvavo-margin"
    supports_short = True

    def __init__(self, config: Optional[BitvavoConfig] = None) -> None:
        super().__init__(config)
        self.margin_enabled = os.getenv("BITVAVO_MARGIN_ENABLED", "1").strip().lower() not in (
            "0", "false", "no", "off"
        )
        self.max_margin_leverage = min(
            10.0, max(1.0, float(os.getenv("BITVAVO_MARGIN_LEVERAGE", "10") or 10))
        )
        self._margin_positions: dict[str, dict] = {}
        self._margin_ratio = 0.0
        self._adjusted_net_liquidation = 0.0

    @property
    def mode(self) -> str:
        return "simulation (margin dry-run)" if self.config.dry_run else f"REEL MARGE {self.max_margin_leverage:.0f}x"

    def connect(self) -> bool:
        if not self.margin_enabled:
            self._last_error = "BITVAVO_MARGIN_ENABLED=0"
            return False
        if not super().connect():
            return False
        try:
            self._refresh_margin_account()
            logger.info(
                "Bitvavo marge activee: compte leveraged OK — levier logiciel max %.1fx — ratio marge %.3f",
                self.max_margin_leverage, self._margin_ratio,
            )
            return True
        except Exception as exc:  # noqa: BLE001
            self._last_error = (
                "compte Bitvavo leveraged/margin indisponible ou non autorise: "
                + str(exc)[:220]
            )
            logger.error("%s", self._last_error)
            return False

    def _refresh_margin_account(self) -> None:
        data = self._appel("GET", "/netLiquidation")
        if not isinstance(data, dict):
            raise BrokerError("reponse /netLiquidation invalide")
        net = data.get("netLiquidation") or {}
        adjusted = data.get("adjustedNetLiquidation") or net
        self._margin_ratio = float(data.get("marginRatio", 0) or 0)
        self._adjusted_net_liquidation = float(adjusted.get("value", 0) or 0)
        if self._adjusted_net_liquidation <= 0:
            raise BrokerError("net liquidation ajuste nul")
        minimum = data.get("minimumNetLiquidation") or {}
        minimum_value = float(minimum.get("value", 0) or 0)
        if minimum_value and self._adjusted_net_liquidation < minimum_value:
            raise BrokerError(
                f"net liquidation {self._adjusted_net_liquidation:.2f} sous le minimum "
                f"Bitvavo {minimum_value:.2f} pour le compte leveraged"
            )
        if self._margin_ratio and self._margin_ratio <= 1.0:
            raise BrokerError(f"health/margin ratio dangereux: {self._margin_ratio:.3f}")
        positions = self._appel("GET", "/positions")
        self._margin_positions = {
            str(row.get("symbol", "")).upper(): row
            for row in (positions.get("assets", []) if isinstance(positions, dict) else [])
            if float(row.get("position", 0) or 0) != 0
        }

    def sync(self) -> None:
        self._refresh_margin_account()
        equity = self._adjusted_net_liquidation
        # AccountInfo.margin_free is used by the risk layer as an execution
        # budget. We expose only the configured leverage budget, reduced by
        # the already tracked local notionals; the hard risk percentage and
        # max_leverage checks remain authoritative.
        used = 0.0
        for position in self._positions.values():
            price = self._prix(self.symbol_for(position.symbol)) or position.entry_price
            used += abs(position.volume * price)
        margin_free = max(0.0, equity * self.max_margin_leverage - used)
        self._account = AccountInfo(
            equity=equity,
            balance=equity,
            currency=self.config.quote_asset,
            margin_used=used / self.max_margin_leverage,
            margin_free=margin_free,
            leverage=self.max_margin_leverage,
        )
        self._last_error = ""

    def account(self) -> AccountInfo:
        return self._account

    def open_position(self, instrument: Instrument, side: Side, lots: float,
                      stop_loss: float, take_profit: float, comment: str = "") -> Position:
        if not stop_loss:
            raise BrokerError("ouverture refusee: stop-loss obligatoire")
        code = self.symbol_for(instrument.symbol)
        regle = self.regle(instrument.symbol)
        quantite = regle.arrondir_quantite(lots)
        if quantite <= 0 or (regle.min_amount and quantite < regle.min_amount):
            raise BrokerError(f"quantite sous le minimum sur {code}")
        reference = self._prix(code) or (stop_loss + take_profit) / 2.0
        notionnel = quantite * reference
        if notionnel <= 0:
            raise BrokerError(f"notionnel invalide sur {code}")
        if self._account.margin_free > 0 and notionnel > self._account.margin_free * 0.995:
            raise BrokerError(
                f"notionnel {notionnel:.2f} au-dela du budget marge libre "
                f"{self._account.margin_free:.2f} {self.config.quote_asset}"
            )
        if self.config.dry_run:
            reponse = {
                "filledAmount": formater(quantite),
                "filledAmountQuote": formater(notionnel),
                "orderId": "",
            }
        else:
            reponse = self._appel("POST", "/order", corps={
                "market": code,
                "side": "buy" if side is Side.BUY else "sell",
                "orderType": "market",
                "amount": formater(quantite, regle.amount_decimals),
                "operatorId": self.config.operator_id,
            })
        rempli = self._prix_moyen(reponse) or reference
        obtenu = float(reponse.get("filledAmount", quantite) or quantite)
        position = Position(
            id=instrument.symbol,
            symbol=instrument.symbol,
            side=side,
            volume=obtenu,
            entry_price=regle.arrondir_prix(rempli),
            stop_loss=regle.arrondir_prix(stop_loss),
            take_profit=regle.arrondir_prix(take_profit),
            opened_at=time.time(),
            broker_ref=str(reponse.get("orderId", "")),
            comment=comment,
        )
        self._positions[instrument.symbol] = position
        self._instruments[instrument.symbol] = instrument
        frais_entree = self._frais_reels(reponse)
        self._frais_entree[position.id] = (
            frais_entree if frais_entree is not None
            else position.entry_price * obtenu * self.config.fee_rate
        )
        self._poser_margin_stop(position)
        logger.info(
            "%s [%s] %s %s @ %s | SL %s TP %s",
            "ACHAT" if side is Side.BUY else "VENTE SHORT",
            self.mode, code, formater(obtenu), formater(position.entry_price),
            formater(position.stop_loss), formater(position.take_profit),
        )
        return position

    def _poser_margin_stop(self, position: Position) -> None:
        """Place a protective trigger in the opposite direction of the position."""
        if self.config.dry_run:
            return
        code = self.symbol_for(position.symbol)
        regle = self.regle(position.symbol)
        trigger = regle.arrondir_prix(position.stop_loss)
        if trigger <= 0:
            raise BrokerError("stop invalide")
        current = self._prix(code)
        if current is not None:
            if position.side is Side.BUY and current <= trigger:
                raise BrokerError(f"stop deja atteint sur {code}")
            if position.side is Side.SELL and current >= trigger:
                raise BrokerError(f"stop deja atteint sur {code}")
        quantite = regle.arrondir_quantite(position.volume)
        limit = regle.arrondir_prix(trigger * (0.998 if position.side is Side.BUY else 1.002))
        response = self._appel("POST", "/order", corps={
            "market": code,
            "side": "sell" if position.side is Side.BUY else "buy",
            "orderType": "stopLossLimit",
            "operatorId": self.config.operator_id,
            "amount": formater(quantite, regle.amount_decimals),
            "price": formater(limit),
            "triggerType": "price",
            "triggerReference": "lastTrade",
            "triggerAmount": formater(trigger),
        })
        self._stops[position.symbol] = str(response.get("orderId", ""))
        self._stop_pose[position.symbol] = trigger

    def close_position(self, position_id: str, volume: Optional[float] = None,
                       reason: str = "") -> Optional[ClosedTrade]:
        position = self._positions.get(position_id)
        if position is None:
            return None
        code = self.symbol_for(position.symbol)
        regle = self.regle(position.symbol)
        quantite = regle.arrondir_quantite(min(volume or position.volume, position.volume))
        if quantite <= 0:
            return None
        self._annuler_stop(position.symbol)
        if self.config.dry_run:
            price = self._prix(code) or position.entry_price
            reponse = {"filledAmount": formater(quantite), "filledAmountQuote": formater(quantite * price)}
        else:
            reponse = self._appel("POST", "/order", corps={
                "market": code,
                "side": "sell" if position.side is Side.BUY else "buy",
                "orderType": "market",
                "amount": formater(quantite, regle.amount_decimals),
                "operatorId": self.config.operator_id,
            })
        exit_price = self._prix_moyen(reponse) or self._prix(code) or position.entry_price
        fee = self._frais_reels(reponse)
        if fee is None:
            fee = exit_price * quantite * self.config.fee_rate
        entry_fee = self._part_des_frais_d_entree(position, quantite)
        pnl_gross = (exit_price - position.entry_price) * quantite * position.side.sign
        trade = ClosedTrade(
            position_id=position.id,
            symbol=position.symbol,
            side=position.side,
            volume=quantite,
            entry_price=position.entry_price,
            exit_price=regle.arrondir_prix(exit_price),
            opened_at=position.opened_at,
            closed_at=time.time(),
            profit=round(pnl_gross - entry_fee - fee, 6),
            r_multiple=round(position.r_multiple(exit_price), 3),
            reason=reason,
            tp_extensions=position.tp_extensions,
            max_favorable_r=round(position.r_multiple(position.max_favorable), 3),
            partial=quantite < position.volume - 1e-12,
        )
        self._closed.append(trade)
        if quantite >= position.volume - 1e-12:
            self._positions.pop(position.id, None)
            self._frais_entree.pop(position.id, None)
        else:
            position.volume = regle.arrondir_quantite(position.volume - quantite)
        logger.info("FERMETURE MARGE %s %s -> %s | %+0.4f %s | %s",
                    code, formater(quantite), formater(exit_price), trade.profit,
                    self.config.quote_asset, reason or "sans raison")
        return trade
