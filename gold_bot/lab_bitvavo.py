"""Historique Bitvavo dedie au Strategy Lab.

Le labo travaille sur les marches EUR actuellement en trading chez Bitvavo,
sans volume/spread arbitraires, et conserve un cache local des bougies.
"""
from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

from .core import Candle
from .datasources.base import http_get, tf_seconds
from .universe import Universe, ajouter_cryptos, instrument_crypto

logger = logging.getLogger(__name__)

BITVAVO = "https://api.bitvavo.com/v2"
CACHE = Path(os.getenv("GB_LAB_BITVAVO_CACHE", "data/lab-bitvavo"))
ONE_YEAR_DAYS = int(os.getenv("GB_LAB_HISTORY_DAYS", "365"))
LIMIT = 1440
INTERVALS = {"M1": "1m", "M3": "3m", "M5": "5m", "M15": "15m",
             "M30": "30m", "H1": "1h", "H4": "4h", "D1": "1d"}
def _align(ts: float, seconds: int) -> int:
    return int(ts // seconds) * seconds


def bitvavo_markets() -> list[dict]:
    rows = http_get(f"{BITVAVO}/markets")
    if not isinstance(rows, list):
        raise RuntimeError("Bitvavo /markets: réponse inattendue")
    quote = os.getenv("BITVAVO_QUOTE_ASSET", "EUR").upper()
    return [m for m in rows
            if isinstance(m, dict)
            and m.get("quote") == quote
            and m.get("status") == "trading"
            and m.get("base") not in (None, "", quote)]


def lab_universe(markets: list[dict]) -> list:
    groupes = {str(m["base"]).upper(): "crypto_alt" for m in markets}
    ajouter_cryptos(groupes)
    return [instrument_crypto(base, "crypto_alt")
            for base in sorted(groupes)]
def _market_file(market: str, timeframe: str) -> Path:
    safe = market.replace("/", "_").replace("-", "_")
    return CACHE / safe / f"{timeframe}.json"


def _load_cache(path: Path) -> list[Candle]:
    if not path.exists():
        return []
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
        return [Candle(float(r[0]), float(r[1]), float(r[2]), float(r[3]),
                       float(r[4]), float(r[5])) for r in rows]
    except Exception as exc:
        logger.warning("cache Bitvavo illisible %s: %s", path, str(exc)[:100])
        return []


def _save_cache(path: Path, candles: list[Candle]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps([[c.ts, c.open, c.high, c.low, c.close, c.volume]
                               for c in candles], separators=(",", ":")), encoding="utf-8")
    tmp.replace(path)
def _fetch_range(market: str, timeframe: str, start: int, end: int) -> list[Candle]:
    interval = INTERVALS[timeframe]
    step = tf_seconds(timeframe) * 1000
    out: list[Candle] = []
    cursor = _align(start / 1000, tf_seconds(timeframe)) * 1000
    final = _align(end / 1000, tf_seconds(timeframe)) * 1000
    while cursor <= final:
        window_end = min(final, cursor + step * (LIMIT - 1))
        rows = http_get(f"{BITVAVO}/{market}/candles", params={
            "interval": interval, "start": cursor, "end": window_end, "limit": LIMIT})
        if not isinstance(rows, list):
            raise RuntimeError(f"Bitvavo candles {market} {timeframe}: réponse inattendue")
        got = []
        for r in rows:
            if len(r) < 6:
                continue
            got.append(Candle(float(r[0]) / 1000, float(r[1]), float(r[2]),
                              float(r[3]), float(r[4]), float(r[5])))
        if not got:
            cursor = window_end + step
            continue
        got.sort(key=lambda c: c.ts)
        out.extend(got)
        last = int(got[-1].ts * 1000)
        cursor = max(cursor + step, last + step)
    uniq = {c.ts: c for c in out}
    return [uniq[k] for k in sorted(uniq)]
def candles_1y(market: str, timeframe: str, now: float | None = None) -> list[Candle]:
    now = now or time.time()
    seconds = tf_seconds(timeframe)
    end = _align(now, seconds)
    start = end - ONE_YEAR_DAYS * 86400
    path = _market_file(market, timeframe)
    cached = _load_cache(path)
    if cached and cached[0].ts <= start and cached[-1].ts >= end - seconds:
        return [c for c in cached if start <= c.ts <= end]
    logger.info("Bitvavo Lab: téléchargement %s %s (%d jours)", market, timeframe, ONE_YEAR_DAYS)
    fresh = _fetch_range(market, timeframe, int(start * 1000), int(end * 1000))
    if not fresh:
        raise RuntimeError(f"historique vide: {market} {timeframe}")
    _save_cache(path, fresh)
    return [c for c in fresh if start <= c.ts <= end]


def history_for_symbol(base: str, market: str, timeframes: list[str]) -> dict[str, list[Candle]]:
    out = {}
    for tf in sorted(set(timeframes), key=tf_seconds):
        out[tf] = candles_1y(market, tf)
    return out


def coverage(candles: list[Candle]) -> float:
    if len(candles) < 2:
        return 0.0
    return (candles[-1].ts - candles[0].ts) / 86400.0
