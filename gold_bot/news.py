"""Calendrier economique et filtre d'annonces.

L'or est l'actif le plus sensible aux statistiques americaines : NFP, CPI,
FOMC et PIB peuvent deplacer le metal de 20 a 40 $ en quelques secondes,
avec un elargissement brutal du spread. Un systeme court terme qui ignore
le calendrier finit par se faire sortir sur des meches.

Strategie retenue :
  1. BLACKOUT  : aucune nouvelle entree autour d'une annonce a fort impact,
  2. PROTECTION: les positions ouvertes voient leur stop resserre avant l'heure,
  3. BREAKOUT  : apres la publication, une fois la premiere impulsion digeree,
     le robot peut reprendre dans le sens du mouvement (mode optionnel).

Sources supportees : Finnhub, Financial Modeling Prep, TradingEconomics,
fichier local JSON. En l'absence de cle, un calendrier recurrent integre
couvre les rendez-vous structurellement connus (NFP, CPI, FOMC...).
"""
from __future__ import annotations

import calendar as _cal
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from .datasources.base import ProviderError, http_get

logger = logging.getLogger(__name__)

IMPACT_HIGH = "high"
IMPACT_MEDIUM = "medium"
IMPACT_LOW = "low"

# Devises dont les annonces comptent, par classe d'actif.
IMPACT_CURRENCIES = {
    "metal": {"USD", "EUR"},
    "forex": {"USD", "EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD"},
    "crypto": {"USD"},
    "index": {"USD"},
    "energy": {"USD"},
}

# Mots-cles des annonces qui bougent reellement l'or et le dollar.
HIGH_IMPACT_KEYWORDS = (
    "non-farm", "nonfarm", "nfp", "payroll", "unemployment rate",
    "cpi", "consumer price", "core cpi", "ppi", "producer price",
    "fomc", "fed interest rate", "federal funds", "interest rate decision",
    "gdp", "retail sales", "pce", "powell", "fed chair", "ism",
    "ecb", "boe", "boj", "jackson hole", "beige book",
)


@dataclass(slots=True)
class EconomicEvent:
    """Un evenement du calendrier economique."""

    ts: float                 # horodatage UTC de la publication
    title: str
    currency: str
    impact: str               # "high" | "medium" | "low"
    actual: Optional[float] = None
    forecast: Optional[float] = None
    previous: Optional[float] = None
    source: str = ""

    @property
    def when(self) -> datetime:
        return datetime.fromtimestamp(self.ts, tz=timezone.utc)

    def surprise(self) -> Optional[float]:
        """Ecart entre le publie et le consensus, normalise.

        C'est ce qui fait bouger le marche : pas le chiffre lui-meme, mais
        sa distance au consensus.
        """
        if self.actual is None or self.forecast is None:
            return None
        base = abs(self.forecast) if abs(self.forecast) > 1e-9 else 1.0
        return (self.actual - self.forecast) / base

    def gold_direction(self) -> int:
        """Impact theorique de la surprise sur l'or : +1 haussier, -1 baissier, 0 neutre.

        Regle macro de base : une statistique americaine meilleure que prevu
        renforce le dollar et les taux, donc pese sur l'or. Les chiffres
        d'inflation et de chomage s'interpretent en sens inverse.
        """
        s = self.surprise()
        if s is None or abs(s) < 0.02 or self.currency != "USD":
            return 0
        title = self.title.lower()
        inverse = any(k in title for k in ("unemployment", "jobless", "chomage"))
        inflation = any(k in title for k in ("cpi", "ppi", "pce", "inflation", "price index"))
        if inflation:
            # Inflation plus forte : d'abord hausse des taux (negatif or),
            # mais soutien de long terme. On retient l'effet immediat.
            return -1 if s > 0 else 1
        if inverse:
            return 1 if s > 0 else -1
        return -1 if s > 0 else 1


@dataclass(slots=True)
class NewsWindow:
    """Verdict du filtre news a un instant donne."""

    blocked: bool
    reason: str = ""
    event: Optional[EconomicEvent] = None
    minutes_to_event: Optional[float] = None
    tighten_stops: bool = False
    breakout_mode: bool = False


# ==========================================================================
# Sources de calendrier
# ==========================================================================
class CalendarSource:
    """Interface d'une source de calendrier."""

    name = "abstract"

    def available(self) -> bool:
        return True

    def fetch(self, days_ahead: int = 3, days_back: int = 1) -> list[EconomicEvent]:
        raise NotImplementedError


class FinnhubCalendar(CalendarSource):
    """Calendrier economique Finnhub. Cle : FINNHUB_API_KEY."""

    name = "finnhub"

    def available(self) -> bool:
        return bool(os.getenv("FINNHUB_API_KEY"))

    def fetch(self, days_ahead: int = 3, days_back: int = 1) -> list[EconomicEvent]:
        key = os.getenv("FINNHUB_API_KEY", "")
        if not key:
            raise ProviderError("finnhub: cle absente")
        today = datetime.now(timezone.utc).date()
        data = http_get(
            "https://finnhub.io/api/v1/calendar/economic",
            params={"from": str(today - timedelta(days=days_back)),
                    "to": str(today + timedelta(days=days_ahead)), "token": key},
        )
        out = []
        for row in (data.get("economicCalendar") or []):
            try:
                ts = _parse_ts(row.get("time"))
                if ts is None:
                    continue
                out.append(EconomicEvent(
                    ts=ts, title=row.get("event", ""), currency=(row.get("country") or "").upper()[:3],
                    impact=_normalize_impact(row.get("impact")),
                    actual=_num(row.get("actual")), forecast=_num(row.get("estimate")),
                    previous=_num(row.get("prev")), source=self.name))
            except Exception:  # noqa: BLE001
                continue
        return out


class FMPCalendar(CalendarSource):
    """Financial Modeling Prep. Cle : FMP_API_KEY."""

    name = "fmp"

    def available(self) -> bool:
        return bool(os.getenv("FMP_API_KEY"))

    def fetch(self, days_ahead: int = 3, days_back: int = 1) -> list[EconomicEvent]:
        key = os.getenv("FMP_API_KEY", "")
        if not key:
            raise ProviderError("fmp: cle absente")
        today = datetime.now(timezone.utc).date()
        data = http_get(
            "https://financialmodelingprep.com/api/v3/economic_calendar",
            params={"from": str(today - timedelta(days=days_back)),
                    "to": str(today + timedelta(days=days_ahead)), "apikey": key},
        )
        out = []
        for row in data if isinstance(data, list) else []:
            ts = _parse_ts(row.get("date"))
            if ts is None:
                continue
            out.append(EconomicEvent(
                ts=ts, title=row.get("event", ""), currency=(row.get("currency") or "").upper()[:3],
                impact=_normalize_impact(row.get("impact")),
                actual=_num(row.get("actual")), forecast=_num(row.get("estimate")),
                previous=_num(row.get("previous")), source=self.name))
        return out


class TradingEconomicsCalendar(CalendarSource):
    """TradingEconomics. Cle : TRADINGECONOMICS_API_KEY (format 'user:pass')."""

    name = "tradingeconomics"

    def available(self) -> bool:
        return bool(os.getenv("TRADINGECONOMICS_API_KEY"))

    def fetch(self, days_ahead: int = 3, days_back: int = 1) -> list[EconomicEvent]:
        key = os.getenv("TRADINGECONOMICS_API_KEY", "")
        if not key:
            raise ProviderError("tradingeconomics: cle absente")
        today = datetime.now(timezone.utc).date()
        data = http_get(
            f"https://api.tradingeconomics.com/calendar/country/all/"
            f"{today - timedelta(days=days_back)}/{today + timedelta(days=days_ahead)}",
            params={"c": key, "f": "json"},
        )
        out = []
        for row in data if isinstance(data, list) else []:
            ts = _parse_ts(row.get("Date"))
            if ts is None:
                continue
            out.append(EconomicEvent(
                ts=ts, title=row.get("Event", ""), currency=(row.get("Currency") or "").upper()[:3],
                impact=_normalize_impact(row.get("Importance")),
                actual=_num(row.get("Actual")), forecast=_num(row.get("Forecast")),
                previous=_num(row.get("Previous")), source=self.name))
        return out


class LocalCalendar(CalendarSource):
    """Calendrier fourni par l'utilisateur (fichier JSON).

    Format attendu : [{"time": "2026-09-05T12:30:00Z", "event": "Non-Farm Payrolls",
                       "currency": "USD", "impact": "high"}, ...]
    """

    name = "local"

    def __init__(self, path: str = "") -> None:
        self.path = path or os.getenv("GB_CALENDAR_FILE", "data/economic_calendar.json")

    def available(self) -> bool:
        return os.path.exists(self.path)

    def fetch(self, days_ahead: int = 3, days_back: int = 1) -> list[EconomicEvent]:
        if not os.path.exists(self.path):
            return []
        with open(self.path, "r", encoding="utf-8") as fh:
            rows = json.load(fh)
        out = []
        for row in rows:
            ts = _parse_ts(row.get("time") or row.get("date"))
            if ts is None:
                continue
            out.append(EconomicEvent(
                ts=ts, title=row.get("event", ""), currency=(row.get("currency") or "USD").upper()[:3],
                impact=_normalize_impact(row.get("impact")),
                actual=_num(row.get("actual")), forecast=_num(row.get("forecast")),
                previous=_num(row.get("previous")), source=self.name))
        return out


class RecurringCalendar(CalendarSource):
    """Filet de securite : rendez-vous macro structurellement connus.

    Sans aucune cle API, le robot connait quand meme les creneaux les plus
    dangereux : NFP (1er vendredi 12h30 UTC), CPI US (mi-mois 12h30 UTC),
    decisions FOMC (18h-18h30 UTC), et l'ouverture du COMEX.

    Ces horaires sont approximatifs (l'heure d'ete decale d'une heure) : la
    fenetre de blackout est volontairement large pour compenser.
    """

    name = "recurring"

    def fetch(self, days_ahead: int = 3, days_back: int = 1) -> list[EconomicEvent]:
        out: list[EconomicEvent] = []
        today = datetime.now(timezone.utc).date()
        for offset in range(-days_back, days_ahead + 1):
            day = today + timedelta(days=offset)
            # NFP : premier vendredi du mois, 12h30 UTC
            if day.weekday() == 4 and day.day <= 7:
                out.append(_recurring_event(day, 12, 30, "Non-Farm Payrolls (recurrent)"))
            # CPI US : autour du 10-15 du mois, 12h30 UTC
            if 10 <= day.day <= 15 and day.weekday() < 5:
                out.append(_recurring_event(day, 12, 30, "US CPI (fenetre recurrente)"))
            # FOMC : mercredis de milieu de mois, 18h00 UTC
            if day.weekday() == 2 and 15 <= day.day <= 22:
                out.append(_recurring_event(day, 18, 0, "FOMC (fenetre recurrente)"))
            # Demandes d'allocations chomage : chaque jeudi 12h30 UTC
            if day.weekday() == 3:
                out.append(_recurring_event(day, 12, 30, "US Jobless Claims", IMPACT_MEDIUM))
        return out


def _recurring_event(day, hour: int, minute: int, title: str, impact: str = IMPACT_HIGH) -> EconomicEvent:
    dt = datetime(day.year, day.month, day.day, hour, minute, tzinfo=timezone.utc)
    return EconomicEvent(ts=dt.timestamp(), title=title, currency="USD",
                         impact=impact, source="recurring")


def _num(value) -> Optional[float]:
    if value in (None, "", "-"):
        return None
    try:
        return float(str(value).replace("%", "").replace(",", "").replace("K", "e3").replace("M", "e6"))
    except (TypeError, ValueError):
        return None


def _normalize_impact(value) -> str:
    if value is None:
        return IMPACT_LOW
    v = str(value).strip().lower()
    if v in ("3", "high", "haut", "eleve"):
        return IMPACT_HIGH
    if v in ("2", "medium", "moyen", "moderate"):
        return IMPACT_MEDIUM
    return IMPACT_LOW


def _parse_ts(value) -> Optional[float]:
    """Accepte un timestamp, un ISO 8601 ou 'YYYY-MM-DD HH:MM:SS'."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) / 1000.0 if float(value) > 1e11 else float(value)
    s = str(value).strip().replace("Z", "+00:00")
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S%z",
                "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except ValueError:
            continue
    return None


# ==========================================================================
# Filtre
# ==========================================================================
@dataclass(slots=True)
class NewsFilterConfig:
    """Fenetres de protection autour des annonces (en minutes)."""

    high_before: int = 20
    high_after: int = 20
    medium_before: int = 8
    medium_after: int = 8
    tighten_before: int = 45      # a partir de quand on resserre les stops
    allow_breakout: bool = True   # reprise apres l'impulsion post-annonce
    breakout_from: int = 6        # debut de la fenetre de breakout (min apres)
    breakout_to: int = 45         # fin de la fenetre de breakout
    refresh_seconds: float = 900.0


class NewsFilter:
    """Filtre d'entree base sur le calendrier economique.

    Interroge toutes les sources disponibles, fusionne et deduplique, puis
    repond a une question simple : "puis-je entrer maintenant sur cet actif ?"
    """

    def __init__(
        self,
        config: Optional[NewsFilterConfig] = None,
        sources: Optional[list[CalendarSource]] = None,
    ) -> None:
        self.config = config or NewsFilterConfig()
        self.sources = sources if sources is not None else [
            FinnhubCalendar(), FMPCalendar(), TradingEconomicsCalendar(),
            LocalCalendar(), RecurringCalendar(),
        ]
        self.events: list[EconomicEvent] = []
        self._last_refresh = 0.0

    # ---------------------------------------------------------------
    def refresh(self, force: bool = False) -> int:
        """Recharge le calendrier depuis toutes les sources disponibles."""
        if not force and time.time() - self._last_refresh < self.config.refresh_seconds:
            return len(self.events)
        merged: dict[tuple, EconomicEvent] = {}
        for src in self.sources:
            if not src.available():
                continue
            try:
                for ev in src.fetch():
                    if not ev.title:
                        continue
                    # Deduplication : meme creneau de 15 min + meme devise + meme intitule court
                    key = (int(ev.ts // 900), ev.currency, ev.title.lower()[:22])
                    prior = merged.get(key)
                    # On garde la version la plus riche (avec chiffre publie)
                    if prior is None or (prior.actual is None and ev.actual is not None):
                        merged[key] = ev
            except Exception as exc:  # noqa: BLE001
                logger.warning("calendrier %s indisponible : %s", src.name, str(exc)[:140])
        if merged:
            self.events = sorted(merged.values(), key=lambda e: e.ts)
            self._last_refresh = time.time()
        return len(self.events)

    # ---------------------------------------------------------------
    def relevant(self, asset_class: str, symbol: str = "") -> list[EconomicEvent]:
        """Evenements pertinents pour cet actif."""
        currencies = set(IMPACT_CURRENCIES.get(asset_class, {"USD"}))
        sym = symbol.upper()
        if len(sym) == 6 and asset_class == "forex":
            currencies |= {sym[:3], sym[3:]}
        return [e for e in self.events if e.currency in currencies and e.impact != IMPACT_LOW]

    def is_major(self, event: EconomicEvent) -> bool:
        title = event.title.lower()
        return event.impact == IMPACT_HIGH or any(k in title for k in HIGH_IMPACT_KEYWORDS)

    def check(self, asset_class: str, symbol: str = "", now: Optional[float] = None) -> NewsWindow:
        """Verdict : peut-on ouvrir une position maintenant ?"""
        now = now if now is not None else time.time()
        self.refresh()
        cfg = self.config
        nearest: Optional[EconomicEvent] = None
        nearest_delta = 1e18

        for ev in self.relevant(asset_class, symbol):
            delta_min = (ev.ts - now) / 60.0
            if abs(delta_min) > 120:
                continue
            major = self.is_major(ev)
            before = cfg.high_before if major else cfg.medium_before
            after = cfg.high_after if major else cfg.medium_after

            if -after <= delta_min <= before:
                # On est dans la fenetre interdite. Le mode breakout peut
                # rouvrir la porte une fois la premiere impulsion passee.
                if (cfg.allow_breakout and major
                        and -cfg.breakout_to <= delta_min <= -cfg.breakout_from):
                    return NewsWindow(False, f"fenetre breakout post-{ev.title}", ev,
                                      delta_min, tighten_stops=True, breakout_mode=True)
                return NewsWindow(True, f"annonce {ev.title} ({ev.currency}) dans {delta_min:+.0f} min",
                                  ev, delta_min, tighten_stops=True)

            if abs(delta_min) < abs(nearest_delta):
                nearest, nearest_delta = ev, delta_min

        tighten = bool(nearest and 0 < nearest_delta <= cfg.tighten_before and self.is_major(nearest))
        return NewsWindow(False, "", nearest, nearest_delta if nearest else None, tighten_stops=tighten)

    def next_events(self, asset_class: str = "metal", count: int = 5, now: Optional[float] = None) -> list[EconomicEvent]:
        """Prochaines annonces a venir (affichage et journal)."""
        now = now if now is not None else time.time()
        self.refresh()
        return [e for e in self.relevant(asset_class) if e.ts >= now][:count]

    def news_bias(self, asset_class: str = "metal", window_minutes: int = 120,
                  now: Optional[float] = None) -> float:
        """Biais directionnel issu des dernieres publications (-1 a +1).

        Agrege les surprises des annonces recentes : c'est le pont entre le
        fondamental et la decision technique.
        """
        now = now if now is not None else time.time()
        self.refresh()
        score = 0.0
        for ev in self.relevant(asset_class):
            age_min = (now - ev.ts) / 60.0
            if not (0 <= age_min <= window_minutes) or ev.actual is None:
                continue
            direction = ev.gold_direction()
            if direction == 0:
                continue
            weight = (1.0 - age_min / window_minutes) * (1.0 if self.is_major(ev) else 0.5)
            magnitude = min(1.0, abs(ev.surprise() or 0.0) * 4.0)
            score += direction * weight * magnitude
        return max(-1.0, min(1.0, score))
