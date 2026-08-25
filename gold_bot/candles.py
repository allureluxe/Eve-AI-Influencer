"""Lecture des bougies japonaises (price action).

Les patterns sont normalises par l'ATR : sur l'or, une bougie de 3 $ n'a pas
le meme sens a 10h qu'a 14h30. Un pattern n'est retenu que s'il est
significatif par rapport a la volatilite du moment.

Chaque detecteur retourne un score signe :
    > 0  = biais haussier,  < 0 = biais baissier, 0 = rien.
L'amplitude (0 a 1) traduit la qualite du pattern.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Sequence

from .core import Candle


@dataclass(slots=True)
class PatternHit:
    name: str
    score: float          # signe = direction, valeur absolue = qualite (0..1)
    bullish: bool

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.name}({self.score:+.2f})"


def _sig(candle: Candle, atr: float, min_ratio: float = 0.35) -> bool:
    """La bougie est-elle assez grande pour compter face a la volatilite ?"""
    return atr > 0 and candle.range >= min_ratio * atr


# --------------------------------------------------------------------------
# Patterns a une bougie
# --------------------------------------------------------------------------
def detect_pin_bar(c: Candle, atr: float) -> Optional[PatternHit]:
    """Pin bar / marteau / etoile filante : rejet marque d'un niveau."""
    if not _sig(c, atr, 0.5):
        return None
    if c.body_ratio > 0.4:
        return None
    if c.lower_wick >= 2.0 * c.body and c.lower_wick > c.upper_wick * 2.0:
        quality = min(1.0, c.lower_wick / c.range + 0.15)
        return PatternHit("pin_bar_haussier", quality, True)
    if c.upper_wick >= 2.0 * c.body and c.upper_wick > c.lower_wick * 2.0:
        quality = min(1.0, c.upper_wick / c.range + 0.15)
        return PatternHit("pin_bar_baissier", -quality, False)
    return None


def detect_marubozu(c: Candle, atr: float) -> Optional[PatternHit]:
    """Marubozu : corps plein, aucune hesitation, continuation forte."""
    if not _sig(c, atr, 0.9) or c.body_ratio < 0.85:
        return None
    return PatternHit("marubozu", 0.7 if c.bullish else -0.7, c.bullish)


def detect_doji(c: Candle, atr: float) -> Optional[PatternHit]:
    """Doji : indecision. Score neutre, sert a bloquer une entree."""
    if atr <= 0 or c.range < 0.25 * atr:
        return None
    if c.body_ratio <= 0.08:
        return PatternHit("doji", 0.0, False)
    return None


# --------------------------------------------------------------------------
# Patterns a deux bougies
# --------------------------------------------------------------------------
def detect_engulfing(prev: Candle, cur: Candle, atr: float) -> Optional[PatternHit]:
    """Avalement (engulfing) : le corps courant englobe le precedent."""
    if not _sig(cur, atr, 0.6):
        return None
    if cur.body < prev.body:
        return None
    body_low_cur, body_high_cur = min(cur.open, cur.close), max(cur.open, cur.close)
    body_low_prev, body_high_prev = min(prev.open, prev.close), max(prev.open, prev.close)
    if not (body_low_cur <= body_low_prev and body_high_cur >= body_high_prev):
        return None
    quality = min(1.0, 0.45 + cur.body / max(atr, 1e-9) * 0.3)
    if cur.bullish and prev.bearish:
        return PatternHit("avalement_haussier", quality, True)
    if cur.bearish and prev.bullish:
        return PatternHit("avalement_baissier", -quality, False)
    return None


def detect_harami(prev: Candle, cur: Candle, atr: float) -> Optional[PatternHit]:
    """Harami : bougie interieure apres une grande bougie (essoufflement)."""
    if prev.body < 0.7 * atr or cur.body > 0.5 * prev.body:
        return None
    if max(cur.open, cur.close) <= max(prev.open, prev.close) and min(cur.open, cur.close) >= min(prev.open, prev.close):
        if prev.bearish and cur.bullish:
            return PatternHit("harami_haussier", 0.4, True)
        if prev.bullish and cur.bearish:
            return PatternHit("harami_baissier", -0.4, False)
    return None


def detect_piercing(prev: Candle, cur: Candle, atr: float) -> Optional[PatternHit]:
    """Pénétrante / couverture en nuage noir : reprise au-dela de 50 % du corps."""
    if not _sig(cur, atr, 0.6) or prev.body < 0.4 * atr:
        return None
    mid_prev = (prev.open + prev.close) / 2.0
    if prev.bearish and cur.bullish and cur.open < prev.close and cur.close > mid_prev and cur.close < prev.open:
        return PatternHit("penetrante", 0.55, True)
    if prev.bullish and cur.bearish and cur.open > prev.close and cur.close < mid_prev and cur.close > prev.open:
        return PatternHit("nuage_noir", -0.55, False)
    return None


def detect_inside_bar(prev: Candle, cur: Candle, atr: float) -> Optional[PatternHit]:
    """Inside bar : compression, signal de breakout imminent (neutre en direction)."""
    if cur.high <= prev.high and cur.low >= prev.low and prev.range >= 0.8 * atr:
        return PatternHit("inside_bar", 0.0, False)
    return None


# --------------------------------------------------------------------------
# Patterns a trois bougies
# --------------------------------------------------------------------------
def detect_star(c1: Candle, c2: Candle, c3: Candle, atr: float) -> Optional[PatternHit]:
    """Etoile du matin / du soir : retournement en trois temps."""
    if c1.body < 0.5 * atr or c3.body < 0.5 * atr:
        return None
    if c2.body > 0.4 * c1.body:
        return None
    mid1 = (c1.open + c1.close) / 2.0
    if c1.bearish and c3.bullish and c3.close > mid1:
        return PatternHit("etoile_du_matin", 0.8, True)
    if c1.bullish and c3.bearish and c3.close < mid1:
        return PatternHit("etoile_du_soir", -0.8, False)
    return None


def detect_three_soldiers(c1: Candle, c2: Candle, c3: Candle, atr: float) -> Optional[PatternHit]:
    """Trois soldats blancs / trois corbeaux noirs : poussee directionnelle."""
    bodies = [c.body for c in (c1, c2, c3)]
    if min(bodies) < 0.35 * atr:
        return None
    if all(c.bullish for c in (c1, c2, c3)) and c2.close > c1.close and c3.close > c2.close:
        return PatternHit("trois_soldats", 0.75, True)
    if all(c.bearish for c in (c1, c2, c3)) and c2.close < c1.close and c3.close < c2.close:
        return PatternHit("trois_corbeaux", -0.75, False)
    return None


# --------------------------------------------------------------------------
# Agregation
# --------------------------------------------------------------------------
BLOCKING_PATTERNS = {"doji", "inside_bar"}


def scan(candles: Sequence[Candle], atr: float) -> list[PatternHit]:
    """Analyse les dernieres bougies et retourne tous les patterns detectes."""
    hits: list[PatternHit] = []
    if not candles or atr <= 0:
        return hits

    cur = candles[-1]
    for fn in (detect_pin_bar, detect_marubozu):
        hit = fn(cur, atr)
        if hit:
            hits.append(hit)
    # Un doji n'est retenu que si aucune lecture directionnelle n'a ete faite :
    # une pin bar a petit corps est un rejet, pas une indecision.
    if not hits:
        hit = detect_doji(cur, atr)
        if hit:
            hits.append(hit)

    if len(candles) >= 2:
        prev = candles[-2]
        for fn2 in (detect_engulfing, detect_harami, detect_piercing, detect_inside_bar):
            hit = fn2(prev, cur, atr)
            if hit:
                hits.append(hit)

    if len(candles) >= 3:
        c1, c2, c3 = candles[-3], candles[-2], candles[-1]
        for fn3 in (detect_star, detect_three_soldiers):
            hit = fn3(c1, c2, c3, atr)
            if hit:
                hits.append(hit)

    return hits


def pattern_score(hits: Sequence[PatternHit]) -> float:
    """Score net des patterns, borne a [-1, 1]."""
    if not hits:
        return 0.0
    total = sum(h.score for h in hits)
    return max(-1.0, min(1.0, total))


def has_blocker(hits: Sequence[PatternHit]) -> bool:
    """Presence d'un pattern d'indecision qui doit annuler une entree.

    Un signal directionnel franc (|score| >= 0.5) prend le pas sur
    l'indecision : une inside bar suivie d'un avalement reste tradable.
    """
    if any(abs(h.score) >= 0.5 for h in hits):
        return False
    return any(h.name in BLOCKING_PATTERNS for h in hits)


def opposing_reversal(hits: Sequence[PatternHit], bullish_position: bool) -> bool:
    """Un pattern de retournement contraire a la position est-il present ?

    Utilise par la gestion de trade : si le prix approche du TP mais qu'une
    etoile du soir apparait sur un achat, on n'etend pas l'objectif.
    """
    threshold = 0.5
    for h in hits:
        if bullish_position and h.score <= -threshold:
            return True
        if not bullish_position and h.score >= threshold:
            return True
    return False
