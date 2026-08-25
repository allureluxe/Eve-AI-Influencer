"""Sources de prix concretes.

Le robot ne depend jamais d'un seul fournisseur : le registre teste les
sources dans l'ordre et bascule automatiquement a la premiere qui repond.
Les sources sans cle API (Yahoo, Binance, Stooq) assurent le fonctionnement
par defaut ; les sources a cle (TwelveData, AlphaVantage, Finnhub, Polygon,
MetalPrice) s'activent seules des que la variable d'environnement existe.
"""
from __future__ import annotations

import csv
import hashlib
import io
import logging
import os
import random
import time
from typing import Optional

from ..core import Candle, Tick
from ..universe import CATALOGUE_CRYPTO
from .base import (
    SymbolNotSupported,
    PriceProvider,
    ProviderCapabilities,
    ProviderError,
    http_get,
    resample,
    tf_seconds,
)

logger = logging.getLogger(__name__)


def _flottant(valeur) -> Optional[float]:
    """Convertit si possible, rend None sinon.

    None et 0.0 ne veulent pas dire la meme chose sur une taille de
    carnet : 0.0 signifie « plus personne a ce prix », None signifie
    « la source ne le dit pas ». Les confondre inventerait un
    desequilibre maximal la ou il n'y a qu'une donnee manquante.
    """
    if valeur is None or valeur == "":
        return None
    try:
        return float(valeur)
    except (TypeError, ValueError):
        return None


# ==========================================================================
# Yahoo Finance - gratuit, sans cle, intraday 1m/5m/15m
# ==========================================================================
class YahooProvider(PriceProvider):
    """Yahoo Finance : couvre l'or (GC=F), le forex, les cryptos et les indices macro."""

    name = "yahoo"
    capabilities = ProviderCapabilities(rate_limit_per_min=60)

    MAP = {
        "XAUUSD": "GC=F", "XAGUSD": "SI=F",
        "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "USDJPY": "USDJPY=X",
        "AUDUSD": "AUDUSD=X", "USDCAD": "USDCAD=X", "USDCHF": "USDCHF=X",
        "NZDUSD": "NZDUSD=X",
        "BTCUSD": "BTC-USD", "ETHUSD": "ETH-USD", "SOLUSD": "SOL-USD",
        "XRPUSD": "XRP-USD", "DOGEUSD": "DOGE-USD",
        "DXY": "DX-Y.NYB", "VIX": "^VIX", "SPX": "^GSPC", "US10Y": "^TNX",
        "WTI": "CL=F", "GLD": "GLD",
    }
    INTERVALS = {"M1": "1m", "M5": "5m", "M15": "15m", "M30": "30m",
                 "H1": "60m", "H4": "1h", "D1": "1d"}

    def symbol_for(self, symbol: str, asset_class: str) -> Optional[str]:
        return self.MAP.get(symbol.upper())

    def fetch_candles(self, symbol: str, asset_class: str, timeframe: str, limit: int) -> list[Candle]:
        code = self.symbol_for(symbol, asset_class)
        if not code:
            raise SymbolNotSupported(f"{self.name}: {symbol} non cote ici")
        interval = self.INTERVALS.get(timeframe)
        if interval is None:
            raise ProviderError(f"{self.name}: unite de temps non supportee {timeframe}")

        # Yahoo limite l'historique intraday : on demande la plus petite plage suffisante.
        needed = tf_seconds(timeframe) * (limit + 5)
        if timeframe == "M1":
            rng = "1d" if needed <= 86400 else "7d"
        elif needed <= 5 * 86400:
            rng = "5d"
        elif needed <= 30 * 86400:
            rng = "1mo"
        elif needed <= 90 * 86400:
            rng = "3mo"
        else:
            rng = "1y"

        self.throttle()
        data = http_get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{code}",
            params={"interval": interval, "range": rng, "includePrePost": "false"},
        )
        try:
            result = data["chart"]["result"][0]
            stamps = result["timestamp"]
            q = result["indicators"]["quote"][0]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError(f"{self.name}: reponse inattendue ({exc})") from exc

        out: list[Candle] = []
        for i, ts in enumerate(stamps):
            o, h, l, c = q.get("open")[i], q.get("high")[i], q.get("low")[i], q.get("close")[i]
            v = (q.get("volume") or [None] * len(stamps))[i]
            if None in (o, h, l, c):
                continue
            out.append(Candle(float(ts), float(o), float(h), float(l), float(c), float(v or 0.0)))

        if timeframe == "H4" and out:
            out = resample(out, "H1", "H4")
        return out[-limit:]


# ==========================================================================
# Binance - gratuit, sans cle, ideal pour les cryptos 24/7
# ==========================================================================
class BinanceProvider(PriceProvider):
    """Binance : donnees crypto de reference, granularite a la minute, sans cle."""

    name = "binance"
    capabilities = ProviderCapabilities(asset_classes=("crypto",), rate_limit_per_min=120)

    # Le catalogue est celui de l'univers, pas une seconde liste tenue a la
    # main : une source de prix plus etroite que les instruments reellement
    # negociables produit des trous silencieux, et une liste divergente se
    # remarque des qu'on ajoute un actif.
    #
    # La devise de cotation suit celle de l'execution (BINANCE_QUOTE_ASSET) :
    # lire les prix sur BTC/USDT tout en achetant sur BTC/USDC introduirait un
    # ecart entre les niveaux calcules et ceux envoyes a la plateforme.
    ACTIFS = {f"{actif}USD": actif for actif in CATALOGUE_CRYPTO}
    INTERVALS = {"M1": "1m", "M3": "3m", "M5": "5m", "M15": "15m",
                 "M30": "30m", "H1": "1h", "H4": "4h", "D1": "1d"}

    @property
    def devise(self) -> str:
        return os.getenv("BINANCE_QUOTE_ASSET", "USDT").upper()

    def symbol_for(self, symbol: str, asset_class: str) -> Optional[str]:
        actif = self.ACTIFS.get(symbol.upper())
        return f"{actif}{self.devise}" if actif else None

    def fetch_candles(self, symbol: str, asset_class: str, timeframe: str, limit: int) -> list[Candle]:
        code = self.symbol_for(symbol, asset_class)
        if not code:
            raise SymbolNotSupported(f"{self.name}: {symbol} non cote ici")
        interval = self.INTERVALS.get(timeframe)
        if not interval:
            raise ProviderError(f"{self.name}: unite de temps non supportee {timeframe}")
        self.throttle()
        try:
            rows = http_get(
                "https://api.binance.com/api/v3/klines",
                params={"symbol": code, "interval": interval, "limit": min(limit, 1000)},
            )
        except ProviderError as exc:
            # Binance repond 400 « Invalid symbol » pour une paire absente
            # dans cette devise de cotation. Ce n'est pas une panne : la
            # source reste saine pour les 80 autres instruments.
            if getattr(exc, "status", None) == 400:
                raise SymbolNotSupported(
                    f"{self.name}: {symbol} non cote en {self.devise}") from exc
            raise
        if not isinstance(rows, list):
            raise ProviderError(f"{self.name}: reponse inattendue")
        return [
            Candle(float(r[0]) / 1000.0, float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5]))
            for r in rows
        ]

    def fetch_tick(self, symbol: str, asset_class: str) -> Optional[Tick]:
        code = self.symbol_for(symbol, asset_class)
        if not code:
            return None
        self.throttle()
        try:
            data = http_get("https://api.binance.com/api/v3/ticker/bookTicker",
                            params={"symbol": code})
        except ProviderError as exc:
            if getattr(exc, "status", None) == 400:
                raise SymbolNotSupported(
                    f"{self.name}: {symbol} non cote en {self.devise}") from exc
            raise
        return Tick(time.time(), float(data["bidPrice"]), float(data["askPrice"]))



# ==========================================================================
# Bitvavo - lieu d'execution europeen, cotation en EUR, sans cle
# ==========================================================================
class BitvavoProvider(PriceProvider):
    """Bitvavo : la source qui cote dans la meme devise que les ordres.

    Elle est prioritaire sur les autres sources crypto quand le robot
    execute sur Bitvavo : les niveaux calcules et les ordres envoyes
    doivent vivre sur la meme echelle de prix. Les endpoints publics ne
    demandent aucune cle.
    """

    name = "bitvavo"
    capabilities = ProviderCapabilities(asset_classes=("crypto",), rate_limit_per_min=120)
    devise_crypto = os.getenv("BITVAVO_QUOTE_ASSET", "EUR").upper()

    # Meme catalogue que l'univers et que l'execution : une liste tenue a la
    # main ici divergerait des le premier actif ajoute.
    ACTIFS = {f"{actif}USD": actif for actif in CATALOGUE_CRYPTO}
    # Bitvavo n'expose pas M3 : il est reconstruit a partir de la minute.
    INTERVALS = {"M1": "1m", "M5": "5m", "M15": "15m", "M30": "30m",
                 "H1": "1h", "H4": "4h", "D1": "1d"}

    @property
    def devise(self) -> str:
        return os.getenv("BITVAVO_QUOTE_ASSET", "EUR").upper()

    def symbol_for(self, symbol: str, asset_class: str) -> Optional[str]:
        actif = self.ACTIFS.get(symbol.upper())
        return f"{actif}-{self.devise}" if actif else None

    def fetch_candles(self, symbol: str, asset_class: str, timeframe: str,
                      limit: int) -> list[Candle]:
        code = self.symbol_for(symbol, asset_class)
        if not code:
            raise SymbolNotSupported(f"{self.name}: {symbol} non cote ici")

        interval = self.INTERVALS.get(timeframe)
        source_tf = timeframe
        if not interval:
            # M3 se deduit de trois bougies M1 ; toute autre unite absente du
            # tableau est un vrai defaut de configuration.
            if timeframe != "M3":
                raise ProviderError(f"{self.name}: unite de temps non supportee {timeframe}")
            interval, source_tf = "1m", "M1"

        besoin = limit * 3 if source_tf != timeframe else limit
        self.throttle()
        try:
            rows = http_get(f"https://api.bitvavo.com/v2/{code}/candles",
                            params={"interval": interval, "limit": min(besoin, 1440)})
        except ProviderError as exc:
            # Bitvavo repond 400 pour un marche qu'il ne liste pas. Ce n'est
            # pas une panne : la source reste saine pour tous les autres.
            if getattr(exc, "status", None) == 400:
                raise SymbolNotSupported(
                    f"{self.name}: {symbol} non cote en {self.devise}") from exc
            raise
        if not isinstance(rows, list):
            raise ProviderError(f"{self.name}: reponse inattendue")

        # Bitvavo renvoie la bougie la plus RECENTE en premier ; tout le
        # robot raisonne dans l'ordre chronologique.
        bougies = [
            Candle(float(r[0]) / 1000.0, float(r[1]), float(r[2]),
                   float(r[3]), float(r[4]), float(r[5]))
            for r in reversed(rows)
        ]
        if source_tf != timeframe:
            bougies = resample(bougies, source_tf, timeframe)
        return bougies

    def fetch_tick(self, symbol: str, asset_class: str) -> Optional[Tick]:
        code = self.symbol_for(symbol, asset_class)
        if not code:
            return None
        self.throttle()
        try:
            data = http_get("https://api.bitvavo.com/v2/ticker/book",
                            params={"market": code})
        except ProviderError as exc:
            if getattr(exc, "status", None) == 400:
                raise SymbolNotSupported(
                    f"{self.name}: {symbol} non cote en {self.devise}") from exc
            raise
        try:
            # Les tailles arrivent dans la meme reponse : les lire ne coute
            # aucun appel de plus.
            return Tick(time.time(), float(data["bid"]), float(data["ask"]),
                        _flottant(data.get("bidSize")), _flottant(data.get("askSize")))
        except (KeyError, TypeError, ValueError):
            return None



# ==========================================================================
# OKX - lieu d'execution europeen (MiCA/MFSA), cotation en EUR, sans cle
# ==========================================================================
class OkxProvider(PriceProvider):
    """OKX : source alignee sur le lieu d'execution, endpoints publics.

    Deux particularites de l'API v5, toutes deux traitees ici :
      - une reponse HTTP 200 peut porter un echec, c'est `code` qui fait foi ;
      - la derniere bougie renvoyee n'est pas cloturee (`confirm` = 0). La
        garder ferait decider le robot sur une bougie encore en train de
        bouger, ce qui invente des signaux qui disparaissent ensuite.
    """

    name = "okx"
    capabilities = ProviderCapabilities(asset_classes=("crypto",), rate_limit_per_min=120)
    devise_crypto = os.getenv("OKX_QUOTE_ASSET", "EUR").upper()

    ACTIFS = {f"{actif}USD": actif for actif in CATALOGUE_CRYPTO}
    # Attention aux majuscules : OKX ecrit les minutes en minuscule et les
    # heures et jours en MAJUSCULE. « 4h » est refuse, « 4H » accepte.
    INTERVALS = {"M1": "1m", "M3": "3m", "M5": "5m", "M15": "15m",
                 "M30": "30m", "H1": "1H", "H4": "4H", "D1": "1D"}

    BASE = os.getenv("OKX_API_URL", "https://www.okx.com").rstrip("/")

    @property
    def devise(self) -> str:
        return os.getenv("OKX_QUOTE_ASSET", "EUR").upper()

    def symbol_for(self, symbol: str, asset_class: str) -> Optional[str]:
        actif = self.ACTIFS.get(symbol.upper())
        return f"{actif}-{self.devise}" if actif else None

    def _lire(self, chemin: str, params: dict) -> list:
        """Appel public v5, avec validation de l'enveloppe."""
        reponse = http_get(f"{self.BASE}{chemin}", params=params)
        if not isinstance(reponse, dict):
            raise ProviderError(f"{self.name}: reponse inattendue")
        code = str(reponse.get("code", ""))
        if code != "0":
            message = str(reponse.get("msg", ""))[:120]
            # 51001 : instrument inconnu. Ce n'est pas une panne, la source
            # reste saine pour tous les autres marches.
            if code in ("51001", "51000"):
                raise SymbolNotSupported(f"{self.name}: {message or code}")
            raise ProviderError(f"{self.name}: [{code}] {message}")
        return reponse.get("data") or []

    # Plafond impose par OKX sur une reponse de bougies.
    PAR_PAGE = 300
    # Garde-fou : au-dela, on tirerait des centaines de requetes par
    # instrument et on se ferait limiter avant la fin du scan.
    PAGES_MAX = 12

    def _paginer(self, code: str, interval: str, voulu: int) -> list:
        """Remonte l'historique page par page, du plus recent au plus ancien.

        `after` demande a OKX les enregistrements ANTERIEURS a un horodatage.
        On repart donc du plus ancien recu a chaque tour. La boucle s'arrete
        des qu'une page revient vide, plus courte que le plafond, ou ne
        recule plus — trois facons pour l'historique de s'epuiser, et sans
        elles on tournerait indefiniment.
        """
        collecte: list = []
        curseur = ""
        vus: set[str] = set()
        for _ in range(self.PAGES_MAX):
            if len(collecte) >= voulu:
                break
            params = {"instId": code, "bar": interval,
                      "limit": min(self.PAR_PAGE, max(1, voulu - len(collecte)))}
            if curseur:
                params["after"] = curseur
            self.throttle()
            try:
                page = self._lire("/api/v5/market/candles", params)
            except ProviderError as exc:
                if getattr(exc, "status", None) == 400:
                    raise SymbolNotSupported(
                        f"{self.name}: {code} non cote") from exc
                if collecte:
                    break          # on garde ce qu'on a plutot que tout perdre
                raise
            if not page:
                break
            nouveaux = [r for r in page if r and str(r[0]) not in vus]
            if not nouveaux:
                break
            vus.update(str(r[0]) for r in nouveaux)
            collecte.extend(nouveaux)
            plus_ancien = min(int(r[0]) for r in nouveaux)
            if curseur and int(curseur) <= plus_ancien:
                break
            curseur = str(plus_ancien)
            if len(page) < params["limit"]:
                break
        return collecte

    def fetch_candles(self, symbol: str, asset_class: str, timeframe: str,
                      limit: int) -> list[Candle]:
        code = self.symbol_for(symbol, asset_class)
        if not code:
            raise SymbolNotSupported(f"{self.name}: {symbol} non cote ici")
        interval = self.INTERVALS.get(timeframe)
        if not interval:
            raise ProviderError(f"{self.name}: unite de temps non supportee {timeframe}")

        # OKX plafonne chaque reponse a 300 bougies. Sans pagination, un
        # backtest demandant 1500 bougies en recevrait 300 et mesurerait
        # douze jours en croyant en mesurer deux mois — un echantillon trop
        # court pour distinguer une strategie du hasard.
        rows = self._paginer(code, interval, limit + 1)

        bougies = []
        # OKX renvoie la plus recente en premier ; le robot raisonne dans
        # l'ordre chronologique.
        for r in reversed(rows):
            # `confirm` vaut « 1 » quand la bougie est cloturee. Le champ
            # peut manquer sur d'anciennes reponses : on ne l'exige pas.
            if len(r) > 8 and str(r[8]) == "0":
                continue
            bougies.append(Candle(float(r[0]) / 1000.0, float(r[1]), float(r[2]),
                                  float(r[3]), float(r[4]), float(r[5])))
        return bougies

    def fetch_tick(self, symbol: str, asset_class: str) -> Optional[Tick]:
        code = self.symbol_for(symbol, asset_class)
        if not code:
            return None
        self.throttle()
        data = self._lire("/api/v5/market/ticker", {"instId": code})
        if not data:
            return None
        try:
            ligne = data[0]
            return Tick(time.time(), float(ligne["bidPx"]), float(ligne["askPx"]),
                        _flottant(ligne.get("bidSz")), _flottant(ligne.get("askSz")))
        except (KeyError, TypeError, ValueError):
            return None


# ==========================================================================
# Sources a cle API (activation automatique si la variable existe)
# ==========================================================================
class TwelveDataProvider(PriceProvider):
    """TwelveData : XAU/USD natif, forex et crypto. Cle : TWELVEDATA_API_KEY."""

    name = "twelvedata"
    capabilities = ProviderCapabilities(requires_key=True, rate_limit_per_min=8)

    INTERVALS = {"M1": "1min", "M5": "5min", "M15": "15min", "M30": "30min",
                 "H1": "1h", "H4": "4h", "D1": "1day"}

    def __init__(self) -> None:
        super().__init__()
        self.key = os.getenv("TWELVEDATA_API_KEY", "")

    def available(self) -> bool:
        return bool(self.key)

    def symbol_for(self, symbol: str, asset_class: str) -> Optional[str]:
        s = symbol.upper()
        if asset_class == "crypto":
            return f"{s[:-3]}/USD"
        if len(s) == 6:
            return f"{s[:3]}/{s[3:]}"
        return s

    def fetch_candles(self, symbol: str, asset_class: str, timeframe: str, limit: int) -> list[Candle]:
        if not self.key:
            raise ProviderError(f"{self.name}: cle absente")
        interval = self.INTERVALS.get(timeframe)
        if not interval:
            raise ProviderError(f"{self.name}: unite de temps non supportee {timeframe}")
        self.throttle()
        data = http_get(
            "https://api.twelvedata.com/time_series",
            params={"symbol": self.symbol_for(symbol, asset_class), "interval": interval,
                    "outputsize": min(limit, 5000), "apikey": self.key,
                    "order": "ASC", "format": "JSON"},
        )
        if data.get("status") == "error":
            raise ProviderError(f"{self.name}: {data.get('message')}")
        out = []
        for row in data.get("values", []):
            stamp = row["datetime"]
            fmt = "%Y-%m-%d %H:%M:%S" if len(stamp) > 10 else "%Y-%m-%d"
            ts = time.mktime(time.strptime(stamp[:19].replace("T", " "), fmt))
            out.append(Candle(ts, float(row["open"]), float(row["high"]),
                              float(row["low"]), float(row["close"]), float(row.get("volume") or 0)))
        return out[-limit:]


class AlphaVantageProvider(PriceProvider):
    """AlphaVantage : forex et crypto intraday. Cle : ALPHAVANTAGE_API_KEY."""

    name = "alphavantage"
    capabilities = ProviderCapabilities(requires_key=True, rate_limit_per_min=5)

    INTERVALS = {"M1": "1min", "M5": "5min", "M15": "15min", "M30": "30min", "H1": "60min"}

    def __init__(self) -> None:
        super().__init__()
        self.key = os.getenv("ALPHAVANTAGE_API_KEY", "")

    def available(self) -> bool:
        return bool(self.key)

    def symbol_for(self, symbol: str, asset_class: str) -> Optional[str]:
        return symbol.upper()

    def fetch_candles(self, symbol: str, asset_class: str, timeframe: str, limit: int) -> list[Candle]:
        if not self.key:
            raise ProviderError(f"{self.name}: cle absente")
        interval = self.INTERVALS.get(timeframe)
        if not interval:
            raise ProviderError(f"{self.name}: unite de temps non supportee {timeframe}")
        s = symbol.upper()
        base, quote = (s[:-3], s[-3:]) if len(s) >= 6 else (s, "USD")
        func = "CRYPTO_INTRADAY" if asset_class == "crypto" else "FX_INTRADAY"
        params = {"function": func, "interval": interval, "apikey": self.key, "outputsize": "compact"}
        if func == "FX_INTRADAY":
            params.update({"from_symbol": base, "to_symbol": quote})
        else:
            params.update({"symbol": base, "market": quote})
        self.throttle()
        data = http_get("https://www.alphavantage.co/query", params=params)
        series_key = next((k for k in data if "Time Series" in k), None)
        if not series_key:
            raise ProviderError(f"{self.name}: {data.get('Note') or data.get('Error Message') or 'reponse vide'}")
        out = []
        for stamp, row in sorted(data[series_key].items()):
            ts = time.mktime(time.strptime(stamp[:19], "%Y-%m-%d %H:%M:%S"))
            vals = {k.split(". ")[-1]: v for k, v in row.items()}
            out.append(Candle(ts, float(vals["open"]), float(vals["high"]),
                              float(vals["low"]), float(vals["close"]), float(vals.get("volume") or 0)))
        return out[-limit:]


class FinnhubProvider(PriceProvider):
    """Finnhub : forex et crypto + calendrier economique. Cle : FINNHUB_API_KEY."""

    name = "finnhub"
    capabilities = ProviderCapabilities(requires_key=True, rate_limit_per_min=30)

    RES = {"M1": "1", "M5": "5", "M15": "15", "M30": "30", "H1": "60", "D1": "D"}

    def __init__(self) -> None:
        super().__init__()
        self.key = os.getenv("FINNHUB_API_KEY", "")

    def available(self) -> bool:
        return bool(self.key)

    def symbol_for(self, symbol: str, asset_class: str) -> Optional[str]:
        s = symbol.upper()
        if asset_class == "crypto":
            return f"BINANCE:{s[:-3]}USDT"
        return f"OANDA:{s[:3]}_{s[3:]}"

    def fetch_candles(self, symbol: str, asset_class: str, timeframe: str, limit: int) -> list[Candle]:
        if not self.key:
            raise ProviderError(f"{self.name}: cle absente")
        res = self.RES.get(timeframe)
        if not res:
            raise ProviderError(f"{self.name}: unite de temps non supportee {timeframe}")
        now = int(time.time())
        frm = now - tf_seconds(timeframe) * (limit + 10)
        url = ("https://finnhub.io/api/v1/crypto/candle" if asset_class == "crypto"
               else "https://finnhub.io/api/v1/forex/candle")
        self.throttle()
        data = http_get(url, params={"symbol": self.symbol_for(symbol, asset_class),
                                     "resolution": res, "from": frm, "to": now, "token": self.key})
        if data.get("s") != "ok":
            raise ProviderError(f"{self.name}: statut {data.get('s')}")
        vols = data.get("v") or [0] * len(data["t"])
        return [
            Candle(float(t), float(o), float(h), float(l), float(c), float(v))
            for t, o, h, l, c, v in zip(data["t"], data["o"], data["h"], data["l"], data["c"], vols)
        ][-limit:]


class PolygonProvider(PriceProvider):
    """Polygon.io : agregats forex/crypto. Cle : POLYGON_API_KEY."""

    name = "polygon"
    capabilities = ProviderCapabilities(requires_key=True, rate_limit_per_min=5)

    MULT = {"M1": (1, "minute"), "M5": (5, "minute"), "M15": (15, "minute"),
            "M30": (30, "minute"), "H1": (1, "hour"), "H4": (4, "hour"), "D1": (1, "day")}

    def __init__(self) -> None:
        super().__init__()
        self.key = os.getenv("POLYGON_API_KEY", "")

    def available(self) -> bool:
        return bool(self.key)

    def symbol_for(self, symbol: str, asset_class: str) -> Optional[str]:
        s = symbol.upper()
        return f"X:{s[:-3]}USD" if asset_class == "crypto" else f"C:{s}"

    def fetch_candles(self, symbol: str, asset_class: str, timeframe: str, limit: int) -> list[Candle]:
        if not self.key:
            raise ProviderError(f"{self.name}: cle absente")
        mult = self.MULT.get(timeframe)
        if not mult:
            raise ProviderError(f"{self.name}: unite de temps non supportee {timeframe}")
        n, unit = mult
        end = int(time.time() * 1000)
        start = end - tf_seconds(timeframe) * (limit + 10) * 1000
        self.throttle()
        data = http_get(
            f"https://api.polygon.io/v2/aggs/ticker/{self.symbol_for(symbol, asset_class)}"
            f"/range/{n}/{unit}/{start}/{end}",
            params={"adjusted": "true", "sort": "asc", "limit": min(limit + 10, 50000), "apiKey": self.key},
        )
        if data.get("status") not in ("OK", "DELAYED") or "results" not in data:
            raise ProviderError(f"{self.name}: {data.get('error') or data.get('status')}")
        return [
            Candle(float(r["t"]) / 1000.0, float(r["o"]), float(r["h"]),
                   float(r["l"]), float(r["c"]), float(r.get("v", 0)))
            for r in data["results"]
        ][-limit:]


class MetalPriceProvider(PriceProvider):
    """MetalpriceAPI : cotation spot de l'or/argent. Cle : METALPRICE_API_KEY."""

    name = "metalprice"
    capabilities = ProviderCapabilities(intraday=False, asset_classes=("metal",),
                                        requires_key=True, rate_limit_per_min=5)

    def __init__(self) -> None:
        super().__init__()
        self.key = os.getenv("METALPRICE_API_KEY", "")

    def available(self) -> bool:
        return bool(self.key)

    def symbol_for(self, symbol: str, asset_class: str) -> Optional[str]:
        return {"XAUUSD": "XAU", "XAGUSD": "XAG"}.get(symbol.upper())

    def fetch_candles(self, symbol: str, asset_class: str, timeframe: str, limit: int) -> list[Candle]:
        raise ProviderError(f"{self.name}: source de cotation seulement, pas d'historique")

    def fetch_tick(self, symbol: str, asset_class: str) -> Optional[Tick]:
        code = self.symbol_for(symbol, asset_class)
        if not code or not self.key:
            return None
        self.throttle()
        data = http_get("https://api.metalpriceapi.com/v1/latest",
                        params={"api_key": self.key, "base": "USD", "currencies": code})
        rate = (data.get("rates") or {}).get(code)
        if not rate:
            return None
        price = 1.0 / float(rate)     # l'API cote USD -> XAU, on inverse
        half = price * 2e-5
        return Tick(time.time(), price - half, price + half)


class StooqProvider(PriceProvider):
    """Stooq : historique journalier gratuit, utile pour le biais de fond."""

    name = "stooq"
    capabilities = ProviderCapabilities(intraday=False, rate_limit_per_min=20)

    MAP = {"XAUUSD": "xauusd", "XAGUSD": "xagusd", "EURUSD": "eurusd",
           "GBPUSD": "gbpusd", "USDJPY": "usdjpy", "AUDUSD": "audusd",
           "USDCAD": "usdcad", "BTCUSD": "btcusd", "ETHUSD": "ethusd",
           "DXY": "dx.f", "SPX": "^spx"}

    def symbol_for(self, symbol: str, asset_class: str) -> Optional[str]:
        return self.MAP.get(symbol.upper())

    def fetch_candles(self, symbol: str, asset_class: str, timeframe: str, limit: int) -> list[Candle]:
        if timeframe != "D1":
            raise ProviderError(f"{self.name}: uniquement en journalier")
        code = self.symbol_for(symbol, asset_class)
        if not code:
            raise ProviderError(f"{self.name}: symbole non supporte {symbol}")
        self.throttle()
        raw = http_get("https://stooq.com/q/d/l/", params={"s": code, "i": "d"}, as_json=False)
        out = []
        for row in csv.DictReader(io.StringIO(raw)):
            try:
                ts = time.mktime(time.strptime(row["Date"], "%Y-%m-%d"))
                out.append(Candle(ts, float(row["Open"]), float(row["High"]),
                                  float(row["Low"]), float(row["Close"]), float(row.get("Volume") or 0)))
            except (ValueError, KeyError, TypeError):
                continue
        if not out:
            raise ProviderError(f"{self.name}: aucune donnee")
        return out[-limit:]


class MoonXProvider(PriceProvider):
    """Prix issus de MoonX : la source la plus fidele, c'est le lieu d'execution.

    Configuration : MOONX_API_URL, MOONX_API_KEY. Les routes sont
    surchargeables (MOONX_CANDLES_PATH / MOONX_TICK_PATH) pour coller a
    l'API sans modifier le code.
    """

    name = "moonx"
    capabilities = ProviderCapabilities(requires_key=True, rate_limit_per_min=60)

    def __init__(self) -> None:
        super().__init__()
        self.base = os.getenv("MOONX_API_URL", "").rstrip("/")
        self.key = os.getenv("MOONX_API_KEY", "")
        self.candles_path = os.getenv("MOONX_CANDLES_PATH", "/api/v1/market/candles")
        self.tick_path = os.getenv("MOONX_TICK_PATH", "/api/v1/market/ticker")

    def available(self) -> bool:
        return bool(self.base and self.key)

    def symbol_for(self, symbol: str, asset_class: str) -> Optional[str]:
        return os.getenv(f"MOONX_SYMBOL_{symbol.upper()}", symbol.upper())

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}

    def fetch_candles(self, symbol: str, asset_class: str, timeframe: str, limit: int) -> list[Candle]:
        if not self.available():
            raise ProviderError(f"{self.name}: non configure")
        self.throttle()
        data = http_get(f"{self.base}{self.candles_path}",
                        params={"symbol": self.symbol_for(symbol, asset_class),
                                "interval": timeframe.lower(), "limit": limit},
                        headers=self._headers())
        rows = data.get("data", data) if isinstance(data, dict) else data
        if not isinstance(rows, list):
            raise ProviderError(f"{self.name}: reponse inattendue")
        out = []
        for r in rows:
            if isinstance(r, dict):
                ts = float(r.get("t") or r.get("time") or r.get("timestamp") or 0)
                out.append(Candle(ts / 1000.0 if ts > 1e11 else ts,
                                  float(r.get("o") or r["open"]), float(r.get("h") or r["high"]),
                                  float(r.get("l") or r["low"]), float(r.get("c") or r["close"]),
                                  float(r.get("v") or r.get("volume") or 0)))
            else:
                ts = float(r[0])
                out.append(Candle(ts / 1000.0 if ts > 1e11 else ts, float(r[1]), float(r[2]),
                                  float(r[3]), float(r[4]), float(r[5]) if len(r) > 5 else 0.0))
        return out[-limit:]

    def fetch_tick(self, symbol: str, asset_class: str) -> Optional[Tick]:
        if not self.available():
            return None
        self.throttle()
        data = http_get(f"{self.base}{self.tick_path}",
                        params={"symbol": self.symbol_for(symbol, asset_class)},
                        headers=self._headers())
        d = data.get("data", data) if isinstance(data, dict) else {}
        bid, ask = d.get("bid") or d.get("bidPrice"), d.get("ask") or d.get("askPrice")
        if bid is None or ask is None:
            last = d.get("last") or d.get("price") or d.get("c")
            if last is None:
                return None
            price = float(last)
            half = price * 1e-4
            return Tick(time.time(), price - half, price + half)
        return Tick(time.time(), float(bid), float(ask))


# ==========================================================================
# Source synthetique : backtest reproductible et mode hors ligne
# ==========================================================================
class SyntheticProvider(PriceProvider):
    """Genere un marche realiste (tendance, volatilite, chocs) sans reseau.

    Sert au backtest reproductible et a la validation du pipeline complet.
    Ne doit jamais servir en execution reelle : le moteur le refuse en live.
    """

    name = "synthetic"
    capabilities = ProviderCapabilities(rate_limit_per_min=1000000)

    BASE_PRICES = {"XAUUSD": 2650.0, "XAGUSD": 31.0, "EURUSD": 1.085, "GBPUSD": 1.27,
                   "USDJPY": 152.0, "AUDUSD": 0.655, "USDCAD": 1.38,
                   "BTCUSD": 68000.0, "ETHUSD": 3300.0, "SOLUSD": 165.0, "XRPUSD": 0.62}

    def __init__(self, seed: int = 42) -> None:
        super().__init__()
        self.seed = seed

    def symbol_for(self, symbol: str, asset_class: str) -> Optional[str]:
        return symbol.upper()

    @staticmethod
    def _seed_for(seed: int, symbol: str, timeframe: str) -> int:
        """Graine deterministe.

        `hash()` de Python est randomise a chaque processus (PYTHONHASHSEED) :
        l'utiliser rendrait chaque backtest different du precedent sur les
        memes parametres. On derive donc la graine d'un hachage stable.
        """
        raw = f"{seed}|{symbol.upper()}|{timeframe}".encode("utf-8")
        return int.from_bytes(hashlib.sha256(raw).digest()[:4], "big")

    def fetch_candles(self, symbol: str, asset_class: str, timeframe: str, limit: int) -> list[Candle]:
        rng = random.Random(self._seed_for(self.seed, symbol, timeframe))
        price = self.BASE_PRICES.get(symbol.upper(), 100.0)
        vol = price * (0.0012 if asset_class == "crypto" else 0.0004)
        step = tf_seconds(timeframe)
        # Ancrage sur l'heure ronde courante : les bougies restent stables
        # tant qu'on reste dans la meme heure, ce qui rend deux executions
        # successives d'un backtest comparables.
        now = int(time.time() // 3600) * 3600
        out: list[Candle] = []
        drift = rng.uniform(-0.4, 0.4) * vol
        for i in range(limit, 0, -1):
            if rng.random() < 0.02:                 # changement de regime
                drift = rng.uniform(-0.6, 0.6) * vol
            shock = rng.gauss(0, vol) * (4.0 if rng.random() < 0.01 else 1.0)
            o = price
            price = max(price * 0.5, price + drift + shock)
            c = price
            hi = max(o, c) + abs(rng.gauss(0, vol * 0.6))
            lo = min(o, c) - abs(rng.gauss(0, vol * 0.6))
            out.append(Candle(now - i * step, o, hi, lo, c, rng.uniform(50, 500)))
        return out
