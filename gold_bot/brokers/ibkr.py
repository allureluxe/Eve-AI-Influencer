"""IBKR execution adapter.

Retail IBKR accounts use TWS/IB Gateway authentication rather than exchange-style
API keys. The adapter therefore connects to an already authenticated IB Gateway
socket. Credentials stay outside the repository.

The broker is deliberately defensive: live orders require IBKR_TRADING_LIVE=1,
contract details must resolve, and the account's real available funds/margin are
checked before an order is submitted.
"""
from __future__ import annotations

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
except ImportError:
    IB = None
    Forex = Stock = MarketOrder = StopOrder = LimitOrder = None


class IBKRBroker(Broker):
    """IB Gateway/TWS execution adapter with real long/short support."""
    name = "ibkr"
    is_live = True
    supports_short = True

    def __init__(self) -> None:
        self.host = os.getenv("IBKR_HOST", "127.0.0.1")
        self.port = int(os.getenv("IBKR_PORT", "4002"))
        self.client_id = int(os.getenv("IBKR_CLIENT_ID", "27"))
        self.account_id = os.getenv("IBKR_ACCOUNT", "").strip()
        self.live_enabled = os.getenv("IBKR_TRADING_LIVE", "0").strip().lower() in {"1", "true", "yes", "oui"}
        self.allow_short = os.getenv("IBKR_ALLOW_SHORT", "1").strip().lower() in {"1", "true", "yes", "oui"}
        self.currency = os.getenv("IBKR_CURRENCY", "EUR")
        self.ib = None
        self._positions: dict[str, Position] = {}
        self._closed: list[ClosedTrade] = []
        self._contracts: dict[str, object] = {}
        self._contract_specs = self._load_specs()

    @staticmethod
    def _load_specs() -> dict[str, dict]:
        import json
        defaults = {
            "EURUSD": {"secType": "CASH", "pair": "EURUSD", "exchange": "IDEALPRO", "currency": "USD", "contract_size": 1.0, "min_lot": 1000.0, "lot_step": 1000.0},
            "GBPUSD": {"secType": "CASH", "pair": "GBPUSD", "exchange": "IDEALPRO", "currency": "USD", "contract_size": 1.0, "min_lot": 1000.0, "lot_step": 1000.0},
            "USDJPY": {"secType": "CASH", "pair": "USDJPY", "exchange": "IDEALPRO", "currency": "JPY", "contract_size": 1.0, "min_lot": 1000.0, "lot_step": 1000.0},
            "AUDUSD": {"secType": "CASH", "pair": "AUDUSD", "exchange": "IDEALPRO", "currency": "USD", "contract_size": 1.0, "min_lot": 1000.0, "lot_step": 1000.0},
            "USDCAD": {"secType": "CASH", "pair": "USDCAD", "exchange": "IDEALPRO", "currency": "CAD", "contract_size": 1.0, "min_lot": 1000.0, "lot_step": 1000.0},
        }
        raw = os.getenv("IBKR_CONTRACTS", "").strip()
        if raw:
            try:
                data = json.loads(raw)
                defaults.update({str(k).upper(): dict(v) for k, v in data.items() if isinstance(v, dict)})
            except Exception as exc:
                raise BrokerError(f"IBKR_CONTRACTS invalide: {exc}") from exc
        return defaults

    def connect(self) -> bool:
        if IB is None:
            raise BrokerError("dependance IBKR absente: installez ib_async")
        if not self.live_enabled:
            logger.warning("IBKR present mais trading reel DESARME (IBKR_TRADING_LIVE=0)")
        self.ib = IB()
        try:
            self.ib.connect(self.host, self.port, clientId=self.client_id, readonly=not self.live_enabled, timeout=8)
        except Exception as exc:
            self.ib = None
            raise BrokerError(f"connexion IBKR impossible {self.host}:{self.port}: {exc}") from exc
        if not self.account_id:
            accounts = self.ib.managedAccounts()
            if accounts:
                self.account_id = accounts[0]
        if not self.account_id:
            raise BrokerError("IBKR_ACCOUNT absent et aucun compte retourne par Gateway")
        self.sync()
        return True

    def _require(self) -> None:
        if self.ib is None or not self.ib.isConnected():
            raise BrokerError("IBKR non connecte")

    def _contract(self, instrument: Instrument):
        self._require()
        sym = instrument.symbol.upper()
        if sym in self._contracts:
            return self._contracts[sym]
        spec = self._contract_specs.get(sym, {})
        sec_type = str(spec.get("secType", "CASH" if instrument.asset_class == "forex" else "STK")).upper()
        if sec_type == "CASH":
            pair = spec.get("pair") or sym
            contract = Forex(pair, exchange=spec.get("exchange", "IDEALPRO"))
        elif sec_type == "STK":
            contract = Stock(spec.get("symbol", sym), spec.get("exchange", "SMART"), spec.get("currency", instrument.quote_currency or self.currency), primaryExchange=spec.get("primaryExchange", ""))
        else:
            raise BrokerError(f"type de contrat IBKR non pris en charge pour {sym}: {sec_type}")
        details = self.ib.reqContractDetails(contract)
        if not details:
            raise BrokerError(f"contrat IBKR introuvable: {sym}")
        self._contracts[sym] = details[0].contract
        return self._contracts[sym]

    def supports(self, symbol: str) -> bool:
        return symbol.upper() in self._contract_specs

    def register_instrument(self, instrument: Instrument) -> None:
        if self.supports(instrument.symbol):
            try:
                self._contract(instrument)
            except Exception as exc:
                logger.warning("IBKR contrat %s indisponible: %s", instrument.symbol, str(exc)[:120])

    def account(self) -> AccountInfo:
        self._require()
        summary = self.ib.accountSummary(self.account_id)
        vals = {x.tag: x.value for x in summary if getattr(x, "currency", "") in {self.currency, "BASE", "EUR"}}
        def num(key: str) -> float:
            try: return float(vals.get(key, 0.0))
            except (TypeError, ValueError): return 0.0
        equity = num("NetLiquidation")
        balance = num("TotalCashValue") or equity
        margin_used = num("MaintMarginReq")
        margin_free = num("AvailableFunds") or max(0.0, equity - margin_used)
        return AccountInfo(equity=equity, balance=balance, currency=self.currency, margin_used=margin_used, margin_free=margin_free, leverage=(equity / margin_used if margin_used > 0 else 0.0))

    def positions(self) -> list[Position]:
        self.sync()
        return list(self._positions.values())

    def sync(self) -> None:
        self._require()
        live = {}
        for p in self.ib.positions(account=self.account_id):
            qty = float(p.position)
            if abs(qty) < 1e-12:
                continue
            symbol = getattr(p.contract, "symbol", "").upper()
            side = Side.BUY if qty > 0 else Side.SELL
            existing = self._positions.get(symbol)
            if existing:
                live[symbol] = existing
                continue
            price = float(getattr(p, "avgCost", 0.0) or 0.0)
            live[symbol] = Position(new_position_id(), symbol, side, abs(qty), price, 0.0, 0.0, time.time(), comment="reprise IBKR")
        self._positions = live

    def _margin_check(self, contract, action: str, quantity: float) -> None:
        acc = self.account()
        if quantity <= 0:
            raise BrokerError("quantite IBKR nulle")
        if acc.margin_free <= 0:
            raise BrokerError(f"marge disponible insuffisante: {acc.margin_free:.2f} {acc.currency}")

    def open_position(self, instrument: Instrument, side: Side, lots: float, stop_loss: float, take_profit: float, comment: str = "") -> Position:
        self._require()
        if side is Side.SELL and not self.allow_short:
            raise BrokerError("short IBKR desactive par IBKR_ALLOW_SHORT=0")
        if not self.live_enabled:
            raise BrokerError("ordre IBKR bloque: IBKR_TRADING_LIVE=0")
        contract = self._contract(instrument)
        qty = instrument.normalize_lot(lots, round_down=True)
        if qty <= 0:
            raise BrokerError("volume IBKR invalide")
        action = "BUY" if side is Side.BUY else "SELL"
        self._margin_check(contract, action, qty)
        order = MarketOrder(action, qty)
        order.account = self.account_id
        trade = self.ib.placeOrder(contract, order)
        self.ib.sleep(0.5)
        status = str(getattr(trade.orderStatus, "status", ""))
        if status in {"Cancelled", "ApiCancelled", "Inactive"}:
            raise BrokerError(f"ordre IBKR refuse: {status} {getattr(trade.orderStatus, 'whyHeld', '')}")
        fill = next((f for f in trade.fills if float(getattr(f.execution, "shares", 0)) > 0), None)
        entry = float(fill.execution.avgPrice if fill else getattr(trade.orderStatus, "avgFillPrice", 0.0))
        if entry <= 0:
            raise BrokerError(f"IBKR ordre sans execution: {status}")
        pid = str(trade.order.orderId)
        pos = Position(pid, instrument.symbol, side, qty, entry, stop_loss, take_profit, time.time(), broker_ref=str(trade.order.orderId), comment=comment)
        self._positions[instrument.symbol] = pos
        self._place_protection(contract, pos)
        return pos

    def _place_protection(self, contract, pos: Position) -> None:
        if pos.stop_loss and pos.stop_loss > 0:
            stop_action = "SELL" if pos.side is Side.BUY else "BUY"
            stop = StopOrder(stop_action, pos.volume, pos.stop_loss)
            stop.account = self.account_id
            stop.orderRef = f"GB-SL-{pos.id}"
            self.ib.placeOrder(contract, stop)
        if pos.take_profit and pos.take_profit > 0:
            tp_action = "SELL" if pos.side is Side.BUY else "BUY"
            tp = LimitOrder(tp_action, pos.volume, pos.take_profit)
            tp.account = self.account_id
            tp.orderRef = f"GB-TP-{pos.id}"
            self.ib.placeOrder(contract, tp)

    def modify_position(self, position_id: str, stop_loss: Optional[float] = None, take_profit: Optional[float] = None) -> bool:
        self._require()
        pos = next((p for p in self._positions.values() if p.id == position_id), None)
        if not pos:
            return False
        if stop_loss is not None: pos.stop_loss = float(stop_loss)
        if take_profit is not None: pos.take_profit = float(take_profit)
        return True

    def close_position(self, position_id: str, volume: Optional[float] = None, reason: str = "") -> Optional[ClosedTrade]:
        self._require()
        pos = next((p for p in self._positions.values() if p.id == position_id), None)
        if not pos:
            return None
        qty = min(pos.volume, float(volume)) if volume else pos.volume
        ib_contract = self._contracts.get(pos.symbol) or self._contract_from_symbol(pos.symbol)
        action = "SELL" if pos.side is Side.BUY else "BUY"
        order = MarketOrder(action, qty)
        order.account = self.account_id
        trade = self.ib.placeOrder(ib_contract, order)
        self.ib.sleep(0.5)
        fill = next((f for f in trade.fills if float(getattr(f.execution, "shares", 0)) > 0), None)
        exit_price = float(fill.execution.avgPrice if fill else getattr(trade.orderStatus, "avgFillPrice", 0.0))
        if exit_price <= 0:
            raise BrokerError("fermeture IBKR sans execution")
        profit = pos.side.sign * (exit_price - pos.entry_price) * qty * self._contract_size(pos.symbol)
        closed = ClosedTrade(pos.id, pos.symbol, pos.side, qty, pos.entry_price, exit_price, pos.opened_at, time.time(), profit, pos.r_multiple(exit_price), reason or "fermeture IBKR")
        if qty >= pos.volume - 1e-12: self._positions.pop(pos.symbol, None)
        else: pos.volume -= qty
        self._closed.append(closed)
        return closed

    def _contract_from_symbol(self, symbol: str):
        spec = self._contract_specs.get(symbol, {})
        if str(spec.get("secType", "STK")).upper() == "CASH":
            c = Forex(spec.get("pair", symbol), exchange=spec.get("exchange", "IDEALPRO"))
        else:
            c = Stock(spec.get("symbol", symbol), spec.get("exchange", "SMART"), spec.get("currency", "USD"), primaryExchange=spec.get("primaryExchange", ""))
        details = self.ib.reqContractDetails(c)
        if not details: raise BrokerError(f"contrat IBKR introuvable: {symbol}")
        self._contracts[symbol] = details[0].contract
        return self._contracts[symbol]

    def _contract_size(self, symbol: str) -> float:
        try: return float(self._contract_specs.get(symbol, {}).get("contract_size", 1.0))
        except (TypeError, ValueError): return 1.0

    def closed_trades(self) -> list[ClosedTrade]:
        out, self._closed = self._closed, []
        return out

    def healthy(self) -> bool:
        return bool(self.ib and self.ib.isConnected())
