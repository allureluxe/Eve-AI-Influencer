"""Types de base du robot de trading OR (XAU/USD).

Aucune dependance externe : tout est en Python standard pour rester rapide
et deployable partout (VPS minimal, container, Raspberry...).
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Side(str, Enum):
    """Sens d'une position."""

    BUY = "BUY"
    SELL = "SELL"

    @property
    def sign(self) -> int:
        """+1 pour un achat, -1 pour une vente (simplifie toutes les maths)."""
        return 1 if self is Side.BUY else -1

    @property
    def opposite(self) -> "Side":
        return Side.SELL if self is Side.BUY else Side.BUY


@dataclass(slots=True)
class Candle:
    """Une bougie OHLCV. `ts` est un timestamp UNIX en secondes (UTC)."""

    ts: float
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    # --- Geometrie de la bougie (utilisee par la lecture des patterns) ---
    @property
    def body(self) -> float:
        return abs(self.close - self.open)

    @property
    def range(self) -> float:
        return max(self.high - self.low, 1e-12)

    @property
    def upper_wick(self) -> float:
        return self.high - max(self.open, self.close)

    @property
    def lower_wick(self) -> float:
        return min(self.open, self.close) - self.low

    @property
    def bullish(self) -> bool:
        return self.close > self.open

    @property
    def bearish(self) -> bool:
        return self.close < self.open

    @property
    def body_ratio(self) -> float:
        """Part du corps dans l'amplitude totale (0 = doji, 1 = marubozu)."""
        return self.body / self.range

    @property
    def close_position(self) -> float:
        """Position de la cloture dans la bougie : 0 = sur le bas, 1 = sur le haut."""
        return (self.close - self.low) / self.range


@dataclass(slots=True)
class Tick:
    """Prix courant bid/ask."""

    ts: float
    bid: float
    ask: float

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0

    @property
    def spread(self) -> float:
        return self.ask - self.bid

    def price_for(self, side: Side) -> float:
        """Prix d'entree pour un sens donne (on paie le spread a l'ouverture)."""
        return self.ask if side is Side.BUY else self.bid

    def exit_price_for(self, side: Side) -> float:
        """Prix de sortie d'une position ouverte dans ce sens."""
        return self.bid if side is Side.BUY else self.ask


@dataclass(slots=True)
class Signal:
    """Signal produit par la strategie."""

    side: Side
    score: float
    reasons: list[str] = field(default_factory=list)
    atr: float = 0.0
    ts: float = field(default_factory=time.time)

    def __str__(self) -> str:  # pragma: no cover - confort de log
        return f"{self.side.value} score={self.score:.2f} [{', '.join(self.reasons)}]"


@dataclass(slots=True)
class Position:
    """Position ouverte, avec tout l'etat necessaire au trailing dynamique."""

    id: str
    symbol: str
    side: Side
    volume: float          # en lots
    entry_price: float
    stop_loss: float
    take_profit: float
    opened_at: float

    initial_stop: float = 0.0
    initial_tp: float = 0.0
    initial_risk: float = 0.0   # distance entree <-> SL initial, en prix (= 1R)

    # Suivi du parcours du prix (indispensable pour un trailing correct)
    max_favorable: float = 0.0  # meilleur prix atteint dans le sens du trade
    max_adverse: float = 0.0    # pire prix atteint

    tp_extensions: int = 0
    breakeven_done: bool = False
    partial_done: bool = False
    broker_ref: Optional[str] = None
    comment: str = ""

    def __post_init__(self) -> None:
        if not self.initial_stop:
            self.initial_stop = self.stop_loss
        if not self.initial_tp:
            self.initial_tp = self.take_profit
        if not self.initial_risk:
            self.initial_risk = abs(self.entry_price - self.initial_stop)
        if not self.max_favorable:
            self.max_favorable = self.entry_price
        if not self.max_adverse:
            self.max_adverse = self.entry_price

    # --- Mesures en R (1R = risque initial) ---
    def r_multiple(self, price: float) -> float:
        """Gain courant exprime en multiples du risque initial."""
        if self.initial_risk <= 0:
            return 0.0
        return self.side.sign * (price - self.entry_price) / self.initial_risk

    def locked_r(self) -> float:
        """Gain deja verrouille par le stop (negatif tant que le SL est sous l'entree)."""
        if self.initial_risk <= 0:
            return 0.0
        return self.side.sign * (self.stop_loss - self.entry_price) / self.initial_risk

    def tp_r(self) -> float:
        """Objectif courant exprime en R."""
        if self.initial_risk <= 0:
            return 0.0
        return self.side.sign * (self.take_profit - self.entry_price) / self.initial_risk

    def progress_to_tp(self, price: float) -> float:
        """Avancement vers le TP : 0 = a l'entree, 1 = TP touche."""
        span = self.side.sign * (self.take_profit - self.entry_price)
        if span <= 0:
            return 0.0
        return self.side.sign * (price - self.entry_price) / span

    def track(self, price: float) -> None:
        """Met a jour les extremes parcourus par le prix."""
        if self.side is Side.BUY:
            self.max_favorable = max(self.max_favorable, price)
            self.max_adverse = min(self.max_adverse, price)
        else:
            self.max_favorable = min(self.max_favorable, price)
            self.max_adverse = max(self.max_adverse, price)

    def hit_stop(self, price: float) -> bool:
        return price <= self.stop_loss if self.side is Side.BUY else price >= self.stop_loss

    def hit_target(self, price: float) -> bool:
        return price >= self.take_profit if self.side is Side.BUY else price <= self.take_profit


@dataclass(slots=True)
class ClosedTrade:
    """Trade termine, pour le journal et les statistiques."""

    position_id: str
    symbol: str
    side: Side
    volume: float
    entry_price: float
    exit_price: float
    opened_at: float
    closed_at: float
    profit: float
    r_multiple: float
    reason: str
    tp_extensions: int = 0
    max_favorable_r: float = 0.0
    partial: bool = False   # True = fermeture partielle, pas la fin du trade


def round_price(price: float, digits: int) -> float:
    """Arrondi au tick du symbole (l'or cote en general a 2 decimales)."""
    return round(price + 0.0, digits)


def is_finite(*values: float) -> bool:
    return all(v is not None and math.isfinite(v) for v in values)
