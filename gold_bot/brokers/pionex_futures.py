"""Broker USDT-M Futures Pionex pour le moteur de trading.

Implementation alignee sur l'OpenAPI Futures Pionex : compte, positions,
ordres market, confirmation, fermeture et synchronisation.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import math
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from typing import Any, Optional

from ..core import ClosedTrade, Position, Side
from ..universe import CATALOGUE_CRYPTO, Instrument
from .base import AccountInfo, Broker, BrokerError

logger = logging.getLogger(__name__)
BASE = "https://api.pionex.com"
ACTIFS = {str(a).upper() for a in CATALOGUE_CRYPTO}


@dataclass(slots=True)
class PionexFuturesRule:
    symbol: str
    base_currency: str
    quote_currency: str
    base_precision: int = 8
    quote_precision: int = 8
    min_notional: float = 0.0
    base_step: float = 0.0
    min_size_market: float = 0.0
    max_size_market: float = 0.0
    enabled: bool = True

    def size_down(self, value: float) -> float:
        if value <= 0:
            return 0.0
        if self.base_step > 0:
            q = Decimal(str(self.base_step))
            return float((Decimal(str(value)) / q).to_integral_value(rounding=ROUND_DOWN) * q)
        q = Decimal("1").scaleb(-max(0, self.base_precision))
        return float(Decimal(str(value)).quantize(q, rounding=ROUND_DOWN))


@dataclass(slots=True)
class PionexFuturesConfig:
    api_key: str = ""
    api_secret: str = ""
    quote_asset: str = "USDT"
    timeout: float = 15.0
    dry_run: bool = False
    leverage: float = 1.0
    margin_mode: str = "CROSS"
    position_mode: str = "OPENCLOSE"
    poll_order_seconds: float = 0.5
    order_timeout_seconds: float = 10.0
    fee_rate: float = 0.0005

    @classmethod
    def from_env(cls) -> "PionexFuturesConfig":
        return cls(
            api_key=os.getenv("PIONEX_API_KEY", "").strip(),
            api_secret=os.getenv("PIONEX_API_SECRET", "").strip(),
            quote_asset=os.getenv("PIONEX_QUOTE_ASSET", "USDT").strip().upper() or "USDT",
            timeout=float(os.getenv("PIONEX_TIMEOUT", "15") or 15),
            dry_run=os.getenv("PIONEX_DRY_RUN", "0").strip().lower() in ("1", "true", "yes", "oui"),
            leverage=max(1.0, float(os.getenv("PIONEX_LEVERAGE", "1") or 1)),
            margin_mode=os.getenv("PIONEX_MARGIN_MODE", "CROSS").strip().upper() or "CROSS",
            position_mode=os.getenv("PIONEX_POSITION_MODE", "OPENCLOSE").strip().upper() or "OPENCLOSE",
            poll_order_seconds=float(os.getenv("PIONEX_POLL_ORDER_SECONDS", "0.5") or 0.5),
            order_timeout_seconds=float(os.getenv("PIONEX_ORDER_TIMEOUT_SECONDS", "10") or 10),
            fee_rate=float(os.getenv("PIONEX_FEE_RATE", "0.0005") or 0.0005),
        )


class PionexFuturesBroker(Broker):
    name = "pionex"
    is_live = True
    supports_short = True

    def __init__(self, config: Optional[PionexFuturesConfig] = None) -> None:
        self.config = config or PionexFuturesConfig.from_env()
        self._positions: dict[str, Position] = {}
        self._instruments: dict[str, Instrument] = {}
        self._rules: dict[str, PionexFuturesRule] = {}
        self._closed: list[ClosedTrade] = []
        self._account = AccountInfo(0.0, 0.0, self.config.quote_asset)
        self._healthy = False

    @property
    def mode(self) -> str:
        return "simulation (dry-run)" if self.config.dry_run else "REEL"

    def register_instrument(self, instrument: Instrument) -> None:
        self._instruments[instrument.symbol] = instrument

    def pionex_symbol(self, symbol: str) -> str:
        base = symbol.upper().strip()
        suffixes = (
            f"_{self.config.quote_asset}_PERP", f"{self.config.quote_asset}_PERP",
            f"_{self.config.quote_asset}", self.config.quote_asset,
            "_USD_PERP", "USD_PERP", "_USD", "USD",
        )
        for suffix in suffixes:
            if base.endswith(suffix):
                base = base[:-len(suffix)].rstrip("_")
                break
        if base not in ACTIFS:
            raise BrokerError(f"{symbol} n'est pas dans le catalogue crypto du robot")
        return f"{base}_{self.config.quote_asset}_PERP"

    def symbol_from_pionex(self, symbol: str) -> str:
        return str(symbol).split("_")[0].upper()

    def supports(self, symbol: str) -> bool:
        try:
            code = self.pionex_symbol(symbol)
        except BrokerError:
            return False
        if not self._rules:
            return True
        rule = self._rules.get(code)
        return bool(rule and rule.enabled)

    def notionnel_minimum(self) -> float:
        vals = [r.min_notional for r in self._rules.values() if r.enabled and r.min_notional > 0]
        return min(vals) if vals else 5.0

    @staticmethod
    def _canonical_query(params: dict[str, Any]) -> str:
        return "&".join(f"{k}={str(v)}" for k, v in sorted(params.items()) if v is not None)

    @staticmethod
    def _http_query(params: dict[str, Any]) -> str:
        return urllib.parse.urlencode([(k, v) for k, v in sorted(params.items()) if v is not None])

    def _signature(self, method: str, path: str, params: dict[str, Any], body: str = "") -> str:
        query = self._canonical_query(params)
        path_url = path + (f"?{query}" if query else "")
        message = method.upper() + path_url + body
        return hmac.new(self.config.api_secret.encode(), message.encode(), hashlib.sha256).hexdigest()

    def _request(self, method: str, path: str, *, params: Optional[dict[str, Any]] = None,
                 body: Optional[dict[str, Any]] = None, private: bool = False) -> dict[str, Any]:
        params = dict(params or {})
        if private:
            if not self.config.api_key or not self.config.api_secret:
                raise BrokerError("PIONEX_API_KEY et PIONEX_API_SECRET absents")
            params["timestamp"] = int(time.time() * 1000)
        body_text = json.dumps(body, separators=(",", ":"), ensure_ascii=False) if body is not None else ""
        query = self._http_query(params)
        url = BASE + path + (f"?{query}" if query else "")
        headers = {"Accept": "application/json", "User-Agent": "gold-bot-pionex-futures/1.1"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if private:
            headers["PIONEX-KEY"] = self.config.api_key
            headers["PIONEX-SIGNATURE"] = self._signature(method, path, params, body_text)
        req = urllib.request.Request(url, data=body_text.encode() if body is not None else None,
                                     headers=headers, method=method.upper())
        try:
            with urllib.request.urlopen(req, timeout=self.config.timeout) as response:
                raw = response.read().decode()
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            raise BrokerError(f"Pionex HTTP {exc.code}: {raw[:500]}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise BrokerError(f"Pionex reseau indisponible: {exc}") from exc
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise BrokerError(f"Pionex JSON invalide: {raw[:300]}") from exc
        if not data.get("result", False):
            raise BrokerError(f"Pionex {data.get('code', 'ERROR')}: {data.get('message', 'echec API')}")
        return data

    def _public(self, path: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        return self._request("GET", path, params=params, private=False)

    def _private(self, method: str, path: str, params: Optional[dict[str, Any]] = None,
                 body: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        return self._request(method, path, params=params, body=body, private=True)

    def apply_market_rules(self, _universe: Any = None) -> None:
        data = self._public("/api/v1/common/symbols", params={"type": "PERP", "status": "TRADING"})
        rules: dict[str, PionexFuturesRule] = {}
        for row in data.get("data", {}).get("symbols", []):
            if str(row.get("quoteCurrency", "")).upper() != self.config.quote_asset:
                continue
            symbol = str(row.get("symbol", "")).upper()
            rules[symbol] = PionexFuturesRule(
                symbol=symbol,
                base_currency=str(row.get("baseCurrency", "")).upper(),
                quote_currency=str(row.get("quoteCurrency", "")).upper(),
                base_precision=int(row.get("basePrecision", 8) or 8),
                quote_precision=int(row.get("quotePrecision", 8) or 8),
                min_notional=float(row.get("minNotional", 0) or 0),
                base_step=float(row.get("baseStep", 0) or 0),
                min_size_market=float(row.get("minSizeMarket", row.get("minSizeLimit", 0)) or 0),
                max_size_market=float(row.get("maxSizeMarket", row.get("maxSizeLimit", 0)) or 0),
                enabled=str(row.get("status", "TRADING")).upper() == "TRADING",
            )
        self._rules = rules

    def _book(self, symbol: str) -> tuple[float, float]:
        data = self._public("/api/v1/market/bookTicker", params={"symbol": symbol})
        rows = data.get("data", {}).get("tickers", [])
        if not rows:
            raise BrokerError(f"Pionex aucun bid/ask pour {symbol}")
        row = rows[0]
        try:
            bid, ask = float(row["bidPrice"]), float(row["askPrice"])
        except (KeyError, TypeError, ValueError) as exc:
            raise BrokerError(f"Pionex bookTicker invalide: {row}") from exc
        if bid <= 0 or ask <= 0 or ask < bid:
            raise BrokerError(f"Pionex bid/ask incoherent: {bid}/{ask}")
        return bid, ask

    def _refresh_account(self) -> None:
        data = self._private("GET", "/uapi/v1/account/detail")
        detail = data.get("data", {})
        rows = detail.get("balances", []) or []
        row = next((r for r in rows if str(r.get("coin", "")).upper() == self.config.quote_asset), None)
        if row is None:
            raise BrokerError(f"Pionex Futures : aucun solde {self.config.quote_asset}")
        assets = float(row.get("assets", row.get("free", 0)) or 0)
        free = float(row.get("free", row.get("available", 0)) or 0)
        available = float(row.get("available", free) or free)
        frozen = float(row.get("frozen", 0) or 0)
        unrealized = float(row.get("unrealizedPnL", 0) or 0)
        margin = float(row.get("totalInitialMargin", 0) or 0)
        equity = assets + unrealized
        if equity < 0:
            raise BrokerError(f"Pionex Futures equity negative: {equity}")
        self._account = AccountInfo(equity=equity, balance=assets, currency=self.config.quote_asset,
                                    margin_used=margin if margin > 0 else frozen,
                                    margin_free=max(0.0, available), leverage=self.config.leverage)

    def connect(self) -> bool:
        try:
            self.apply_market_rules(None)
            if self.config.dry_run:
                self._healthy = True
                return True
            self._refresh_account()
            self._sync_exchange_positions()
            self._healthy = True
            return True
        except Exception as exc:  # noqa: BLE001
            self._healthy = False
            logger.error("Pionex Futures connexion impossible: %s", str(exc)[:400])
            return False

    def healthy(self) -> bool:
        return self._healthy

    def account(self) -> AccountInfo:
        if not self.config.dry_run:
            self._refresh_account()
        return self._account

    @staticmethod
    def _side_from_exchange(value: str) -> Optional[Side]:
        value = str(value).upper()
        if value in ("LONG", "BUY"):
            return Side.BUY
        if value in ("SHORT", "SELL"):
            return Side.SELL
        return None

    def _position_from_exchange(self, row: dict[str, Any]) -> Optional[Position]:
        side = self._side_from_exchange(row.get("positionSide", ""))
        size = abs(float(row.get("netSize", 0) or 0))
        if side is None:
            side = self._side_from_exchange(row.get("side", ""))
        if side is None or size <= 0:
            return None
        symbol = self.symbol_from_pionex(str(row.get("symbol", "")))
        entry = float(row.get("avgPrice", 0) or 0)
        if entry <= 0:
            return None
        pid = str(row.get("positionId") or uuid.uuid4().hex[:12])
        mark = float(row.get("markPrice", entry) or entry)
        # Protection values are deliberately conservative when recovering a
        # position that was opened before this process started. The engine
        # will immediately re-evaluate them; no fake exchange-side SL is claimed.
        return Position(id=pid, symbol=symbol, side=side, volume=size,
                        entry_price=entry, stop_loss=entry, take_profit=entry,
                        opened_at=float(row.get("createTime", time.time() * 1000) or time.time() * 1000) / 1000.0,
                        broker_ref=pid, comment="pionex-recovered")

    def _sync_exchange_positions(self) -> None:
        data = self._private("GET", "/uapi/v1/account/positions")
        rows = data.get("data", {}).get("positions", []) or []
        exchange: dict[str, Position] = {}
        for row in rows:
            pos = self._position_from_exchange(row)
            if pos:
                exchange[pos.id] = pos
        self._positions = exchange

    def positions(self) -> list[Position]:
        if not self.config.dry_run:
            self._sync_exchange_positions()
        return list(self._positions.values())

    def reprendre(self, position: Position) -> bool:
        try:
            current = self.positions()
            match = next((p for p in current if p.symbol == position.symbol and p.side is position.side), None)
            if not match:
                return False
            position.volume = match.volume
            position.entry_price = match.entry_price
            position.broker_ref = match.broker_ref
            self._positions[position.id] = position
            return True
        except Exception:
            return False

    def _order(self, symbol: str, side: Side, size: float, position_side: Side,
               client_id: str, reduce_only: bool = False) -> str:
        if size <= 0:
            raise BrokerError("taille d'ordre invalide")
        body: dict[str, Any] = {
            "clientOrderId": client_id,
            "symbol": symbol,
            "side": side.value,
            "type": "MARKET_QTY",
            "size": str(size),
        }
        if self.config.position_mode == "OPENCLOSE":
            body["positionSide"] = "LONG" if position_side is Side.BUY else "SHORT"
            body["reduceOnly"] = False
        else:
            body["positionSide"] = "BOTH"
            body["reduceOnly"] = bool(reduce_only)
        data = self._private("POST", "/uapi/v1/trade/order", body=body)
        order_id = data.get("data", {}).get("orderId")
        if order_id is None:
            raise BrokerError(f"Pionex ordre sans orderId: {data}")
        return str(order_id)

    def _wait_order(self, symbol: str, order_id: str) -> dict[str, Any]:
        if self.config.dry_run:
            return {}
        deadline = time.time() + self.config.order_timeout_seconds
        last: dict[str, Any] = {}
        while time.time() < deadline:
            last = self._private("GET", "/uapi/v1/trade/order",
                                 params={"symbol": symbol, "orderId": order_id}).get("data", {})
            status = str(last.get("status", "")).upper()
            if status in {"FILLED", "CLOSED", "CANCELED", "CANCELLED", "REJECTED", "FAILED"}:
                if status not in {"FILLED", "CLOSED"}:
                    raise BrokerError(f"Pionex ordre {order_id} termine en {status}: {last}")
                return last
            time.sleep(self.config.poll_order_seconds)
        raise BrokerError(f"Pionex ordre {order_id} non confirme apres {self.config.order_timeout_seconds:.1f}s")

    def _fill_price(self, symbol: str, order_id: str, fallback: float) -> tuple[float, float]:
        try:
            data = self._private("GET", "/uapi/v1/trade/fillsByOrderId",
                                params={"symbol": symbol, "orderId": order_id}).get("data", {})
            fills = data.get("fills", []) or []
            total_size = sum(float(f.get("size", 0) or 0) for f in fills)
            if total_size <= 0:
                return fallback, 0.0
            weighted = sum(float(f.get("price", fallback) or fallback) * float(f.get("size", 0) or 0) for f in fills)
            return weighted / total_size, sum(float(f.get("fee", 0) or 0) for f in fills)
        except Exception:
            return fallback, 0.0

    def open_position(self, instrument: Instrument, side: Side, lots: float,
                      stop_loss: float, take_profit: float, comment: str = "") -> Position:
        if lots <= 0 or not math.isfinite(lots):
            raise BrokerError("volume invalide")
        symbol = self.pionex_symbol(instrument.symbol)
        rule = self._rules.get(symbol)
        if not rule or not rule.enabled:
            raise BrokerError(f"marche Pionex indisponible: {symbol}")
        bid, ask = self._book(symbol)
        reference = ask if side is Side.BUY else bid
        size = rule.size_down(lots)
        if size < rule.min_size_market:
            raise BrokerError(f"quantite trop faible: {size} < {rule.min_size_market}")
        if rule.max_size_market > 0 and size > rule.max_size_market:
            size = rule.size_down(rule.max_size_market)
        if size * reference < rule.min_notional:
            raise BrokerError(f"notionnel trop faible: {size * reference:.8f} < {rule.min_notional:.8f}")
        if side is Side.BUY and not (0 < stop_loss < reference < take_profit):
            raise BrokerError("SL/TP invalides pour BUY")
        if side is Side.SELL and not (take_profit < reference < stop_loss):
            raise BrokerError("SL/TP invalides pour SELL")
        if self.config.dry_run:
            entry = reference
            order_id = "DRY-" + uuid.uuid4().hex[:12]
        else:
            order_id = self._order(symbol, side, size, side, f"gb-open-{uuid.uuid4().hex[:20]}")
            order = self._wait_order(symbol, order_id)
            filled = float(order.get("filledSize", 0) or 0)
            if filled <= 0:
                filled = size
            entry, _ = self._fill_price(symbol, order_id, reference)
            size = rule.size_down(filled)
            if size <= 0:
                raise BrokerError(f"ordre {order_id} confirme sans taille executee")
        pos = Position(id=uuid.uuid4().hex[:12], symbol=instrument.symbol, side=side,
                       volume=size, entry_price=entry, stop_loss=stop_loss,
                       take_profit=take_profit, opened_at=time.time(),
                       broker_ref=order_id, comment=comment)
        self._positions[pos.id] = pos
        if not self.config.dry_run:
            self._sync_exchange_positions()
            actual = [p for p in self._positions.values() if p.symbol == instrument.symbol and p.side is side]
            if not actual:
                self._positions.pop(pos.id, None)
                raise BrokerError(f"ordre {order_id} confirme mais position absente sur Pionex")
        return pos

    def modify_position(self, position_id: str, stop_loss: Optional[float] = None,
                        take_profit: Optional[float] = None) -> bool:
        pos = self._positions.get(position_id)
        if not pos:
            return False
        if stop_loss is not None:
            pos.stop_loss = float(stop_loss)
        if take_profit is not None:
            pos.take_profit = float(take_profit)
        # Pionex Futures expose TP/SL dans l'interface, mais l'API publique
        # utilisee ici ne fournit pas d'endpoint documente pour les modifier.
        # Le moteur reste donc responsable des sorties au tick.
        return True

    def close_position(self, position_id: str, volume: Optional[float] = None,
                       reason: str = "") -> Optional[ClosedTrade]:
        pos = self._positions.get(position_id)
        if not pos:
            return None
        symbol = self.pionex_symbol(pos.symbol)
        rule = self._rules.get(symbol)
        if not rule:
            raise BrokerError(f"regles marche absentes: {symbol}")
        qty = pos.volume if volume is None else min(float(volume), pos.volume)
        qty = rule.size_down(qty)
        if qty <= 0:
            raise BrokerError("quantite de sortie arrondie a zero")
        bid, ask = self._book(symbol)
        fallback = bid if pos.side is Side.BUY else ask
        if self.config.dry_run:
            order_id = "DRY-CLOSE-" + uuid.uuid4().hex[:12]
            exit_price, fee = fallback, qty * fallback * self.config.fee_rate
        else:
            order_id = self._order(symbol, pos.side.opposite, qty, pos.side,
                                   f"gb-close-{uuid.uuid4().hex[:20]}")
            self._wait_order(symbol, order_id)
            exit_price, fee = self._fill_price(symbol, order_id, fallback)
            if exit_price <= 0:
                exit_price = fallback
        profit = pos.side.sign * (exit_price - pos.entry_price) * qty - fee
        trade = ClosedTrade(position_id=pos.id, symbol=pos.symbol, side=pos.side,
                            volume=qty, entry_price=pos.entry_price, exit_price=exit_price,
                            opened_at=pos.opened_at, closed_at=time.time(), profit=profit,
                            r_multiple=pos.r_multiple(exit_price), reason=reason or "sortie",
                            tp_extensions=pos.tp_extensions,
                            max_favorable_r=pos.r_multiple(pos.max_favorable),
                            partial=qty < pos.volume - 1e-12)
        if qty >= pos.volume - 1e-12:
            self._positions.pop(position_id, None)
        else:
            pos.volume -= qty
        self._closed.append(trade)
        if not self.config.dry_run:
            self._sync_exchange_positions()
        return trade

    def sync(self) -> None:
        if self.config.dry_run:
            self._healthy = True
            return
        self._refresh_account()
        self._sync_exchange_positions()
        self._healthy = True

    def closed_trades(self) -> list[ClosedTrade]:
        out = list(self._closed)
        self._closed.clear()
        return out


__all__ = ["PionexFuturesBroker", "PionexFuturesConfig", "PionexFuturesRule"]
