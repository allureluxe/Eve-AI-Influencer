"""Couche donnees : registre multi-sources avec bascule automatique."""
from __future__ import annotations

import logging
import os
import time
from typing import Optional

from ..core import Candle, Tick
from .base import (PriceProvider, ProviderError, SymbolNotSupported,
                   resample, tf_seconds)
from .providers import (
    AlphaVantageProvider,
    BinanceProvider,
    FinnhubProvider,
    MetalPriceProvider,
    MoonXProvider,
    PolygonProvider,
    StooqProvider,
    SyntheticProvider,
    TwelveDataProvider,
    YahooProvider,
)

logger = logging.getLogger(__name__)

# Ordre de preference : le lieu d'execution d'abord (prix reels du broker),
# puis les sources gratuites fiables, puis les sources a cle.
PROVIDER_CLASSES = [
    MoonXProvider,
    BinanceProvider,
    YahooProvider,
    TwelveDataProvider,
    FinnhubProvider,
    PolygonProvider,
    AlphaVantageProvider,
    MetalPriceProvider,
    StooqProvider,
]


class DataRegistry:
    """Agrege toutes les sources et sert les donnees avec cache + failover.

    Regles :
      - une source en echec est mise en quarantaine quelques minutes,
      - les bougies sont mises en cache jusqu'a la cloture de la periode
        suivante (inutile de redemander une M5 toutes les 2 secondes),
      - si toutes les sources tombent, on remonte une erreur explicite
        plutot que de trader a l'aveugle.
    """

    def __init__(
        self,
        providers: Optional[list[PriceProvider]] = None,
        allow_synthetic: bool = False,
        quarantine_seconds: float = 300.0,
    ) -> None:
        if providers is None:
            providers = [cls() for cls in PROVIDER_CLASSES]
            if allow_synthetic:
                providers.append(SyntheticProvider())
        self.providers = providers
        self.quarantine_seconds = quarantine_seconds
        self._blocked: dict[str, float] = {}
        # Sources dont l'authentification a ete refusee : inutile de reessayer.
        self._auth_failed: set[str] = set()
        self._cache: dict[tuple, tuple[float, list[Candle]]] = {}
        self._tick_cache: dict[str, tuple[float, Tick]] = {}

    # ---------------------------------------------------------------
    def usable(self, asset_class: str) -> list[PriceProvider]:
        """Sources utilisables maintenant pour cette classe d'actif."""
        now = time.time()
        out = []
        for p in self.providers:
            if p.name in self._auth_failed:
                continue
            if not p.available():
                continue
            if asset_class not in p.capabilities.asset_classes:
                continue
            if self._blocked.get(p.name, 0.0) > now:
                continue
            out.append(p)
        # On privilegie les sources historiquement fiables.
        return sorted(out, key=lambda p: -p.health)

    def _quarantine(self, provider: PriceProvider, exc: Exception) -> None:
        provider.failures += 1

        # Une authentification refusee ne se repare pas toute seule : la cle est
        # absente, expiree ou revoquee. La mettre en quarantaine cinq minutes
        # revient a reessayer indefiniment toutes les cinq minutes, sur chaque
        # instrument, en inondant le journal pour un echec certain. On l'ecarte
        # donc jusqu'au prochain demarrage, en le disant une seule fois.
        if getattr(exc, "status", None) in (401, 403):
            if provider.name not in self._auth_failed:
                self._auth_failed.add(provider.name)
                logger.warning(
                    "source %s ecartee definitivement : authentification refusee "
                    "(%s). Corrigez sa cle ou retirez-la de la configuration.",
                    provider.name, str(exc)[:120])
            return

        self._blocked[provider.name] = time.time() + self.quarantine_seconds
        logger.warning("source %s ecartee %.0fs : %s", provider.name,
                       self.quarantine_seconds, str(exc)[:180])

    # ---------------------------------------------------------------
    def candles(
        self,
        symbol: str,
        asset_class: str,
        timeframe: str,
        limit: int = 300,
        max_age: Optional[float] = None,
    ) -> list[Candle]:
        """Bougies cloturees, servies depuis le cache si encore fraiches."""
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
                # La source ne cote pas cet instrument : on passe a la
                # suivante sans la penaliser, elle reste valable ailleurs.
                errors.append(f"{provider.name}: {str(exc)[:80]}")
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{provider.name}: {str(exc)[:80]}")
                self._quarantine(provider, exc)

        # Derniere chance : servir un cache perime plutot que rien du tout,
        # en le signalant clairement a l'appelant via le log.
        if hit:
            logger.warning("%s %s : toutes les sources KO, cache perime servi", symbol, timeframe)
            return hit[1]
        raise ProviderError(f"aucune source pour {symbol} {timeframe} ({' | '.join(errors) or 'aucune source active'})")

    def multi_timeframe(
        self,
        symbol: str,
        asset_class: str,
        timeframes: list[str],
        limit: int = 300,
    ) -> dict[str, list[Candle]]:
        """Recupere plusieurs unites de temps en minimisant les appels reseau.

        On telecharge la plus petite unite disponible et on agrege localement
        tout ce qui en est un multiple. Beaucoup plus rapide et economise le quota.
        """
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
        """Prix courant bid/ask, avec cache tres court (anti-spam d'API)."""
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
            except Exception as exc:  # noqa: BLE001
                self._quarantine(provider, exc)
        return hit[1] if hit else None

    # ---------------------------------------------------------------
    def status(self) -> list[dict]:
        """Etat de sante de chaque source (pour le diagnostic et le monitoring)."""
        now = time.time()
        return [
            {
                "source": p.name,
                "configuree": p.available(),
                "classes": list(p.capabilities.asset_classes),
                "cle_requise": p.capabilities.requires_key,
                "succes": p.successes,
                "echecs": p.failures,
                "sante": round(p.health, 3),
                "quarantaine_s": max(0, round(self._blocked.get(p.name, 0.0) - now)),
            }
            for p in self.providers
        ]


def build_registry(offline: bool = False) -> DataRegistry:
    """Construit le registre par defaut.

    `offline=True` n'active QUE la source synthetique : utile pour le
    backtest, les tests et la validation sans reseau.
    """
    if offline:
        return DataRegistry(providers=[SyntheticProvider()])
    return DataRegistry(allow_synthetic=False)


__all__ = [
    "DataRegistry",
    "build_registry",
    "PriceProvider",
    "ProviderError",
    "SymbolNotSupported",
    "SyntheticProvider",
    "resample",
    "tf_seconds",
]
