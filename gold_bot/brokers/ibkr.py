from __future__ import annotations

import json
import logging
import os
import time
from typing import Optional

from ..core import ClosedTrade, Position, Side
from ..universe import Instrument
from .base import AccountInfo, Broker, BrokerError, new_position_id

logger = logging.getLogger(__name__)
try:
    from ib_async import IB, Forex, Stock, MarketOrder, StopOrder, LimitOrder
except ImportError:  # pragma: no cover
    IB = Forex = Stock = MarketOrder = StopOrder = LimitOrder = None


class IBKRBroker(Broker):
    name = "ibkr"
    is_live = True
    supports_short = True

    def __init__(self) -> None:
        self.host = os.getenv("IBKR_HOST", "127.0.0.1")
        self.port = int(os.getenv("IBKR_PORT", "4001"))
        self.client_id = int(os.getenv("IBKR_CLIENT_ID", "27"))
        self.account_id = os.getenv("IBKR_ACCOUNT", "").strip()
        self.live_enabled = os.getenv("IBKR_TRADING_LIVE", "0").lower() in {"1", "true", "yes", "oui"}
        self.allow_short = os.getenv("IBKR_ALLOW_SHORT", "1").lower() in {"1", "true", "yes", "oui"}
        self.currency = os.getenv("IBKR_CURRENCY", "EUR")
        self.ib = None
        self._contracts: dict[str, object] = {}
        self._positions: dict[str, Position] = {}
        self._closed: list[ClosedTrade] = []
        raw = os.getenv("IBKR_CONTRACTS", "{}")
        try:
            self._specs = {str(k).upper(): dict(v) for k, v in json.loads(raw).items()}
        except Exception as exc:
            raise BrokerError(f"IBKR_CONTRACTS invalide: {exc}") from exc

    def connect(self) -> bool:
        if IB is None:
            raise BrokerError("ib_async absent")
        self.ib = IB()
        try:
            self.ib.connect(self.host, self.port, clientId=self.client_id,
                            readonly=not self.live_enabled, timeout=10)
        except Exception as exc:
            self.ib = None
            raise BrokerError(f"connexion IBKR impossible {self.host}:{self.port}: {exc}") from exc
        accounts = self.ib.managedAccounts()
        if not self.account_id and accounts:
            self.account_id = accounts[0]
        if not self.account_id:
            raise BrokerError("IBKR_ACCOUNT absent et aucun compte detecte")
        if not self.live_enabled:
            logger.warning("IBKR connecte en lecture seule: IBKR_TRADING_LIVE=1 requis pour trader")
        self.sync()
        return True

    def _require(self) -> None:
        if not self.ib or not self.ib.isConnected():
            raise BrokerError("IBKR non connecte")

    def supports(self, symbol: str) -> bool:
        return symbol.upper() in self._specs

    def register_instrument(self, instrument: Instrument) -> None:
        # La resolution coute un appel secdef; elle est donc faite a la
        # premiere utilisation au lieu de bloquer le demarrage de 180 actifs.
        return None

    def _contract(self, symbol: str):
        self._require()
        symbol = symbol.upper()
        if symbol in self._contracts:
            return self._contracts[symbol]
        spec = self._specs.get(symbol)
        if not spec:
            raise BrokerError(f"instrument IBKR non configure: {symbol}")
        if spec.get("secType") == "CASH":
            contract = Forex(spec.get("pair", symbol), exchange=spec.get("exchange", "IDEALPRO"))
        else:
            contract = Stock(spec.get("symbol", symbol), "SMART", spec.get("currency", "USD"))
        details = self.ib.reqContractDetails(contract)
        if not details:
            raise BrokerError(f"contrat IBKR introuvable: {symbol}")
        self._contracts[symbol] = details[0].contract
        return self._contracts[symbol]

    def account(self) -> AccountInfo:
        self._require()
        rows = self.ib.accountSummary(self.account_id)
        vals = {}
        for row in rows:
            cur = getattr(row, "currency", "")
            if cur in {self.currency, "BASE", "EUR"}:
                vals.setdefault(row.tag, row.value)
        def f(name: str) -> float:
            try: return float(vals.get(name, 0.0))
            except (TypeError, ValueError): return 0.0
        equity = f("NetLiquidation")
        balance = f("TotalCashValue") or equity
        used = f("MaintMarginReq")
        free = f("AvailableFunds") or max(0.0, equity - used)
        return AccountInfo(equity, balance, self.currency, used, free, equity / used if used > 0 else 0.0)

    def sync(self) -> None:
        self._require()
        current = {}
        for row in self.ib.positions(account=self.account_id):
            qty = float(row.position)
            if abs(qty) < 1e-12:
                continue
            symbol = str(row.contract.symbol).upper()
            side = Side.BUY if qty > 0 else Side.SELL
            old = self._positions.get(symbol)
            if old:
                current[symbol] = old
            else:
                price = float(getattr(row, "avgCost", 0.0) or 0.0)
                current[symbol] = Position(new_position_id(), symbol, side, abs(qty), price, 0.0, 0.0, time.time(), comment="reprise IBKR")
        self._positions = current

    def positions(self) -> list[Position]:
        self.sync()
        return list(self._positions.values())

    def _qty(self, instrument: Instrument, lots: float) -> float:
        return instrument.normalize_lot(lots, round_down=True)

    def open_position(self, instrument: Instrument, side: Side, lots: float,
                      stop_loss: float, take_profit: float, comment: str = "") -> Position:
        self._require()
        if not self.live_enabled:
            raise BrokerError("IBKR_TRADING_LIVE=0: ordre bloque")
        if side is Side.SELL and not self.allow_short:
            raise BrokerError("IBKR_ALLOW_SHORT=0")
        qty = self._qty(instrument, lots)
        if qty <= 0:
            raise BrokerError("quantite IBKR nulle")
        acc = self.account()
        if acc.margin_free <= 0:
            raise BrokerError(f"fonds/marge disponibles insuffisants: {acc.margin_free:.2f} {acc.currency}")
        contract = self._contract(instrument.symbol)
        action = "BUY" if side is Side.BUY else "SELL"
        order = MarketOrder(action, qty)
        order.account = self.account_id
        trade = self.ib.placeOrder(contract, order)
        self.ib.sleep(0.6)
        status = str(getattr(trade.orderStatus, "status", ""))
        fill = next((f for f in trade.fills if float(getattr(f.execution, "shares", 0.0)) > 0), None)
        entry = float(fill.execution.avgPrice if fill else getattr(trade.orderStatus, "avgFillPrice", 0.0) or 0.0)
        if entry <= 0 or status in {"Cancelled", "ApiCancelled", "Inactive"}:
            raise BrokerError(f"ordre IBKR non execute: {status}")
        pos = Position(new_position_id(), instrument.symbol, side, qty, entry,
                       stop_loss, take_profit, time.time(), broker_ref=str(trade.order.orderId), comment=comment)
        self._positions[instrument.symbol] = pos
        self._protect(contract, pos)
        return pos

    def _protect(self, contract, pos: Position) -> None:
        if pos.stop_loss > 0:
            order = StopOrder("SELL" if pos.side is Side.BUY else "BUY", pos.volume, pos.stop_loss)
            order.account = self.account_id
            order.orderRef = f"GB-SL-{pos.id}"
            self.ib.placeOrder(contract, order)
        if pos.take_profit > 0:
            order = LimitOrder("SELL" if pos.side is Side.BUY else "BUY", pos.volume, pos.take_profit)
            order.account = self.account_id
            order.orderRef = f"GB-TP-{pos.id}"
            self.ib.placeOrder(contract, order)

    def modify_position(self, position_id: str, stop_loss: Optional[float] = None,
                        take_profit: Optional[float] = None) -> bool:
        pos = next((p for p in self._positions.values() if p.id == position_id), None)
        if not pos:
            return False
        if stop_loss is not None: pos.stop_loss = float(stop_loss)
        if take_profit is not None: pos.take_profit = float(take_profit)
        return True

    def close_position(self, position_id: str, volume: Optional[float] = None,
                       reason: str = "") -> Optional[ClosedTrade]:
        self._require()
        pos = next((p for p in self._positions.values() if p.id == position_id), None)
        if not pos:
            return None
        qty = min(pos.volume, float(volume)) if volume else pos.volume
        contract = self._contract(pos.symbol)
        order = MarketOrder("SELL" if pos.side is Side.BUY else "BUY", qty)
        order.account = self.account_id
        trade = self.ib.placeOrder(contract, order)
        self.ib.sleep(0.6)
        fill = next((f for f in trade.fills if float(getattr(f.execution, "shares", 0.0)) > 0), None)
        exit_price = float(fill.execution.avgPrice if fill else getattr(trade.orderStatus, "avgFillPrice", 0.0) or 0.0)
        if exit_price <= 0:
            raise BrokerError("fermeture IBKR sans prix d'execution")
        profit = pos.side.sign * (exit_price - pos.entry_price) * qty
        closed = ClosedTrade(pos.id, pos.symbol, pos.side, qty, pos.entry_price,
                             exit_price, pos.opened_at, time.time(), profit,
                             pos.r_multiple(exit_price), reason or "fermeture IBKR")
        if qty >= pos.volume - 1e-12:
            self._positions.pop(pos.symbol, None)
        else:
            pos.volume -= qty
        self._closed.append(closed)
        return closed

    def closed_trades(self) -> list[ClosedTrade]:
        out, self._closed = self._closed, []
        return out

    def healthy(self) -> bool:
        return bool(self.ib and self.ib.isConnected())
