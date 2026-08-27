"""Couche donnees : registre multi-sources avec bascule automatique."""
from __future__ import annotations

import logging
import time
from typing import Optional

from ..core import Candle, Tick
from .base import (PriceProvider, ProviderError, SymbolNotSupported,
                   resample, tf_seconds)
from .providers import (
    AlphaVantageProvider, BinanceProvider, BitvavoProvider, FinnhubProvider,
    MetalPriceProvider, MoonXProvider, OkxProvider, PolygonProvider,
    StooqProvider, SyntheticProvider, TwelveDataProvider, YahooProvider,
)

logger = logging.getLogger(__name__)

PROVIDER_CLASSES = [
    MoonXProvider, OkxProvider, BitvavoProvider, BinanceProvider,
    YahooProvider, TwelveDataProvider, FinnhubProvider, PolygonProvider,
    AlphaVantageProvider, MetalPriceProvider, StooqProvider,
]


class DataRegistry:
    """Agrege les sources avec cache et failover sans penaliser un symbole absent."""

    def __init__(self, providers: Optional[list[PriceProvider]] = None,
                 allow_synthetic: bool = False, quarantine_seconds: float = 300.0,
                 devise_crypto: str = "") -> None:
        if providers is None:
            providers = [cls() for cls in PROVIDER_CLASSES]
            if allow_synthetic:
                providers.append(SyntheticProvider())
        self.providers = providers
        self.quarantine_seconds = quarantine_seconds
        self.devise_crypto = (devise_crypto or "").upper()
        self._blocked: dict[str, float] = {}
        self._auth_failed: set[str] = set()
        self._cache: dict[tuple, tuple[float, list[Candle]]] = {}
        self._tick_cache: dict[str, tuple[float, Tick]] = {}

    def usable(self, asset_class: str) -> list[PriceProvider]:
        now = time.time()
        out = []
        for p in self.providers:
            if p.name in self._auth_failed or not p.available():
                continue
            if asset_class not in p.capabilities.asset_classes:
                continue
            if asset_class == "crypto" and not self._devise_compatible(p):
                continue
            if self._blocked.get(p.name, 0.0) > now:
                continue
            out.append(p)
        return sorted(out, key=lambda p: -p.health)

    EQUIVALENTS_DOLLAR = frozenset({"USD", "USDT", "USDC", "BUSD", "FDUSD", "DAI", "TUSD"})

    def _devise_compatible(self, provider: PriceProvider) -> bool:
        if not self.devise_crypto:
            return True
        voulue = self.devise_crypto
        offerte = getattr(provider, "devise_crypto", "USD").upper()
        if voulue in self.EQUIVALENTS_DOLLAR:
            return offerte in self.EQUIVALENTS_DOLLAR
        return offerte == voulue

    def _quarantine(self, provider: PriceProvider, exc: Exception) -> None:
        provider.failures += 1
        if getattr(exc, "status", None) in (401, 403):
            if provider.name not in self._auth_failed:
                self._auth_failed.add(provider.name)
                logger.warning("source %s ecartee definitivement : authentification refusee (%s).",
                               provider.name, str(exc)[:120])
            return
        self._blocked[provider.name] = time.time() + self.quarantine_seconds
        logger.warning("source %s ecartee %.0fs : %s", provider.name,
                       self.quarantine_seconds, str(exc)[:180])

    def candles(self, symbol: str, asset_class: str, timeframe: str,
                limit: int = 300, max_age: Optional[float] = None) -> list[Candle]:
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
                # IMPORTANT : symbole absent != panne fournisseur.
                errors.append(f"{provider.name}: {str(exc)[:80]}")
            except Exception as exc:
                errors.append(f"{provider.name}: {str(exc)[:80]}")
                self._quarantine(provider, exc)
        if hit:
            logger.warning("%s %s : toutes les sources KO, cache perime servi", symbol, timeframe)
            return hit[1]
        raise ProviderError(f"aucune source pour {symbol} {timeframe} ({' | '.join(errors) or 'aucune source active'})")

    def multi_timeframe(self, symbol: str, asset_class: str,
                        timeframes: list[str], limit: int = 300) -> dict[str, list[Candle]]:
        wanted = sorted(set(timeframes), key=tf_seconds)
        out: dict[str, list[Candle]] = {}
        base = wanted[0]
        base_secs = tf_seconds(base)
        base_limit = limit
        for tf in wanted[1:]:
            if tf_seconds(tf) % base_secs == 0:
                base_limit = max(base_limit, limit * (tf_seconds(tf) // base_secs))
        base_limit = min(base_limit, 1000)
        try:
            base_candles = self.candles(symbol, asset_class, base, base_limit)
            out[base] = base_candles[-limit:]
        except ProviderError:
            base_candles = []
        for tf in wanted[1:]:
            if base_candles and tf_seconds(tf) % base_secs == 0:
                agg = resample(base_candles, base, tf)
                if len(agg) >= min(limit, 120):
                    out[tf] = agg[-limit:]
                    continue
            out[tf] = self.candles(symbol, asset_class, tf, limit)
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
            except SymbolNotSupported:
                # CRITIQUE : l'ancien code envoyait SymbolNotSupported dans
                # _quarantine(), ce qui mettait Bitvavo/OKX hors service pour
                # 300 s apres UN seul symbole non cote. On passe simplement
                # au fournisseur suivant.
                continue
            except Exception as exc:
                self._quarantine(provider, exc)
        return hit[1] if hit else None

    def status(self) -> list[dict]:
        now = time.time()
        return [{
            "source": p.name, "configuree": p.available(),
            "classes": list(p.capabilities.asset_classes),
            "cle_requise": p.capabilities.requires_key,
            "succes": p.successes, "echecs": p.failures,
            "sante": round(p.health, 3),
            "quarantaine_s": max(0, round(self._blocked.get(p.name, 0.0) - now)),
        } for p in self.providers]


def build_registry(offline: bool = False, devise_crypto: str = "") -> DataRegistry:
    if offline:
        return DataRegistry(providers=[SyntheticProvider()])
    return DataRegistry(allow_synthetic=False, devise_crypto=devise_crypto)


__all__ = ["DataRegistry", "build_registry", "PriceProvider", "ProviderError",
           "SymbolNotSupported", "SyntheticProvider", "resample", "tf_seconds"]
