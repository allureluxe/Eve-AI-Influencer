"""Execution spot sur Pionex via l'OpenAPI officielle.

Le broker est volontairement independant de Bitvavo : un deuxieme service
systemd peut lancer le meme robot avec ``GB_ENGINE_BROKER=pionex``. Cela evite
de melanger les soldes, journaux, risques et devises des deux comptes.

Pionex spot n'expose pas un ordre stop/TP classique dans l'endpoint spot
OpenAPI. Les sorties sont donc surveillees par le moteur, comme un stop
local : le service doit rester actif. En cas de redemarrage, les positions
memorisees par le StateStore sont reprises et leur solde crypto est verifie.
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
from .base import AccountInfo, Broker, BrokerError, new_position_id

logger = logging.getLogger(__name__)

BASE = "https://api.pionex.com"
ACTIFS = {str(a).upper() for a in CATALOGUE_CRYPTO}


@dataclass(slots=True)
class PionexMarketRule:
    symbol: str
    base_currency: str
    quote_currency: str
    base_precision: int = 8
    quote_precision: int = 8
    amount_precision: int = 8
    min_amount: float = 0.0
    min_trade_size: float = 0.0
    min_trade_dumping: float = 0.0
    enabled: bool = True

    def amount_down(self, value: float) -> float:
        precision = max(0, int(self.base_precision or self.amount_precision))
        q = Decimal("1").scaleb(-precision)
        return float(Decimal(str(max(0.0, value))).quantize(q, rounding=ROUND_DOWN))

    def quote_down(self, value: float) -> float:
        q = Decimal("1").scaleb(-max(0, int(self.quote_precision)))
        return float(Decimal(str(max(0.0, value))).quantize(q, rounding=ROUND_DOWN))


@dataclass(slots=True)
class PionexConfig:
    api_key: str = ""
    api_secret: str = ""
    quote_asset: str = "USDT"
    timeout: float = 15.0
    dry_run: bool = False
    fee_rate: float = 0.0005
    poll_order_seconds: float = 0.5
    order_timeout_seconds: float = 10.0
    max_slippage_pct: float = 0.50

    @classmethod
    def from_env(cls) -> "PionexConfig":
        return cls(
            api_key=os.getenv("PIONEX_API_KEY", "").strip(),
            api_secret=os.getenv("PIONEX_API_SECRET", "").strip(),
            quote_asset=os.getenv("PIONEX_QUOTE_ASSET", "USDT").strip().upper() or "USDT",
            timeout=float(os.getenv("PIONEX_TIMEOUT", "15") or 15),
            dry_run=os.getenv("PIONEX_DRY_RUN", "0").strip().lower() in ("1", "true", "yes", "oui"),
            fee_rate=float(os.getenv("PIONEX_FEE_RATE", "0.0005") or 0.0005),
            poll_order_seconds=float(os.getenv("PIONEX_POLL_ORDER_SECONDS", "0.5") or 0.5),
            order_timeout_seconds=float(os.getenv("PIONEX_ORDER_TIMEOUT_SECONDS", "10") or 10),
            max_slippage_pct=float(os.getenv("PIONEX_MAX_SLIPPAGE_PCT", "0.50") or 0.50),
        )


class PionexBroker(Broker):
    """Broker spot Pionex, achat uniquement, avec sorties gerees par le moteur."""

    name = "pionex"
    is_live = True
    supports_short = False

    def __init__(self, config: Optional[PionexConfig] = None) -> None:
        self.config = config or PionexConfig.from_env()
        self._positions: dict[str, Position] = {}
        self._instruments: dict[str, Instrument] = {}
        self._rules: dict[str, PionexMarketRule] = {}
        self._closed: list[ClosedTrade] = []
        self._account = AccountInfo(0.0, 0.0, self.config.quote_asset)
        self._balances: dict[str, tuple[float, float]] = {}
        self._last_error = ""
        self._healthy = False

    @property
    def mode(self) -> str:
        return "simulation (dry-run)" if self.config.dry_run else "REEL"

    def register_instrument(self, instrument: Instrument) -> None:
        self._instruments[instrument.symbol] = instrument

    def pionex_symbol(self, symbol: str) -> str:
        base = symbol.upper()
        if base.endswith("USD"):
            base = base[:-3]
        if base.endswith("USDT"):
            base = base[:-4]
        if base not in ACTIFS:
            raise BrokerError(f"{symbol} n'est pas dans le catalogue crypto du robot")
        return f"{base}_{self.config.quote_asset}"

    def supports(self, symbol: str) -> bool:
        code = self.pionex_symbol(symbol)
        rule = self._rules.get(code)
        return rule.enabled if rule else symbol.upper() in ACTIFS

    def notionnel_minimum(self) -> float:
        values = [r.min_amount for r in self._rules.values() if r.enabled and r.min_amount > 0]
        return min(values) if values else 5.0

    # ------------------------------------------------------------------
    # REST / signature
    # ------------------------------------------------------------------
    def _encode_query(self, params: dict[str, Any]) -> str:
        return "&".join(
            f"{k}={urllib.parse.quote(str(v), safe='') }"
            for k, v in sorted(params.items())
            if v is not None
        )

    def _signature(self, method: str, path: str, params: dict[str, Any], body: str = "") -> str:
        query = self._encode_query(params)
        path_url = path + (f"?{query}" if query else "")
        message = method.upper() + path_url + body
        return hmac.new(
            self.config.api_secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def _request(self, method: str, path: str, *, params: Optional[dict[str, Any]] = None,
                 body: Optional[dict[str, Any]] = None, private: bool = False) -> dict[str, Any]:
        params = dict(params or {})
        body_text = ""
        if private:
            params["timestamp"] = int(time.time() * 1000)
            if not self.config.api_key or not self.config.api_secret:
                raise BrokerError("PIONEX_API_KEY et PIONEX_API_SECRET absents")
        if body is not None:
            body_text = json.dumps(body, separators=(",", ":"), ensure_ascii=False)

        query = self._encode_query(params)
        url = BASE + path + (f"?{query}" if query else "")
        headers = {"Accept": "application/json", "User-Agent": "gold-bot/1.0"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if private:
            headers["PIONEX-KEY"] = self.config.api_key
            headers["PIONEX-SIGNATURE"] = self._signature(method, path, params, body_text)

        request = urllib.request.Request(url, data=body_text.encode("utf-8") if body is not None else None,
                                          headers=headers, method=method.upper())
        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            raise BrokerError(f"Pionex HTTP {exc.code}: {raw[:500]}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise BrokerError(f"Pionex reseau indisponible: {exc}") from exc

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise BrokerError(f"Pionex reponse JSON invalide: {raw[:300]}") from exc
        if not data.get("result", False):
            raise BrokerError(f"Pionex {data.get('code', 'ERROR')}: {data.get('message', 'echec API')}")
        return data

    def _public(self, path: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        return self._request("GET", path, params=params, private=False)

    def _private(self, method: str, path: str, params: Optional[dict[str, Any]] = None,
                 body: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        return self._request(method, path, params=params, body=body, private=True)

    # ------------------------------------------------------------------
    def connect(self) -> bool:
        try:
            self.apply_market_rules(None)
            if self.config.dry_run:
                self._healthy = True
                self._account = AccountInfo(0.0, 0.0, self.config.quote_asset)
                logger.warning("Pionex : mode DRY-RUN, aucun ordre reel ne sera envoye")
                return True
            self._refresh_balances()
            self._healthy = True
            return True
        except Exception as exc:  # noqa: BLE001
            self._healthy = False
            self._last_error = str(exc)
            logger.error("Pionex connexion impossible : %s", str(exc)[:300])
            return False

    def healthy(self) -> bool:
        return self._healthy

    def _refresh_balances(self) -> None:
        data = self._private("GET", "/api/v1/account/balances")
        rows = data.get("data", {}).get("balances", [])
        balances: dict[str, tuple[float, float]] = {}
        for row in rows:
            coin = str(row.get("coin", "")).upper()
            balances[coin] = (float(row.get("free", 0) or 0), float(row.get("frozen", 0) or 0))
        self._balances = balances
        free, frozen = balances.get(self.config.quote_asset, (0.0, 0.0))
        self._account = AccountInfo(
            equity=free + frozen,
            balance=free + frozen,
            currency=self.config.quote_asset,
            margin_used=frozen,
            margin_free=free,
            leverage=1.0,
        )

    def account(self) -> AccountInfo:
        if not self.config.dry_run:
            self._refresh_balances()
        return self._account

    def apply_market_rules(self, _universe: Any = None) -> None:
        params = {"type": "SPOT"}
        data = self._public("/api/v1/common/symbols", params=params)
        rows = data.get("data", {}).get("symbols", [])
        rules: dict[str, PionexMarketRule] = {}
        for row in rows:
            if str(row.get("type", "SPOT")).upper() != "SPOT":
                continue
            if str(row.get("quoteCurrency", "")).upper() != self.config.quote_asset:
                continue
            symbol = str(row.get("symbol", ""))
            rules[symbol] = PionexMarketRule(
                symbol=symbol,
                base_currency=str(row.get("baseCurrency", "")).upper(),
                quote_currency=str(row.get("quoteCurrency", "")).upper(),
                base_precision=int(row.get("basePrecision", 8) or 8),
                quote_precision=int(row.get("quotePrecision", 8) or 8),
                amount_precision=int(row.get("amountPrecision", 8) or 8),
                min_amount=float(row.get("minAmount", 0) or 0),
                min_trade_size=float(row.get("minTradeSize", 0) or 0),
                min_trade_dumping=float(row.get("minTradeDumping", 0) or 0),
                enabled=bool(row.get("enable", True)),
            )
        self._rules = rules

    def _book(self, symbol: str) -> tuple[float, float]:
        data = self._public("/api/v1/market/bookTickers", params={"symbol": symbol, "type": "SPOT"})
        rows = data.get("data", {}).get("tickers", [])
        if not rows:
            raise BrokerError(f"Pionex aucun bid/ask pour {symbol}")
        row = rows[0]
        return float(row["bidPrice"]), float(row["askPrice"])

    def _order(self, symbol: str, side: str, size: Optional[float] = None,
               amount: Optional[float] = None, client_id: str = "") -> str:
        body: dict[str, Any] = {"symbol": symbol, "side": side, "type": "MARKET"}
        if client_id:
            body["clientOrderId"] = client_id
        if size is not None:
            body["size"] = str(size)
        if amount is not None:
            body["amount"] = str(amount)
        if self.config.dry_run:
            return f"DRY-{client_id or int(time.time() * 1000)}"
        data = self._private("POST", "/api/v1/trade/order", body=body)
        order_id = data.get("data", {}).get("orderId")
        if order_id is None:
            raise BrokerError(f"Pionex ordre sans orderId: {data}")
        return str(order_id)

    def _get_order(self, order_id: str) -> dict[str, Any]:
        data = self._private("GET", "/api/v1/trade/order", params={"orderId": order_id})
        return data.get("data", {})

    def _wait_filled(self, order_id: str) -> dict[str, Any]:
        if self.config.dry_run:
            return {}
        deadline = time.time() + self.config.order_timeout_seconds
        last: dict[str, Any] = {}
        while time.time() < deadline:
            last = self._get_order(order_id)
            status = str(last.get("status", "")).upper()
            if status in {"FILLED", "CLOSED", "CANCELLED", "CANCELED", "REJECTED", "FAILED"}:
                return last
            time.sleep(self.config.poll_order_seconds)
        return last

    def _entry_price(self, order: dict[str, Any], fallback: float) -> float:
        filled = float(order.get("filledSize", 0) or 0)
        amount = float(order.get("filledAmount", 0) or 0)
        if filled > 0 and amount > 0:
            return amount / filled
        return fallback

    # ------------------------------------------------------------------
    def positions(self) -> list[Position]:
        return list(self._positions.values())

    def reprendre(self, position: Position) -> bool:
        """Reprend une position locale si le solde de l'actif couvre le volume."""
        try:
            if self.config.dry_run:
                self._positions[position.id] = position
                return True
            base = self.pionex_symbol(position.symbol).split("_")[0]
            free, frozen = self._balances.get(base, (0.0, 0.0))
            if free + frozen + 1e-12 < position.volume:
                logger.warning("Pionex : position %s non reprise, solde %s insuffisant", position.symbol, base)
                return False
            self._positions[position.id] = position
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("Pionex reprise %s impossible: %s", position.symbol, exc)
            return False

    def open_position(self, instrument: Instrument, side: Side, lots: float,
                      stop_loss: float, take_profit: float, comment: str = "") -> Position:
        if side is not Side.BUY:
            raise BrokerError("Pionex spot : vente a decouvert non supportee")
        if lots <= 0 or not math.isfinite(lots):
            raise BrokerError("volume invalide")
        symbol = self.pionex_symbol(instrument.symbol)
        rule = self._rules.get(symbol)
        if not rule or not rule.enabled:
            raise BrokerError(f"marche Pionex indisponible : {symbol}")

        bid, ask = self._book(symbol)
        amount = rule.quote_down(lots * ask)
        min_amount = rule.min_amount or 0.0
        if amount < min_amount:
            raise BrokerError(f"notionnel Pionex trop faible : {amount:.8f} < minimum {min_amount:.8f} {self.config.quote_asset}")
        size = rule.amount_down(amount / ask)
        if size < (rule.min_trade_size or 0.0):
            raise BrokerError(f"quantite Pionex trop faible : {size} < minimum {rule.min_trade_size}")

        # Le moteur fournit les niveaux sur le prix d'entree du signal. Pour
        # rester coherent meme si Bitvavo et Pionex cotent legerement differents,
        # on conserve les distances relatives au prix et on les applique au ask Pionex.
        sl_pct = abs(stop_loss - ask) / ask if ask > 0 else 0.0
        tp_pct = abs(take_profit - ask) / ask if ask > 0 else 0.0
        if not (0 < sl_pct < 1.0 and 0 < tp_pct < 10.0):
            raise BrokerError(f"niveaux invalides apres normalisation Pionex: SL={sl_pct:.4%}, TP={tp_pct:.4%}")

        client = f"gb-{int(time.time()*1000)}-{new_position_id()}"
        order_id = self._order(symbol, "BUY", amount=amount, client_id=client)
        order = self._wait_filled(order_id)
        filled_size = float(order.get("filledSize", 0) or size) if order else size
        entry = self._entry_price(order, ask) if order else ask
        if filled_size <= 0:
            raise BrokerError(f"achat Pionex non rempli: order={order_id} status={order.get('status', '?')}")

        # Recalcule les niveaux a partir du prix reel de remplissage.
        actual_sl = entry * (1.0 - sl_pct)
        actual_tp = entry * (1.0 + tp_pct)
        pos = Position(
            id=new_position_id(),
            symbol=instrument.symbol,
            side=Side.BUY,
            volume=filled_size,
            entry_price=entry,
            stop_loss=actual_sl,
            take_profit=actual_tp,
            opened_at=time.time(),
            broker_ref=order_id,
            comment=comment,
        )
        self._positions[pos.id] = pos
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
        return True

    def close_position(self, position_id: str, volume: Optional[float] = None,
                       reason: str = "") -> Optional[ClosedTrade]:
        pos = self._positions.get(position_id)
        if not pos:
            return None
        qty = pos.volume if volume is None else min(float(volume), pos.volume)
        if qty <= 0:
            return None
        symbol = self.pionex_symbol(pos.symbol)
        rule = self._rules.get(symbol)
        if not rule:
            raise BrokerError(f"regles marche absentes: {symbol}")
        qty = rule.amount_down(qty)
        if qty <= 0:
            raise BrokerError("quantite de sortie arrondie a zero")

        bid, _ = self._book(symbol)
        order_id = self._order(symbol, "SELL", size=qty, client_id=f"gb-close-{new_position_id()}")
        order = self._wait_filled(order_id)
        filled = float(order.get("filledSize", 0) or qty) if order else qty
        exit_price = self._entry_price(order, bid) if order else bid
        if filled <= 0:
            raise BrokerError(f"vente Pionex non remplie: order={order_id}")

        profit = (exit_price - pos.entry_price) * filled
        fee = float(order.get("fee", 0) or 0) if order else 0.0
        profit -= fee
        trade = ClosedTrade(
            position_id=pos.id,
            symbol=pos.symbol,
            side=pos.side,
            volume=filled,
            entry_price=pos.entry_price,
            exit_price=exit_price,
            opened_at=pos.opened_at,
            closed_at=time.time(),
            profit=profit,
            r_multiple=pos.r_multiple(exit_price),
            reason=reason or "sortie",
            tp_extensions=pos.tp_extensions,
            max_favorable_r=pos.r_multiple(pos.max_favorable),
            partial=filled < pos.volume - 1e-12,
        )
        if filled >= pos.volume - 1e-12:
            self._positions.pop(position_id, None)
        else:
            pos.volume -= filled
        self._closed.append(trade)
        return trade

    def sync(self) -> None:
        if not self.config.dry_run:
            self._refresh_balances()
        self._healthy = True

    def closed_trades(self) -> list[ClosedTrade]:
        out = list(self._closed)
        self._closed.clear()
        return out


__all__ = ["PionexBroker", "PionexConfig", "PionexMarketRule"]
