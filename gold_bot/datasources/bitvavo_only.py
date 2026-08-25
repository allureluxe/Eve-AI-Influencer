"""Source de prix Bitvavo uniquement."""
from __future__ import annotations
import time
from typing import Optional
from ..core import Candle, Tick
from ..universe import CATALOGUE_CRYPTO
from .base import PriceProvider, ProviderCapabilities, ProviderError, SymbolNotSupported, http_get, resample

class BitvavoProvider(PriceProvider):
    name = "bitvavo"
    capabilities = ProviderCapabilities(asset_classes=("crypto",), rate_limit_per_min=120)
    devise_crypto = "EUR"
    ACTIFS = {f"{a}USD": a for a in CATALOGUE_CRYPTO}
    INTERVALS = {"M1":"1m","M5":"5m","M15":"15m","M30":"30m","H1":"1h","H4":"4h","D1":"1d"}

    @property
    def devise(self) -> str:
        return "EUR"

    def symbol_for(self, symbol: str, asset_class: str) -> Optional[str]:
        actif = self.ACTIFS.get(symbol.upper())
        return f"{actif}-EUR" if actif else None

    def fetch_candles(self, symbol: str, asset_class: str, timeframe: str, limit: int) -> list[Candle]:
        code = self.symbol_for(symbol, asset_class)
        if not code:
            raise SymbolNotSupported(f"bitvavo: {symbol} non cote")
        interval = self.INTERVALS.get(timeframe)
        if not interval:
            raise ProviderError(f"bitvavo: unite de temps non supportee {timeframe}")
        self.throttle()
        try:
            rows = http_get(f"https://api.bitvavo.com/v2/{code}/candles", params={"interval": interval, "limit": min(limit, 1440)})
        except ProviderError as exc:
            if getattr(exc, "status", None) == 400:
                raise SymbolNotSupported(f"bitvavo: {symbol} non cote en EUR") from exc
            raise
        if not isinstance(rows, list):
            raise ProviderError("bitvavo: reponse inattendue")
        out = [Candle(float(r[0])/1000, float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])) for r in reversed(rows)]
        return out[-limit:]

    def fetch_tick(self, symbol: str, asset_class: str) -> Optional[Tick]:
        code = self.symbol_for(symbol, asset_class)
        if not code:
            return None
        self.throttle()
        data = http_get("https://api.bitvavo.com/v2/ticker/book", params={"market": code})
        try:
            return Tick(time.time(), float(data["bid"]), float(data["ask"]), float(data.get("bidSize")) if data.get("bidSize") is not None else None, float(data.get("askSize")) if data.get("askSize") is not None else None)
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderError(f"bitvavo: tick invalide: {exc}") from exc
