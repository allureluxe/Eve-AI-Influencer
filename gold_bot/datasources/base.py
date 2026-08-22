"""Socle commun a toutes les sources de donnees.

Aucune dependance externe : on utilise urllib et json de la librairie
standard, avec un client HTTP tolerant (timeout, retries, respect du proxy).
"""
from __future__ import annotations

import json
import logging
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional

from ..core import Candle, Tick

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = float(os.getenv("GB_HTTP_TIMEOUT", "12"))
USER_AGENT = "gold-bot/1.0 (+trading-research)"


class ProviderError(RuntimeError):
    """Erreur recuperable : le registre bascule sur la source suivante."""


class SymbolNotSupported(ProviderError):
    """La source ne cote pas cet instrument — ce n'est pas une panne.

    Distinction essentielle : une source injoignable doit etre mise en
    quarantaine pour laisser la main aux suivantes, mais une source qui ne
    connait simplement pas ce symbole reste parfaitement saine pour tous les
    autres. Les confondre revient a couper Binance pour le BTC parce qu'on lui
    a demande une paire exotique qu'elle ne liste pas.
    """


def http_get(
    url: str,
    params: Optional[dict[str, Any]] = None,
    headers: Optional[dict[str, str]] = None,
    timeout: float = DEFAULT_TIMEOUT,
    retries: int = 2,
    as_json: bool = True,
) -> Any:
    """GET HTTP avec retries exponentiels. Retourne du JSON ou du texte brut."""
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    hdrs = {"User-Agent": USER_AGENT, "Accept": "*/*"}
    if headers:
        hdrs.update(headers)

    last_err: Optional[Exception] = None
    statut: Optional[int] = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=hdrs)
            ctx = ssl.create_default_context()
            ca = os.getenv("GB_CA_BUNDLE") or "/root/.ccr/ca-bundle.crt"
            if os.path.exists(ca):
                try:
                    ctx.load_verify_locations(ca)
                except Exception:  # pragma: no cover - environnement sans bundle
                    pass
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw) if as_json else raw
        except urllib.error.HTTPError as exc:
            last_err = exc
            statut = exc.code
            # Une erreur 4xx vient de la requete elle-meme : la reessayer
            # donnera exactement la meme reponse. Seul 429 (trop de requetes)
            # merite d'attendre. Sortir tout de suite evite trois tentatives
            # inutiles sur un symbole qui n'existe pas.
            if 400 <= exc.code < 500 and exc.code != 429:
                break
            if attempt < retries:
                time.sleep(min(2 ** attempt, 4))
        except Exception as exc:  # noqa: BLE001 - on veut vraiment tout attraper
            last_err = exc
            if attempt < retries:
                time.sleep(min(2 ** attempt, 4))

    erreur = ProviderError(f"GET {url} a echoue: {last_err}")
    # Le code HTTP permet a l'appelant de distinguer une panne d'un symbole
    # inconnu, distinction qui decide de la mise en quarantaine de la source.
    erreur.status = statut
    raise erreur


@dataclass(slots=True)
class ProviderCapabilities:
    intraday: bool = True
    daily: bool = True
    quotes: bool = True
    asset_classes: tuple[str, ...] = ("metal", "forex", "crypto", "index")
    requires_key: bool = False
    rate_limit_per_min: int = 60


class PriceProvider(ABC):
    """Interface d'une source de prix."""

    name: str = "abstract"
    capabilities: ProviderCapabilities = ProviderCapabilities()

    def __init__(self) -> None:
        self._last_call = 0.0
        self.failures = 0
        self.successes = 0

    # --- a implementer ---
    @abstractmethod
    def symbol_for(self, symbol: str, asset_class: str) -> Optional[str]:
        """Traduit un symbole interne (XAUUSD) vers le code du fournisseur."""

    @abstractmethod
    def fetch_candles(self, symbol: str, asset_class: str, timeframe: str, limit: int) -> list[Candle]:
        """Recupere `limit` bougies cloturees pour l'unite de temps demandee."""

    def fetch_tick(self, symbol: str, asset_class: str) -> Optional[Tick]:
        """Prix courant. Par defaut : derive de la derniere bougie M1."""
        candles = self.fetch_candles(symbol, asset_class, "M1", 2)
        if not candles:
            return None
        last = candles[-1]
        half = max(abs(last.close) * 1e-5, 1e-6)
        return Tick(last.ts, last.close - half, last.close + half)

    # --- utilitaires communs ---
    def available(self) -> bool:
        """La source est-elle utilisable (cle presente, quota non epuise) ?"""
        return True

    def throttle(self) -> None:
        """Respecte la limite d'appels par minute du fournisseur."""
        min_gap = 60.0 / max(1, self.capabilities.rate_limit_per_min)
        elapsed = time.time() - self._last_call
        if elapsed < min_gap:
            time.sleep(min_gap - elapsed)
        self._last_call = time.time()

    @property
    def health(self) -> float:
        """Taux de succes observe (sert au classement des sources)."""
        total = self.successes + self.failures
        return 1.0 if total == 0 else self.successes / total


TIMEFRAME_SECONDS = {
    "M1": 60, "M3": 180, "M5": 300, "M15": 900, "M30": 1800,
    "H1": 3600, "H4": 14400, "D1": 86400,
}


def tf_seconds(timeframe: str) -> int:
    if timeframe not in TIMEFRAME_SECONDS:
        raise ValueError(f"unite de temps inconnue: {timeframe}")
    return TIMEFRAME_SECONDS[timeframe]


def resample(candles: list[Candle], source_tf: str, target_tf: str) -> list[Candle]:
    """Agrege des bougies vers une unite de temps superieure.

    Permet de n'appeler qu'une seule fois l'API en M1 et d'en deduire
    M5 / M15 / H1 localement : moins de requetes, plus de reactivite.
    """
    src, dst = tf_seconds(source_tf), tf_seconds(target_tf)
    if dst == src:
        return list(candles)
    if dst < src or dst % src != 0:
        raise ValueError(f"agregation impossible de {source_tf} vers {target_tf}")

    out: list[Candle] = []
    bucket: Optional[Candle] = None
    bucket_start = -1
    for c in candles:
        start = int(c.ts // dst) * dst
        if bucket is None or start != bucket_start:
            if bucket is not None:
                out.append(bucket)
            bucket = Candle(start, c.open, c.high, c.low, c.close, c.volume)
            bucket_start = start
        else:
            bucket.high = max(bucket.high, c.high)
            bucket.low = min(bucket.low, c.low)
            bucket.close = c.close
            bucket.volume += c.volume
    if bucket is not None:
        out.append(bucket)
    return out
