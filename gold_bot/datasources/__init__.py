"""Couche donnees : Bitvavo uniquement pour le trading crypto."""
from __future__ import annotations
import logging
import time
from typing import Optional
from ..core import Candle, Tick
from .base import PriceProvider, ProviderError, SymbolNotSupported, resample, tf_seconds
from .bitvavo_only import BitvavoProvider

logger = logging.getLogger(__name__)
PROVIDER_CLASSES = [BitvavoProvider]

class DataRegistry:
    def __init__(self, providers: Optional[list[PriceProvider]] = None, allow_synthetic: bool = False, quarantine_seconds: float = 300.0, devise_crypto: str = "EUR") -> None:
        if providers is None:
            providers = [cls() for cls in PROVIDER_CLASSES]
        self.providers = providers
        self.quarantine_seconds = quarantine_seconds
        self.devise_crypto = (devise_crypto or "EUR").upper()
        self._blocked: dict[str, float] = {}
        self._cache: dict[tuple, tuple[float, list[Candle]]] = {}
        self._tick_cache: dict[str, tuple[float, Tick]] = {}

    def usable(self, asset_class: str) -> list[PriceProvider]:
        now = time.time()
        return [p for p in self.providers if p.available() and asset_class in p.capabilities.asset_classes and self._blocked.get(p.name, 0.0) <= now]

    def _quarantine(self, provider: PriceProvider, exc: Exception) -> None:
        provider.failures += 1
        self._blocked[provider.name] = time.time() + self.quarantine_seconds
        logger.warning("source %s ecartee %.0fs : %s", provider.name, self.quarantine_seconds, str(exc)[:180])

    def candles(self, symbol: str, asset_class: str, timeframe: str, limit: int = 300, max_age: Optional[float] = None) -> list[Candle]:
        key = (symbol, timeframe, limit)
        ttl = max_age if max_age is not None else min(tf_seconds(timeframe) / 3.0, 60.0)
        hit = self._cache.get(key)
        if hit and time.time() - hit[0] < ttl:
            return hit[1]
        errors = []
        for provider in self.usable(asset_class):
            try:
                data = provider.fetch_candles(symbol, asset_class, timeframe, limit)
                if len(data) < min(30, limit):
                    raise ProviderError(f"historique trop court ({len(data)})")
                provider.successes += 1
                self._cache[key] = (time.time(), data)
                return data
            except SymbolNotSupported as exc:
                errors.append(str(exc)[:100])
            except Exception as exc:
                errors.append(str(exc)[:100])
                self._quarantine(provider, exc)
        if hit:
            return hit[1]
        raise ProviderError(f"aucune source Bitvavo pour {symbol} {timeframe}: {' | '.join(errors)}")

    def multi_timeframe(self, symbol: str, asset_class: str, timeframes: list[str], limit: int = 300) -> dict[str, list[Candle]]:
        wanted = sorted(set(timeframes), key=tf_seconds)
        out: dict[str, list[Candle]] = {}
        base = wanted[0]
        base_candles = self.candles(symbol, asset_class, base, min(limit * max(1, tf_seconds(wanted[-1]) // tf_seconds(base)), 1000))
        for tf in wanted:
            if tf == base:
                out[tf] = base_candles[-limit:]
            else:
                agg = resample(base_candles, base, tf)
                out[tf] = agg[-limit:]
        return out

    def tick(self, symbol: str, asset_class: str, max_age: float = 2.0) -> Optional[Tick]:
        hit = self._tick_cache.get(symbol)
        if hit and time.time() - hit[0] < max_age:
            return hit[1]
        for provider in self.usable(asset_class):
            try:
                t = provider.fetch_tick(symbol, asset_class)
                if t and t.bid > 0 and t.ask >= t.bid:
                    provider.successes += 1
                    self._tick_cache[symbol] = (time.time(), t)
                    return t
            except Exception as exc:
                self._quarantine(provider, exc)
        return hit[1] if hit else None

    def status(self) -> list[dict]:
        now = time.time()
        return [{"source": p.name, "configuree": p.available(), "classes": list(p.capabilities.asset_classes), "cle_requise": p.capabilities.requires_key, "succes": p.successes, "echecs": p.failures, "sante": round(p.health, 3), "quarantaine_s": max(0, round(self._blocked.get(p.name, 0.0) - now))} for p in self.providers]

def build_registry(offline: bool = False, devise_crypto: str = "EUR") -> DataRegistry:
    if offline:
        raise ProviderError("offline/synthetique desactive : le robot est Bitvavo uniquement")
    return DataRegistry(devise_crypto="EUR")

__all__ = ["DataRegistry", "build_registry", "PriceProvider", "ProviderError", "SymbolNotSupported", "resample", "tf_seconds"]
