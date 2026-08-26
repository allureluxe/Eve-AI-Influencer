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
        """Convertit un symbole du moteur vers le contrat Futures Pionex.

        Important : ``ETH_USDT`` doit devenir ``ETH_USDT_PERP`` et non
        ``ETH__USDT_PERP``. Les variantes BTCUSD, BTC_USD, BTCUSDT,
        BTC_USDT et deja-normalisees sont toutes acceptees.
        """
        base = symbol.upper().strip()
        suffixes = (
            f"_{self.config.quote_asset}_PERP",
            f"{self.config.quote_asset}_PERP",
            f"_{self.config.quote_asset}",
            f"{self.config.quote_asset}",
            "_USD_PERP",
            "USD_PERP",
            "_USD",
            "USD",
        )
        for suffix in suffixes:
            if base.endswith(suffix):
                base = base[: -len(suffix)].rstrip("_")
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
