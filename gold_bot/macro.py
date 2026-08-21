"""Moteur macro / fondamental.

La litterature academique est stable sur les determinants de l'or :

  1. Taux d'interet reels americains (rendement 10 ans - inflation anticipee).
     C'est le driver dominant : l'or ne verse pas de coupon, son cout
     d'opportunite monte quand les taux reels montent. Correlation
     historiquement negative et forte.
  2. Dollar americain (DXY). L'or est cote en dollars : dollar fort,
     or mecaniquement sous pression.
  3. Aversion au risque (VIX, actions). L'or est une valeur refuge.
  4. Flux : encours des ETF or, positions nettes des non-commerciaux (COT).

Pour les cryptos, on utilise le meme cadre "appetit pour le risque" mais
avec le signe inverse : dollar faible et VIX bas favorisent le risque.

Le score macro ne declenche jamais un trade a lui seul : il pondere la
conviction technique et peut interdire une entree qui va franchement
contre le fond.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from .core import Candle
from .datasources import DataRegistry
from .datasources.base import ProviderError, http_get
from .indicators import correlation

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class MacroSnapshot:
    """Photographie des drivers fondamentaux a un instant donne."""

    ts: float = 0.0
    dxy: Optional[float] = None
    dxy_change_pct: Optional[float] = None
    us10y: Optional[float] = None
    us10y_change: Optional[float] = None
    real_rate: Optional[float] = None
    breakeven_inflation: Optional[float] = None
    vix: Optional[float] = None
    vix_change_pct: Optional[float] = None
    spx_change_pct: Optional[float] = None
    gold_etf_flow: Optional[float] = None
    cot_net_long: Optional[float] = None
    cot_change: Optional[float] = None
    correlations: dict[str, float] = field(default_factory=dict)
    details: dict[str, str] = field(default_factory=dict)

    @property
    def age_minutes(self) -> float:
        return (time.time() - self.ts) / 60.0 if self.ts else 1e9


@dataclass(slots=True)
class MacroBias:
    """Verdict macro pour un actif."""

    score: float                  # -1 (baissier) a +1 (haussier)
    drivers: list[str] = field(default_factory=list)
    confidence: float = 0.0       # 0 a 1 : proportion de drivers disponibles

    @property
    def direction(self) -> str:
        if self.score > 0.2:
            return "bullish"
        if self.score < -0.2:
            return "bearish"
        return "neutral"


class FredClient:
    """Serie temporelles FRED (Federal Reserve). Cle : FRED_API_KEY.

    Series utilisees :
      DGS10   - rendement nominal 10 ans
      DFII10  - rendement reel 10 ans (TIPS)  <- le driver n1 de l'or
      T10YIE  - inflation anticipee 10 ans (point mort)
      DTWEXBGS- indice large du dollar
    """

    def __init__(self) -> None:
        self.key = os.getenv("FRED_API_KEY", "")

    def available(self) -> bool:
        return bool(self.key)

    def series(self, series_id: str, days: int = 30) -> list[tuple[str, float]]:
        if not self.key:
            raise ProviderError("fred: cle absente")
        start = (datetime.now(timezone.utc) - timedelta(days=days)).date()
        data = http_get(
            "https://api.stlouisfed.org/fred/series/observations",
            params={"series_id": series_id, "api_key": self.key, "file_type": "json",
                    "observation_start": str(start), "sort_order": "asc"},
        )
        out = []
        for row in data.get("observations", []):
            try:
                out.append((row["date"], float(row["value"])))
            except (KeyError, ValueError):
                continue
        return out

    def latest(self, series_id: str, days: int = 30) -> Optional[float]:
        try:
            rows = self.series(series_id, days)
            return rows[-1][1] if rows else None
        except Exception as exc:  # noqa: BLE001
            logger.debug("fred %s indisponible : %s", series_id, exc)
            return None

    def change(self, series_id: str, days: int = 30) -> Optional[float]:
        try:
            rows = self.series(series_id, days)
            return rows[-1][1] - rows[0][1] if len(rows) >= 2 else None
        except Exception:  # noqa: BLE001
            return None


class CotClient:
    """Positions COT (CFTC) sur l'or, via l'API publique Socrata.

    Le positionnement net des non-commerciaux est un indicateur de
    sentiment contrarian : un net long extreme signale un marche sature.
    """

    DATASET = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"

    def fetch_gold(self) -> Optional[dict]:
        try:
            rows = http_get(
                self.DATASET,
                params={"$where": "market_and_exchange_names like '%GOLD%'",
                        "$order": "report_date_as_yyyy_mm_dd DESC", "$limit": 2},
            )
            if not isinstance(rows, list) or not rows:
                return None
            def net(row):
                return float(row.get("noncomm_positions_long_all", 0)) - float(row.get("noncomm_positions_short_all", 0))
            latest = net(rows[0])
            prior = net(rows[1]) if len(rows) > 1 else latest
            return {"net_long": latest, "change": latest - prior,
                    "date": rows[0].get("report_date_as_yyyy_mm_dd", "")}
        except Exception as exc:  # noqa: BLE001
            logger.debug("COT indisponible : %s", exc)
            return None


class MacroEngine:
    """Collecte les drivers fondamentaux et produit un biais par actif."""

    def __init__(self, registry: DataRegistry, refresh_seconds: float = 1800.0) -> None:
        self.registry = registry
        self.refresh_seconds = refresh_seconds
        self.fred = FredClient()
        self.cot = CotClient()
        self.snapshot = MacroSnapshot()
        self._series_cache: dict[str, list[Candle]] = {}

    # ---------------------------------------------------------------
    def _daily(self, symbol: str, limit: int = 60) -> list[Candle]:
        """Serie journaliere d'un indice macro (avec tolerance a l'echec)."""
        try:
            data = self.registry.candles(symbol, "index", "D1", limit, max_age=3600.0)
            self._series_cache[symbol] = data
            return data
        except Exception as exc:  # noqa: BLE001
            logger.debug("serie macro %s indisponible : %s", symbol, exc)
            return self._series_cache.get(symbol, [])

    @staticmethod
    def _pct_change(candles: list[Candle], periods: int = 5) -> Optional[float]:
        if len(candles) <= periods:
            return None
        old = candles[-1 - periods].close
        if old == 0:
            return None
        return (candles[-1].close - old) / abs(old) * 100.0

    def refresh(self, force: bool = False) -> MacroSnapshot:
        """Rafraichit la photographie macro (toutes les 30 min par defaut)."""
        if not force and self.snapshot.age_minutes < self.refresh_seconds / 60.0:
            return self.snapshot

        snap = MacroSnapshot(ts=time.time())

        dxy = self._daily("DXY")
        if dxy:
            snap.dxy = dxy[-1].close
            snap.dxy_change_pct = self._pct_change(dxy)
            snap.details["dxy"] = "yahoo DX-Y.NYB"

        tnx = self._daily("US10Y")
        if tnx:
            # ^TNX cote le rendement x10 chez Yahoo
            snap.us10y = tnx[-1].close / 10.0 if tnx[-1].close > 20 else tnx[-1].close
            chg = self._pct_change(tnx)
            snap.us10y_change = (chg / 100.0 * snap.us10y) if chg is not None else None
            snap.details["us10y"] = "yahoo ^TNX"

        vix = self._daily("VIX")
        if vix:
            snap.vix = vix[-1].close
            snap.vix_change_pct = self._pct_change(vix)

        spx = self._daily("SPX")
        if spx:
            snap.spx_change_pct = self._pct_change(spx)

        # Taux reel : la source la plus fiable est FRED (DFII10).
        if self.fred.available():
            real = self.fred.latest("DFII10")
            if real is not None:
                snap.real_rate = real
                snap.details["real_rate"] = "FRED DFII10"
            snap.breakeven_inflation = self.fred.latest("T10YIE")
            if snap.us10y is None:
                snap.us10y = self.fred.latest("DGS10")
        if snap.real_rate is None and snap.us10y is not None and snap.breakeven_inflation is not None:
            snap.real_rate = snap.us10y - snap.breakeven_inflation
            snap.details["real_rate"] = "calcule (10Y - point mort)"

        cot = self.cot.fetch_gold()
        if cot:
            snap.cot_net_long = cot["net_long"]
            snap.cot_change = cot["change"]
            snap.details["cot"] = f"CFTC {cot['date'][:10]}"

        # Correlations glissantes or / dollar / actions : sert a savoir
        # quel driver domine reellement en ce moment.
        gold = self._daily("XAUUSD") or self._daily("GLD")
        if gold and dxy:
            snap.correlations["gold_dxy"] = correlation(
                [c.close for c in gold[-30:]], [c.close for c in dxy[-30:]])
        if gold and spx:
            snap.correlations["gold_spx"] = correlation(
                [c.close for c in gold[-30:]], [c.close for c in spx[-30:]])
        if gold and tnx:
            snap.correlations["gold_us10y"] = correlation(
                [c.close for c in gold[-30:]], [c.close for c in tnx[-30:]])

        self.snapshot = snap
        return snap

    # ---------------------------------------------------------------
    def bias(self, symbol: str, asset_class: str) -> MacroBias:
        """Biais fondamental pour un actif donne."""
        snap = self.refresh()
        if asset_class == "metal":
            return self._gold_bias(snap)
        if asset_class == "crypto":
            return self._risk_asset_bias(snap, weight=1.0)
        if asset_class == "forex":
            return self._forex_bias(snap, symbol)
        return self._risk_asset_bias(snap, weight=0.6)

    def _gold_bias(self, snap: MacroSnapshot) -> MacroBias:
        score, drivers, available, total = 0.0, [], 0, 4

        # 1. Taux reels : driver dominant (poids 0.4)
        if snap.real_rate is not None:
            available += 1
            # Zone neutre autour de 1.5 % : au-dela, l'or souffre.
            pressure = max(-1.0, min(1.0, (1.5 - snap.real_rate) / 1.5))
            score += 0.40 * pressure
            drivers.append(f"taux reel 10A {snap.real_rate:+.2f}% -> {'soutien' if pressure > 0 else 'frein'}")

        # 2. Dollar (poids 0.3)
        if snap.dxy_change_pct is not None:
            available += 1
            usd = max(-1.0, min(1.0, -snap.dxy_change_pct / 1.5))
            score += 0.30 * usd
            drivers.append(f"DXY {snap.dxy_change_pct:+.2f}% sur 5j -> {'soutien' if usd > 0 else 'frein'}")

        # 3. Aversion au risque (poids 0.2)
        if snap.vix is not None:
            available += 1
            fear = max(-1.0, min(1.0, (snap.vix - 17.0) / 12.0))
            score += 0.20 * fear
            drivers.append(f"VIX {snap.vix:.1f} -> {'refuge' if fear > 0 else 'appetit risque'}")

        # 4. Positionnement COT (poids 0.1, contrarian aux extremes)
        if snap.cot_net_long is not None:
            available += 1
            if snap.cot_net_long > 250000:
                score -= 0.10
                drivers.append("COT net long extreme -> risque de purge")
            elif snap.cot_net_long < 50000:
                score += 0.10
                drivers.append("COT net long faible -> marge de hausse")
            else:
                drivers.append(f"COT net long {snap.cot_net_long:,.0f} (neutre)")

        confidence = available / total
        return MacroBias(max(-1.0, min(1.0, score)), drivers, confidence)

    def _risk_asset_bias(self, snap: MacroSnapshot, weight: float = 1.0) -> MacroBias:
        """Crypto et indices : pilotes par l'appetit pour le risque."""
        score, drivers, available, total = 0.0, [], 0, 3
        if snap.vix is not None:
            available += 1
            calm = max(-1.0, min(1.0, (18.0 - snap.vix) / 10.0))
            score += 0.4 * calm
            drivers.append(f"VIX {snap.vix:.1f} -> {'risk-on' if calm > 0 else 'risk-off'}")
        if snap.spx_change_pct is not None:
            available += 1
            score += 0.35 * max(-1.0, min(1.0, snap.spx_change_pct / 3.0))
            drivers.append(f"S&P500 {snap.spx_change_pct:+.2f}% sur 5j")
        if snap.dxy_change_pct is not None:
            available += 1
            score += 0.25 * max(-1.0, min(1.0, -snap.dxy_change_pct / 1.5))
            drivers.append(f"DXY {snap.dxy_change_pct:+.2f}% sur 5j")
        return MacroBias(max(-1.0, min(1.0, score * weight)), drivers, available / total)

    def _forex_bias(self, snap: MacroSnapshot, symbol: str) -> MacroBias:
        """Paires forex : le biais porte sur la force du dollar."""
        s = symbol.upper()
        if snap.dxy_change_pct is None:
            return MacroBias(0.0, ["DXY indisponible"], 0.0)
        usd_strength = max(-1.0, min(1.0, snap.dxy_change_pct / 1.5))
        usd_is_base = s.startswith("USD")
        score = usd_strength if usd_is_base else -usd_strength
        drivers = [f"DXY {snap.dxy_change_pct:+.2f}% sur 5j -> "
                   f"{'dollar fort' if usd_strength > 0 else 'dollar faible'}"]
        if snap.vix is not None and s[3:] in ("JPY", "CHF"):
            # Yen et franc suisse se renforcent en aversion au risque.
            fear = max(-1.0, min(1.0, (snap.vix - 17.0) / 12.0))
            score -= 0.3 * fear
            drivers.append(f"VIX {snap.vix:.1f} -> devise refuge {s[3:]}")
        return MacroBias(max(-1.0, min(1.0, score)), drivers, 0.7)

    # ---------------------------------------------------------------
    def veto(self, symbol: str, asset_class: str, side_is_buy: bool,
             threshold: float = 0.55) -> Optional[str]:
        """Interdit une entree qui va frontalement contre un fond tres marque.

        Le veto ne se declenche que sur un biais macro fort ET fiable :
        le technique garde la main dans tous les cas ordinaires.
        """
        b = self.bias(symbol, asset_class)
        if b.confidence < 0.5:
            return None
        if side_is_buy and b.score <= -threshold:
            return f"macro fortement baissier ({b.score:+.2f}) : {'; '.join(b.drivers[:2])}"
        if not side_is_buy and b.score >= threshold:
            return f"macro fortement haussier ({b.score:+.2f}) : {'; '.join(b.drivers[:2])}"
        return None
