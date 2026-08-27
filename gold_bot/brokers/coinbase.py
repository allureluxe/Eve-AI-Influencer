"""Coinbase Advanced Trade spot broker.

Credentials stay in environment variables. JWTs are generated per REST request
using Coinbase's official Python SDK. Exit protection uses Coinbase linked
bracket orders so TP and SL are mutually exclusive on the exchange.
"""
from __future__ import annotations
import logging, os, time, uuid
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from typing import Any, Optional
import requests
from ..core import ClosedTrade, Position, Side
from ..universe import Instrument
from .base import AccountInfo, Broker, BrokerError

logger = logging.getLogger(__name__)
BASE = "https://api.coinbase.com/api/v3/brokerage"

@dataclass(slots=True)
class CoinbaseConfig:
    api_key: str = ""
    api_secret: str = ""
    quote_asset: str = "USD"
    timeout: float = 15.0
    dry_run: bool = True
    request_retries: int = 2
    @classmethod
    def from_env(cls) -> "CoinbaseConfig":
        return cls(
            api_key=(os.getenv("COINBASE_API_KEY") or os.getenv("COINBASE_KEY_NAME") or "").strip(),
            api_secret=(os.getenv("COINBASE_API_SECRET") or os.getenv("COINBASE_PRIVATE_KEY") or "").replace("\\n", "\n").strip(),
            quote_asset=(os.getenv("COINBASE_QUOTE_ASSET", "USD") or "USD").upper(),
            timeout=float(os.getenv("COINBASE_TIMEOUT", "15") or 15),
            dry_run=os.getenv("COINBASE_DRY_RUN", "1").strip().lower() not in {"0", "false", "no"},
            request_retries=max(0, int(os.getenv("COINBASE_REQUEST_RETRIES", "2") or 2)),
        )

@dataclass(slots=True)
class CoinbaseProductRule:
    product_id: str
    base_increment: Decimal = Decimal("0.00000001")
    quote_increment: Decimal = Decimal("0.01")
    base_min: Decimal = Decimal("0")
    quote_min: Decimal = Decimal("1")
    trading_disabled: bool = False
    def amount(self, value: float) -> str:
        return format(Decimal(str(max(0.0, value))).quantize(self.base_increment, rounding=ROUND_DOWN), "f")
    def price(self, value: float) -> str:
        return format(Decimal(str(max(0.0, value))).quantize(self.quote_increment, rounding=ROUND_DOWN), "f")

class CoinbaseBroker(Broker):
    name = "coinbase"
    is_live = True
    supports_short = False
    def __init__(self, config: Optional[CoinbaseConfig] = None) -> None:
        self.config = config or CoinbaseConfig.from_env()
        self._session = requests.Session()
        self._rules: dict[str, CoinbaseProductRule] = {}
        self._positions: dict[str, Position] = {}
        self._closed: list[ClosedTrade] = []
        self._orders: dict[str, dict[str, Any]] = {}
        self._instruments: dict[str, Instrument] = {}
        self._account = AccountInfo(0.0, 0.0, self.config.quote_asset)
        self._last_error = ""
    @property
    def mode(self) -> str:
        return "simulation (dry-run)" if self.config.dry_run else "REEL"
    def register_instrument(self, instrument: Instrument) -> None:
        self._instruments[instrument.symbol] = instrument
    @staticmethod
    def product_id(symbol: str, quote: str) -> str:
        s = symbol.upper().replace("/", "-")
        return s if "-" in s else (f"{s[:-len(quote)]}-{quote}" if s.endswith(quote) else f"{s}-{quote}")
    def _jwt(self, method: str, path: str) -> str:
        try:
            from coinbase import jwt_generator
            uri = jwt_generator.format_jwt_uri(method.upper(), path)
            return jwt_generator.build_rest_jwt(uri, self.config.api_key, self.config.api_secret)
        except Exception as exc:
            raise BrokerError(f"JWT Coinbase invalide: {exc}") from exc
    def _request(self, method: str, path: str, *, params: Optional[dict] = None, body: Optional[dict] = None, auth: bool = True) -> dict[str, Any]:
        last: Optional[Exception] = None
        for attempt in range(self.config.request_retries + 1):
            try:
                headers = {"Accept": "application/json", "Content-Type": "application/json"}
                if auth: headers["Authorization"] = f"Bearer {self._jwt(method, path)}"
                r = self._session.request(method, BASE + path, params=params, json=body, headers=headers, timeout=self.config.timeout)
                if r.status_code in {429, 500, 502, 503, 504} and attempt < self.config.request_retries:
                    time.sleep(0.5 * (attempt + 1)); continue
                if not r.ok: raise BrokerError(f"Coinbase HTTP {r.status_code} {path}: {r.text[:500]}")
                data = r.json()
                if isinstance(data, dict) and data.get("success") is False:
                    raise BrokerError(f"Coinbase {path}: {data.get('error_response', data)}")
                return data
            except requests.RequestException as exc:
                last = exc
                if attempt < self.config.request_retries: time.sleep(0.5 * (attempt + 1)); continue
            except BrokerError: raise
        raise BrokerError(str(last or "Coinbase request failed"))
    def _load_products(self) -> None:
        data = self._request("GET", "/products", params={"limit": 250}, auth=False)
        wanted = {self.product_id(s, self.config.quote_asset) for s in self._instruments}
        for p in data.get("products", []):
            pid = str(p.get("product_id", ""))
            if pid not in wanted and not pid.endswith("-" + self.config.quote_asset): continue
            self._rules[pid] = CoinbaseProductRule(
                pid,
                Decimal(str(p.get("base_increment", "0.00000001") or "0.00000001")),
                Decimal(str(p.get("quote_increment", "0.01") or "0.01")),
                Decimal(str(p.get("base_min_size", "0") or "0")),
                Decimal(str(p.get("quote_min_size", "1") or "1")),
                bool(p.get("trading_disabled", False)),
            )
    def connect(self) -> bool:
        if not self.config.api_key or not self.config.api_secret:
            self._last_error = "COINBASE_API_KEY/COINBASE_API_SECRET absents"; logger.error(self._last_error); return False
        try:
            self._load_products()
            if not self.config.dry_run: self.sync(); logger.warning("Coinbase MODE REEL: argent reel")
            else: logger.info("Coinbase preflight OK [dry-run]")
            self._last_error = ""; return True
        except Exception as exc:
            self._last_error = str(exc); logger.error("preflight Coinbase echoue: %s", str(exc)[:300]); return False
    def healthy(self) -> bool: return not self._last_error
    def _rule(self, symbol: str) -> CoinbaseProductRule:
        pid = self.product_id(symbol, self.config.quote_asset); rule = self._rules.get(pid)
        if rule is None: self._load_products(); rule = self._rules.get(pid)
        if rule is None: raise BrokerError(f"{pid} n'est pas disponible sur Coinbase")
        if rule.trading_disabled: raise BrokerError(f"{pid} trading disabled sur Coinbase")
        return rule
    def account(self) -> AccountInfo: self.sync(); return self._account
    def sync(self) -> None:
        data = self._request("GET", "/accounts", params={"limit": 250})
        quote = 0.0
        for a in data.get("accounts", []):
            if str(a.get("currency", "")).upper() == self.config.quote_asset:
                try: quote = float(a.get("available_balance", {}).get("value", "0"))
                except (TypeError, ValueError): quote = 0.0
        self._account = AccountInfo(quote, quote, self.config.quote_asset, margin_free=quote, leverage=1.0)
    def positions(self) -> list[Position]: return list(self._positions.values())
    def _wait_filled(self, order_id: str) -> dict[str, Any]:
        for _ in range(30):
            order = self._request("GET", f"/orders/historical/{order_id}").get("order", {})
            if str(order.get("status", "")).upper() in {"FILLED", "CANCELLED", "FAILED", "EXPIRED"}: return order
            time.sleep(0.2)
        return self._request("GET", f"/orders/historical/{order_id}").get("order", {})
    def open_position(self, instrument: Instrument, side: Side, lots: float, stop_loss: float, take_profit: float, comment: str = "") -> Position:
        if side is not Side.BUY: raise BrokerError("Coinbase spot ne supporte pas les shorts")
        rule = self._rule(instrument.symbol); size = rule.amount(lots)
        if Decimal(size) < rule.base_min: raise BrokerError(f"quantite {size} sous le minimum Coinbase {rule.base_min}")
        if self.config.dry_run:
            entry = float(self._request("GET", f"/products/{rule.product_id}", auth=False).get("price", 0))
            pos = Position(uuid.uuid4().hex[:12], instrument.symbol, side, float(size), entry, stop_loss, take_profit, time.time(), comment=comment)
            self._positions[pos.id] = pos; return pos
        buy = self._request("POST", "/orders", body={"client_order_id": uuid.uuid4().hex, "product_id": rule.product_id, "side": "BUY", "order_configuration": {"market_market_ioc": {"base_size": size, "rfq_disabled": True}}})
        entry_id = buy.get("success_response", {}).get("order_id") or buy.get("order_id")
        if not entry_id: raise BrokerError(f"Coinbase achat sans order_id: {buy}")
        filled = self._wait_filled(entry_id)
        if str(filled.get("status", "")).upper() != "FILLED": raise BrokerError(f"Coinbase achat non rempli: {filled.get('status')}")
        filled_size = float(filled.get("filled_size") or size); entry = float(filled.get("average_filled_price") or 0)
        if entry <= 0: entry = float(self._request("GET", f"/products/{rule.product_id}", auth=False).get("price", 0))
        bracket = self._request("POST", "/orders", body={"client_order_id": uuid.uuid4().hex, "product_id": rule.product_id, "side": "SELL", "order_configuration": {"trigger_bracket_gtc": {"base_size": rule.amount(filled_size), "limit_price": rule.price(take_profit), "stop_trigger_price": rule.price(stop_loss)}}})
        bracket_id = bracket.get("success_response", {}).get("order_id") or bracket.get("order_id")
        if not bracket_id: raise BrokerError("Achat execute mais bracket TP/SL Coinbase non cree")
        pos = Position(uuid.uuid4().hex[:12], instrument.symbol, side, filled_size, entry, stop_loss, take_profit, time.time(), broker_ref=bracket_id, comment=comment)
        self._positions[pos.id] = pos; self._orders[pos.id] = {"entry": entry_id, "bracket": bracket_id}; return pos
    def modify_position(self, position_id: str, stop_loss: Optional[float] = None, take_profit: Optional[float] = None) -> bool:
        pos = self._positions.get(position_id)
        if not pos: return False
        new_sl = pos.stop_loss if stop_loss is None else stop_loss; new_tp = pos.take_profit if take_profit is None else take_profit
        if self.config.dry_run: pos.stop_loss, pos.take_profit = new_sl, new_tp; return True
        oid = self._orders.get(position_id, {}).get("bracket")
        if not oid: return False
        rule = self._rule(pos.symbol)
        data = self._request("POST", "/orders/edit", body={"order_id": oid, "price": rule.price(new_tp), "size": rule.amount(pos.volume), "attached_order_configuration": {"trigger_bracket_gtc": {"base_size": rule.amount(pos.volume), "limit_price": rule.price(new_tp), "stop_trigger_price": rule.price(new_sl)}}})
        ok = bool(data.get("success", False))
        if ok: pos.stop_loss, pos.take_profit = new_sl, new_tp
        return ok
    def close_position(self, position_id: str, volume: Optional[float] = None, reason: str = "") -> Optional[ClosedTrade]:
        pos = self._positions.get(position_id)
        if not pos: return None
        qty = min(float(volume or pos.volume), pos.volume); rule = self._rule(pos.symbol)
        if self.config.dry_run:
            exit_price = float(self._request("GET", f"/products/{rule.product_id}", auth=False).get("price", pos.entry_price))
        else:
            bracket = self._orders.get(position_id, {}).get("bracket")
            if bracket: self._request("POST", "/orders/batch_cancel", body={"order_ids": [bracket]})
            sell = self._request("POST", "/orders", body={"client_order_id": uuid.uuid4().hex, "product_id": rule.product_id, "side": "SELL", "order_configuration": {"market_market_ioc": {"base_size": rule.amount(qty), "rfq_disabled": True}}})
            oid = sell.get("success_response", {}).get("order_id") or sell.get("order_id")
            if not oid: raise BrokerError(f"Coinbase fermeture sans order_id: {sell}")
            filled = self._wait_filled(oid); exit_price = float(filled.get("average_filled_price") or pos.entry_price)
        profit = (exit_price - pos.entry_price) * qty * pos.side.sign
        risk = abs(pos.entry_price - pos.initial_stop) * qty
        trade = ClosedTrade(position_id=position_id, symbol=pos.symbol, side=pos.side, volume=qty, entry_price=pos.entry_price, exit_price=exit_price, opened_at=pos.opened_at, closed_at=time.time(), profit=profit, r_multiple=(profit / risk if risk else 0.0), reason=reason, tp_extensions=pos.tp_extensions, max_favorable_r=pos.r_multiple(pos.max_favorable), partial=qty < pos.volume - 1e-12)
        self._closed.append(trade)
        if qty >= pos.volume - 1e-12: self._positions.pop(position_id, None); self._orders.pop(position_id, None)
        else: pos.volume -= qty
        return trade
    def closed_trades(self) -> list[ClosedTrade]: return list(self._closed)
