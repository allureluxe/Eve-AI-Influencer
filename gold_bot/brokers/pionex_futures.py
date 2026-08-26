"""Broker Futures USDT-M Pionex pour le moteur de trading.

Ce module utilise uniquement les endpoints Futures publics et prives
actuellement documentes par Pionex. Le TP/SL fourni au moteur est suivi par
le moteur lui-meme : Pionex ne documente pas actuellement un endpoint public
API dedie pour creer/modifier les ordres TP/SL de position. On ne pretend donc
pas qu'un TP/SL est exchange-side tant que Pionex ne l'expose pas dans son API.
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
        self._configured_mode = False

    @property
    def mode(self) -> str:
        return "simulation (dry-run)" if self.config.dry_run else "REEL"

    def register_instrument(self, instrument: Instrument) -> None:
        self._instruments[instrument.symbol] = instrument

    def pionex_symbol(self, symbol: str) -> str:
        base = symbol.upper()
        for suffix in ("_USDT_PERP", "USDT_PERP", "_USD", "USD", "USDT"):
            if base.endswith(suffix):
                base = base[: -len(suffix)]
                break
        if base not in ACTIFS:
            raise BrokerError(f"{symbol} n'est pas dans le catalogue crypto du robot")
        return f"{base}_{self.config.quote_asset}_PERP"

    def symbol_from_pionex(self, symbol: str) -> str:
        return symbol.split("_")[0].upper()

    def supports(self, symbol: str) -> bool:
        try:
            code = self.pionex_symbol(symbol)
        except BrokerError:
            return False
        rule = self._rules.get(code)
        return bool(rule and rule.enabled) if self._rules else True

    def notionnel_minimum(self) -> float:
        vals = [r.min_notional for r in self._rules.values() if r.enabled and r.min_notional > 0]
        return min(vals) if vals else 5.0

    # ----------------------------- REST ---------------------------------
    @staticmethod
    def _canonical_query(params: dict[str, Any]) -> str:
        return "&".join(f"{k}={str(v)}" for k, v in sorted(params.items()) if v is not None)

    @staticmethod
    def _http_query(params: dict[str, Any]) -> str:
        return urllib.parse.urlencode([(k, v) for k, v in sorted(params.items()) if v is not None])

    def _signature(self, method: str, path: str, params: dict[str, Any], body: str = "") -> str:
        query = self._canonical_query(params)
        path_url = path + (f"?{query}" if query else "")
        msg = method.upper() + path_url + body
        return hmac.new(self.config.api_secret.encode(), msg.encode(), hashlib.sha256).hexdigest()

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
        headers = {"Accept": "application/json", "User-Agent": "gold-bot-pionex-futures/1.0"}
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

    # ----------------------------- market --------------------------------
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
        return float(row["bidPrice"]), float(row["askPrice"])

    # ----------------------------- account --------------------------------
    def _refresh_account(self) -> None:
        data = self._private("GET", "/uapi/v1/account/balances")
        rows = data.get("data", {}).get("balances", [])
        free = frozen = 0.0
        for row in rows:
            if str(row.get("coin", "")).upper() == self.config.quote_asset:
                free = float(row.get("free", 0) or 0)
                frozen = float(row.get("frozen", 0) or 0)
                break
        self._account = AccountInfo(
            equity=free + frozen,
            balance=free + frozen,
            currency=self.config.quote_asset,
            margin_used=frozen,
            margin_free=free,
            leverage=self.config.leverage,
        )

    def account(self) -> AccountInfo:
        if not self.config.dry_run:
            self._refresh_account()
        return self._account

    def _configure_account(self) -> None:
        if self.config.dry_run or self._configured_mode:
            return
        mode = self._private("GET", "/uapi/v1/account/positionMode").get("data", {}).get("positionMode", "")
        positions = self._private("GET", "/uapi/v1/account/positions").get("data", {}).get("positions", [])
        nonzero = [p for p in positions if abs(float(p.get("netSize", 0) or 0)) > 0]
        if mode != self.config.position_mode:
            if nonzero:
                raise BrokerError(
                    f"mode Futures Pionex={mode}, demande={self.config.position_mode}, "
                    "mais des positions existent : changement refuse par securite"
                )
            self._private("POST", "/uapi/v1/account/positionMode",
                          body={"positionMode": self.config.position_mode})
        if self.config.margin_mode not in {"CROSS", "ISOLATED"}:
            raise BrokerError("PIONEX_MARGIN_MODE doit etre CROSS ou ISOLATED")
        self._configured_mode = True

    def connect(self) -> bool:
        try:
            self.apply_market_rules(None)
            if not self.config.dry_run:
                self._configure_account()
                self._refresh_account()
            else:
                self._account = AccountInfo(0.0, 0.0, self.config.quote_asset, leverage=self.config.leverage)
                logger.warning("Pionex Futures : mode DRY-RUN, aucun ordre reel ne sera envoye")
            self._healthy = True
            return True
        except Exception as exc:
            self._healthy = False
            logger.error("Pionex Futures connexion impossible : %s", str(exc)[:400])
            return False

    def healthy(self) -> bool:
        return self._healthy

    # ----------------------------- positions ------------------------------
    def _exchange_positions(self) -> list[dict[str, Any]]:
        if self.config.dry_run:
            return []
        return self._private("GET", "/uapi/v1/account/positions").get("data", {}).get("positions", [])

    def positions(self) -> list[Position]:
        if self.config.dry_run:
            return list(self._positions.values())
        rows = self._exchange_positions()
        seen: set[str] = set()
        for row in rows:
            size = abs(float(row.get("netSize", 0) or 0))
            if size <= 0:
                continue
            symbol = str(row.get("symbol", ""))
            side = Side.BUY if str(row.get("positionSide", "LONG")).upper() == "LONG" else Side.SELL
            pid = str(row.get("positionId") or f"{symbol}:{side.value}")
            seen.add(pid)
            previous = self._positions.get(pid)
            entry = float(row.get("avgPrice", 0) or 0)
            pos = Position(
                id=pid,
                symbol=self.symbol_from_pionex(symbol),
                side=side,
                volume=size,
                entry_price=entry,
                stop_loss=previous.stop_loss if previous else 0.0,
                take_profit=previous.take_profit if previous else 0.0,
                opened_at=(previous.opened_at if previous else float(row.get("createTime", time.time() * 1000)) / 1000),
                broker_ref=pid,
                comment=previous.comment if previous else "Pionex Futures",
            )
            if previous:
                pos.initial_stop = previous.initial_stop
                pos.initial_tp = previous.initial_tp
                pos.initial_risk = previous.initial_risk
                pos.max_favorable = previous.max_favorable
                pos.max_adverse = previous.max_adverse
                pos.tp_extensions = previous.tp_extensions
                pos.breakeven_done = previous.breakeven_done
                pos.partial_done = previous.partial_done
            self._positions[pid] = pos
        for pid in list(self._positions):
            if pid not in seen and not self.config.dry_run:
                self._positions.pop(pid, None)
        return list(self._positions.values())

    def reprendre(self, position: Position) -> bool:
        current = self.positions()
        for p in current:
            if p.symbol == position.symbol and p.side == position.side:
                position.id = p.id
                position.broker_ref = p.broker_ref
                self._positions[p.id] = position
                return True
        return False

    def _set_leverage(self, symbol: str) -> None:
        if self.config.dry_run:
            return
        self._private("POST", "/uapi/v1/account/leverage",
                      body={"symbol": symbol, "leverage": str(self.config.leverage)})
        if self.config.margin_mode in {"CROSS", "ISOLATED"}:
            self._private("POST", "/uapi/v1/trade/isolatedMode",
                          body={"symbol": symbol, "isolatedMode": self.config.margin_mode})

    def _place_market(self, symbol: str, side: Side, size: float, position_side: str) -> str:
        client = f"gb-{int(time.time() * 1000)}-{os.getpid()}"
        body = {
            "clientOrderId": client,
            "symbol": symbol,
            "positionSide": position_side,
            "side": "BUY" if side is Side.BUY else "SELL",
            "type": "MARKET_QTY",
            "size": str(size),
        }
        if self.config.dry_run:
            return f"DRY-{client}"
        data = self._private("POST", "/uapi/v1/trade/order", body=body)
        oid = data.get("data", {}).get("orderId")
        if oid is None:
            raise BrokerError(f"Pionex ordre sans orderId: {data}")
        return str(oid)

    def _wait_order(self, symbol: str, order_id: str) -> dict[str, Any]:
        if self.config.dry_run:
            return {}
        deadline = time.time() + self.config.order_timeout_seconds
        last: dict[str, Any] = {}
        while time.time() < deadline:
            last = self._private("GET", "/uapi/v1/trade/order",
                                 params={"symbol": symbol, "orderId": order_id}).get("data", {})
            if str(last.get("status", "")).upper() in {"FILLED", "CLOSED", "CANCELED", "CANCELLED", "REJECTED", "FAILED"}:
                return last
            time.sleep(self.config.poll_order_seconds)
        return last

    def _avg_fill(self, symbol: str, order_id: str, fallback: float) -> float:
        if self.config.dry_run:
            return fallback
        data = self._private("GET", "/uapi/v1/trade/fillsByOrderId",
                             params={"symbol": symbol, "orderId": order_id, "limit": 200})
        fills = data.get("data", {}).get("fills", [])
        qty = total = 0.0
        for fill in fills:
            q = float(fill.get("size", 0) or 0)
            p = float(fill.get("price", 0) or 0)
            qty += q
            total += q * p
        return total / qty if qty > 0 else fallback

    def open_position(self, instrument: Instrument, side: Side, lots: float,
                      stop_loss: float, take_profit: float, comment: str = "") -> Position:
        if lots <= 0 or not math.isfinite(lots):
            raise BrokerError("volume Futures invalide")
        if not stop_loss or not take_profit:
            raise BrokerError("SL et TP obligatoires")
        symbol = self.pionex_symbol(instrument.symbol)
        rule = self._rules.get(symbol)
        if not rule or not rule.enabled:
            raise BrokerError(f"contrat Futures indisponible : {symbol}")
        bid, ask = self._book(symbol)
        reference = ask if side is Side.BUY else bid
        size = rule.size_down(lots)
        if size <= 0:
            raise BrokerError(f"taille nulle apres arrondi : {lots}")
        if rule.min_size_market > 0 and size < rule.min_size_market:
            raise BrokerError(f"taille {size} sous le minimum Futures {rule.min_size_market} sur {symbol}")
        if rule.max_size_market > 0 and size > rule.max_size_market:
            raise BrokerError(f"taille {size} au-dessus du maximum Futures {rule.max_size_market} sur {symbol}")
        if rule.min_notional > 0 and size * reference < rule.min_notional:
            raise BrokerError(f"notionnel {size * reference:.4f} sous le minimum {rule.min_notional} sur {symbol}")
        if self.config.dry_run:
            entry = reference
            oid = self._place_market(symbol, side, size, "LONG" if side is Side.BUY else "SHORT")
        else:
            self._set_leverage(symbol)
            oid = self._place_market(symbol, side, size, "LONG" if side is Side.BUY else "SHORT")
            order = self._wait_order(symbol, oid)
            status = str(order.get("status", "")).upper()
            if status in {"REJECTED", "FAILED", "CANCELED", "CANCELLED"}:
                raise BrokerError(f"ordre Futures refuse : {status}")
            entry = self._avg_fill(symbol, oid, reference)
        pos_rows = self._exchange_positions() if not self.config.dry_run else []
        pid = ""
        if not self.config.dry_run:
            wanted = "LONG" if side is Side.BUY else "SHORT"
            for row in pos_rows:
                if str(row.get("symbol", "")) == symbol and str(row.get("positionSide", "")).upper() == wanted and abs(float(row.get("netSize", 0) or 0)) > 0:
                    pid = str(row.get("positionId", ""))
                    break
        if not pid:
            pid = f"{symbol}:{wanted if not self.config.dry_run else side.value}:{int(time.time()*1000)}"
        pos = Position(
            id=pid,
            symbol=instrument.symbol,
            side=side,
            volume=size,
            entry_price=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
            opened_at=time.time(),
            broker_ref=oid,
            comment=comment,
        )
        self._positions[pid] = pos
        logger.info("PIONEX FUTURES %s %s %s @ %.8f | SL %.8f TP %.8f | levier %.1fx",
                    self.mode, side.value, symbol, size, entry, stop_loss, take_profit, self.config.leverage)
        logger.warning("Pionex Futures TP/SL : suivi par le moteur, pas exchange-side via API publique documentee")
        return pos

    def modify_position(self, position_id: str, stop_loss: Optional[float] = None,
                        take_profit: Optional[float] = None) -> bool:
        pos = self._positions.get(position_id)
        if not pos:
            self.positions()
            pos = self._positions.get(position_id)
        if not pos:
            return False
        if stop_loss is not None:
            pos.stop_loss = float(stop_loss)
        if take_profit is not None:
            pos.take_profit = float(take_profit)
        return True

    def close_position(self, position_id: str, volume: Optional[float] = None,
                       reason: str = "") -> Optional[ClosedTrade]:
        pos = self._positions.get(position_id)
        if not pos:
            self.positions()
            pos = self._positions.get(position_id)
        if not pos:
            return None
        size = min(pos.volume, float(volume)) if volume is not None else pos.volume
        symbol = self.pionex_symbol(pos.symbol)
        bid, ask = self._book(symbol)
        exit_ref = bid if pos.side is Side.BUY else ask
        if self.config.dry_run:
            exit_price = exit_ref
        else:
            opposite = Side.SELL if pos.side is Side.BUY else Side.BUY
            oid = self._place_market(symbol, opposite, size, "LONG" if pos.side is Side.BUY else "SHORT")
            order = self._wait_order(symbol, oid)
            status = str(order.get("status", "")).upper()
            if status in {"REJECTED", "FAILED", "CANCELED", "CANCELLED"}:
                raise BrokerError(f"fermeture Futures refusee : {status}")
            exit_price = self._avg_fill(symbol, oid, exit_ref)
        profit = pos.side.sign * (exit_price - pos.entry_price) * size
        closed = ClosedTrade(
            position_id=pos.id,
            symbol=pos.symbol,
            side=pos.side,
            volume=size,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            opened_at=pos.opened_at,
            closed_at=time.time(),
            profit=profit,
            r_multiple=pos.r_multiple(exit_price),
            reason=reason or "fermeture",
            tp_extensions=pos.tp_extensions,
            max_favorable_r=pos.r_multiple(pos.max_favorable),
            partial=size < pos.volume,
        )
        if size >= pos.volume - 1e-12:
            self._positions.pop(pos.id, None)
        else:
            pos.volume -= size
        self._closed.append(closed)
        return closed

    def closed_trades(self) -> list[ClosedTrade]:
        out, self._closed = self._closed[:], []
        return out

    def sync(self) -> None:
        if not self.config.dry_run:
            self._refresh_account()
            self.positions()
