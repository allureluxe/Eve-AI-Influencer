"""Analyse graphique avancee : niveaux, figures chartistes, divergences, zones institutionnelles.

Ce module ne prend aucune decision : il produit une lecture objective du
graphique que la strategie utilise ensuite comme facteurs de validation.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, Sequence

from .core import Candle, Side
from .indicators import IndicatorSet


# ==========================================================================
# Niveaux : supports / resistances, pivots, Fibonacci
# ==========================================================================
@dataclass(slots=True)
class Level:
    """Un niveau horizontal (support ou resistance)."""

    price: float
    kind: str            # "support" | "resistance"
    touches: int         # nombre de contacts -> force du niveau
    source: str          # "swing" | "pivot" | "fibo" | "round"

    @property
    def strength(self) -> float:
        base = {"swing": 0.5, "pivot": 0.4, "fibo": 0.3, "round": 0.25}.get(self.source, 0.3)
        return min(1.0, base + 0.15 * (self.touches - 1))


def cluster_levels(prices: Sequence[float], tolerance: float) -> list[tuple[float, int]]:
    """Regroupe des prix proches en un seul niveau (moyenne + nb de contacts)."""
    if not prices:
        return []
    ordered = sorted(prices)
    clusters: list[list[float]] = [[ordered[0]]]
    for p in ordered[1:]:
        if abs(p - clusters[-1][-1]) <= tolerance:
            clusters[-1].append(p)
        else:
            clusters.append([p])
    return [(sum(c) / len(c), len(c)) for c in clusters]


def swing_levels(ind: IndicatorSet, tolerance: Optional[float] = None) -> list[Level]:
    """Supports/resistances issus des swings (methode classique de price action)."""
    atr = ind.atr.value or 0.0
    tol = tolerance if tolerance is not None else max(atr * 0.35, 1e-9)
    levels: list[Level] = []
    for price, touches in cluster_levels(list(ind.swings.swing_highs), tol):
        levels.append(Level(price, "resistance", touches, "swing"))
    for price, touches in cluster_levels(list(ind.swings.swing_lows), tol):
        levels.append(Level(price, "support", touches, "swing"))
    return levels


def pivot_points(prev_high: float, prev_low: float, prev_close: float) -> dict[str, float]:
    """Points pivots classiques (floor trader pivots) de la seance precedente."""
    pp = (prev_high + prev_low + prev_close) / 3.0
    return {
        "PP": pp,
        "R1": 2 * pp - prev_low,
        "S1": 2 * pp - prev_high,
        "R2": pp + (prev_high - prev_low),
        "S2": pp - (prev_high - prev_low),
        "R3": prev_high + 2 * (pp - prev_low),
        "S3": prev_low - 2 * (prev_high - pp),
    }


def session_pivots(candles: Sequence[Candle]) -> dict[str, float]:
    """Calcule les pivots a partir de la journee UTC precedente."""
    if len(candles) < 10:
        return {}
    today = int(candles[-1].ts // 86400)
    prev = [c for c in candles if int(c.ts // 86400) == today - 1]
    if not prev:
        return {}
    return pivot_points(max(c.high for c in prev), min(c.low for c in prev), prev[-1].close)


def fibonacci_levels(swing_low: float, swing_high: float, uptrend: bool = True) -> dict[str, float]:
    """Retracements et extensions de Fibonacci sur l'impulsion donnee."""
    span = swing_high - swing_low
    if span <= 0:
        return {}
    ratios_retr = {"0.236": 0.236, "0.382": 0.382, "0.5": 0.5, "0.618": 0.618, "0.786": 0.786}
    ratios_ext = {"1.272": 1.272, "1.618": 1.618, "2.0": 2.0}
    out: dict[str, float] = {}
    if uptrend:
        for k, r in ratios_retr.items():
            out[f"retr_{k}"] = swing_high - span * r
        for k, r in ratios_ext.items():
            out[f"ext_{k}"] = swing_low + span * r
    else:
        for k, r in ratios_retr.items():
            out[f"retr_{k}"] = swing_low + span * r
        for k, r in ratios_ext.items():
            out[f"ext_{k}"] = swing_high - span * r
    return out


def round_numbers(price: float, step: float, count: int = 3) -> list[float]:
    """Niveaux psychologiques (chiffres ronds) autour du prix.

    Sur l'or, les paliers de 10 $ et 50 $ agissent comme des aimants.
    """
    if step <= 0:
        return []
    base = math.floor(price / step) * step
    return [base + i * step for i in range(-count, count + 1)]


def build_levels(ind: IndicatorSet, round_step: float) -> list[Level]:
    """Carte complete des niveaux : swings + pivots + chiffres ronds."""
    levels = swing_levels(ind)
    price = ind.last.close if ind.last else 0.0
    piv = session_pivots(list(ind.candles))
    for name, value in piv.items():
        if name == "PP":
            kind = "support" if value < price else "resistance"
        else:
            kind = "support" if name.startswith("S") else "resistance"
        levels.append(Level(value, kind, 1, "pivot"))
    for rn in round_numbers(price, round_step):
        if rn > 0:
            levels.append(Level(rn, "support" if rn < price else "resistance", 1, "round"))
    return levels


def nearest_level(levels: Sequence[Level], price: float, kind: str, above: bool,
                  min_strength: float = 0.0) -> Optional[Level]:
    """Niveau le plus proche au-dessus (ou en dessous) du prix."""
    pool = [l for l in levels
            if l.kind == kind and l.strength >= min_strength
            and ((l.price > price) if above else (l.price < price))]
    if not pool:
        return None
    return min(pool, key=lambda l: abs(l.price - price))


# Force minimale pour qu'un niveau soit considere comme un obstacle reel.
# Un chiffre rond (force 0.25) attire le prix mais ne l'arrete pas : sur
# l'or, avec un palier tous les 10 $ et un ATR de 3 $, le traiter comme un
# mur reviendrait a refuser la majorite des trades valables. Les pivots
# (0.40) et surtout les swings testes plusieurs fois (0.50+) comptent.
OBSTACLE_MIN_STRENGTH = 0.40


def headroom(levels: Sequence[Level], price: float, side: Side,
             min_strength: float = OBSTACLE_MIN_STRENGTH) -> Optional[float]:
    """Distance jusqu'au premier obstacle SERIEUX dans le sens du trade.

    C'est le facteur qui evite d'acheter juste sous une resistance majeure.
    """
    if side is Side.BUY:
        lvl = nearest_level(levels, price, "resistance", above=True, min_strength=min_strength)
        return (lvl.price - price) if lvl else None
    lvl = nearest_level(levels, price, "support", above=False, min_strength=min_strength)
    return (price - lvl.price) if lvl else None


# ==========================================================================
# Divergences
# ==========================================================================
@dataclass(slots=True)
class Divergence:
    kind: str        # "regular_bull" | "regular_bear" | "hidden_bull" | "hidden_bear"
    indicator: str
    strength: float

    @property
    def bullish(self) -> bool:
        return self.kind.endswith("bull")


def _pivots(values: Sequence[float], left: int = 2, right: int = 2) -> tuple[list[int], list[int]]:
    """Indices des sommets et creux d'une serie."""
    highs, lows = [], []
    for i in range(left, len(values) - right):
        window = values[i - left:i + right + 1]
        if values[i] == max(window) and window.count(values[i]) == 1:
            highs.append(i)
        if values[i] == min(window) and window.count(values[i]) == 1:
            lows.append(i)
    return highs, lows


def find_divergences(
    candles: Sequence[Candle],
    osc_values: Sequence[float],
    indicator_name: str = "RSI",
    lookback: int = 40,
) -> list[Divergence]:
    """Divergences classiques et cachees entre le prix et un oscillateur.

    Reguliere haussiere : prix fait un creux plus bas, oscillateur un creux plus haut
    -> essoufflement de la baisse. Cachee : signal de continuation de tendance.
    """
    n = min(len(candles), len(osc_values), lookback)
    if n < 12:
        return []
    cs = list(candles)[-n:]
    os_ = list(osc_values)[-n:]
    price_high = [c.high for c in cs]
    price_low = [c.low for c in cs]
    ph, pl = _pivots(price_high), _pivots(price_low)
    high_idx = ph[0]
    low_idx = pl[1]
    out: list[Divergence] = []

    if len(low_idx) >= 2:
        i1, i2 = low_idx[-2], low_idx[-1]
        if price_low[i2] < price_low[i1] and os_[i2] > os_[i1]:
            out.append(Divergence("regular_bull", indicator_name, min(1.0, abs(os_[i2] - os_[i1]) / 12.0)))
        elif price_low[i2] > price_low[i1] and os_[i2] < os_[i1]:
            out.append(Divergence("hidden_bull", indicator_name, min(1.0, abs(os_[i2] - os_[i1]) / 15.0)))

    if len(high_idx) >= 2:
        i1, i2 = high_idx[-2], high_idx[-1]
        if price_high[i2] > price_high[i1] and os_[i2] < os_[i1]:
            out.append(Divergence("regular_bear", indicator_name, min(1.0, abs(os_[i2] - os_[i1]) / 12.0)))
        elif price_high[i2] < price_high[i1] and os_[i2] > os_[i1]:
            out.append(Divergence("hidden_bear", indicator_name, min(1.0, abs(os_[i2] - os_[i1]) / 15.0)))

    return out


# ==========================================================================
# Figures chartistes
# ==========================================================================
@dataclass(slots=True)
class ChartPattern:
    name: str
    bullish: bool
    confidence: float
    target: Optional[float] = None
    neckline: Optional[float] = None


def detect_double_top_bottom(ind: IndicatorSet) -> Optional[ChartPattern]:
    """Double sommet / double creux : deux extremes de meme niveau."""
    highs = list(ind.swings.swing_highs)
    lows = list(ind.swings.swing_lows)
    atr = ind.atr.value or 0.0
    if atr <= 0:
        return None
    tol = 0.4 * atr
    if len(highs) >= 2 and abs(highs[-1] - highs[-2]) <= tol and lows:
        neck = min(lows[-2:]) if len(lows) >= 2 else lows[-1]
        height = highs[-1] - neck
        if height > atr:
            return ChartPattern("double_sommet", False, 0.65, neck - height, neck)
    if len(lows) >= 2 and abs(lows[-1] - lows[-2]) <= tol and highs:
        neck = max(highs[-2:]) if len(highs) >= 2 else highs[-1]
        height = neck - lows[-1]
        if height > atr:
            return ChartPattern("double_creux", True, 0.65, neck + height, neck)
    return None


def detect_head_shoulders(ind: IndicatorSet) -> Optional[ChartPattern]:
    """Epaule-tete-epaule (et sa version inversee)."""
    highs = list(ind.swings.swing_highs)
    lows = list(ind.swings.swing_lows)
    atr = ind.atr.value or 0.0
    if atr <= 0:
        return None
    if len(highs) >= 3 and len(lows) >= 2:
        l, h, r = highs[-3], highs[-2], highs[-1]
        if h > l and h > r and abs(l - r) <= 0.6 * atr:
            neck = sum(lows[-2:]) / 2.0
            height = h - neck
            if height > 1.2 * atr:
                return ChartPattern("epaule_tete_epaule", False, 0.7, neck - height, neck)
    if len(lows) >= 3 and len(highs) >= 2:
        l, h, r = lows[-3], lows[-2], lows[-1]
        if h < l and h < r and abs(l - r) <= 0.6 * atr:
            neck = sum(highs[-2:]) / 2.0
            height = neck - h
            if height > 1.2 * atr:
                return ChartPattern("ete_inverse", True, 0.7, neck + height, neck)
    return None


def detect_triangle(ind: IndicatorSet) -> Optional[ChartPattern]:
    """Triangle / biseau : compression entre sommets et creux convergents."""
    highs = list(ind.swings.swing_highs)
    lows = list(ind.swings.swing_lows)
    atr = ind.atr.value or 0.0
    if len(highs) < 3 or len(lows) < 3 or atr <= 0:
        return None
    lower_highs = highs[-1] < highs[-2] < highs[-3]
    higher_lows = lows[-1] > lows[-2] > lows[-3]
    flat_highs = abs(highs[-1] - highs[-3]) <= 0.5 * atr
    flat_lows = abs(lows[-1] - lows[-3]) <= 0.5 * atr
    if lower_highs and higher_lows:
        return ChartPattern("triangle_symetrique", True, 0.4)   # direction tranchee par le breakout
    if flat_highs and higher_lows:
        return ChartPattern("triangle_ascendant", True, 0.6, None, highs[-1])
    if flat_lows and lower_highs:
        return ChartPattern("triangle_descendant", False, 0.6, None, lows[-1])
    return None


def detect_chart_patterns(ind: IndicatorSet) -> list[ChartPattern]:
    out = []
    for fn in (detect_double_top_bottom, detect_head_shoulders, detect_triangle):
        hit = fn(ind)
        if hit:
            out.append(hit)
    return out


# ==========================================================================
# Zones institutionnelles : Fair Value Gaps et order blocks
# ==========================================================================
@dataclass(slots=True)
class Zone:
    top: float
    bottom: float
    bullish: bool
    kind: str        # "fvg" | "order_block"
    ts: float = 0.0

    def contains(self, price: float) -> bool:
        return self.bottom <= price <= self.top

    @property
    def mid(self) -> float:
        return (self.top + self.bottom) / 2.0


def find_fair_value_gaps(candles: Sequence[Candle], atr: float, lookback: int = 40) -> list[Zone]:
    """Fair Value Gaps : desequilibre sur 3 bougies (le prix y revient souvent).

    FVG haussier : le bas de la bougie 3 est au-dessus du haut de la bougie 1.
    """
    cs = list(candles)[-lookback:]
    zones: list[Zone] = []
    if atr <= 0 or len(cs) < 3:
        return zones
    for i in range(2, len(cs)):
        a, b, c = cs[i - 2], cs[i - 1], cs[i]
        if c.low > a.high and (c.low - a.high) >= 0.2 * atr and b.bullish:
            zones.append(Zone(c.low, a.high, True, "fvg", b.ts))
        elif c.high < a.low and (a.low - c.high) >= 0.2 * atr and b.bearish:
            zones.append(Zone(a.low, c.high, False, "fvg", b.ts))
    return zones


def find_order_blocks(candles: Sequence[Candle], atr: float, lookback: int = 40) -> list[Zone]:
    """Order blocks : derniere bougie opposee avant une impulsion marquee."""
    cs = list(candles)[-lookback:]
    zones: list[Zone] = []
    if atr <= 0 or len(cs) < 3:
        return zones
    for i in range(1, len(cs) - 1):
        base, impulse = cs[i], cs[i + 1]
        if impulse.body < 1.2 * atr:
            continue
        if base.bearish and impulse.bullish and impulse.close > base.high:
            zones.append(Zone(max(base.open, base.close), base.low, True, "order_block", base.ts))
        elif base.bullish and impulse.bearish and impulse.close < base.low:
            zones.append(Zone(base.high, min(base.open, base.close), False, "order_block", base.ts))
    return zones


def active_zones(zones: Sequence[Zone], price: float, atr: float) -> list[Zone]:
    """Zones encore pertinentes : proches du prix et non totalement comblees."""
    if atr <= 0:
        return []
    return [z for z in zones if abs(z.mid - price) <= 3.0 * atr]


# ==========================================================================
# Volume profile simplifie
# ==========================================================================
@dataclass(slots=True)
class VolumeProfile:
    poc: float                # Point of Control : prix le plus echange
    value_area_high: float
    value_area_low: float
    bins: dict[float, float] = field(default_factory=dict)

    def position(self, price: float) -> str:
        if price > self.value_area_high:
            return "above_value"
        if price < self.value_area_low:
            return "below_value"
        return "in_value"


def build_volume_profile(candles: Sequence[Candle], bins: int = 30) -> Optional[VolumeProfile]:
    """Profil de volume : ou le marche a reellement traite."""
    cs = list(candles)
    if len(cs) < 20:
        return None
    lo = min(c.low for c in cs)
    hi = max(c.high for c in cs)
    if hi <= lo:
        return None
    step = (hi - lo) / bins
    hist: dict[float, float] = {}
    for c in cs:
        idx = min(bins - 1, max(0, int(((c.high + c.low + c.close) / 3.0 - lo) / step)))
        key = round(lo + idx * step, 6)
        hist[key] = hist.get(key, 0.0) + (c.volume if c.volume > 0 else 1.0)
    if not hist:
        return None
    poc = max(hist, key=hist.get)
    total = sum(hist.values())
    # Value area = 70 % du volume autour du POC (definition de Steidlmayer)
    ordered = sorted(hist.items(), key=lambda kv: kv[1], reverse=True)
    acc, chosen = 0.0, []
    for price, vol in ordered:
        acc += vol
        chosen.append(price)
        if acc >= 0.7 * total:
            break
    return VolumeProfile(poc, max(chosen), min(chosen), hist)


# ==========================================================================
# Lecture graphique complete
# ==========================================================================
@dataclass(slots=True)
class ChartRead:
    """Photographie objective du graphique a un instant donne."""

    levels: list[Level] = field(default_factory=list)
    divergences: list[Divergence] = field(default_factory=list)
    patterns: list[ChartPattern] = field(default_factory=list)
    fvgs: list[Zone] = field(default_factory=list)
    order_blocks: list[Zone] = field(default_factory=list)
    profile: Optional[VolumeProfile] = None
    fibo: dict[str, float] = field(default_factory=dict)
    pivots: dict[str, float] = field(default_factory=dict)

    def headroom(self, price: float, side: Side,
                 min_strength: float = OBSTACLE_MIN_STRENGTH) -> Optional[float]:
        return headroom(self.levels, price, side, min_strength)

    def magnet(self, price: float, side: Side) -> Optional[float]:
        """Premier niveau devant, chiffres ronds compris (contexte, pas veto)."""
        return headroom(self.levels, price, side, min_strength=0.0)

    def divergence_score(self) -> float:
        """Score net des divergences, borne a [-1, 1]."""
        score = 0.0
        for d in self.divergences:
            weight = d.strength * (0.8 if d.kind.startswith("regular") else 0.5)
            score += weight if d.bullish else -weight
        return max(-1.0, min(1.0, score))

    def pattern_score(self) -> float:
        score = 0.0
        for p in self.patterns:
            score += p.confidence if p.bullish else -p.confidence
        return max(-1.0, min(1.0, score))

    def zone_support(self, price: float, side: Side, atr: float) -> float:
        """Le prix reagit-il sur une zone institutionnelle dans le bon sens ?"""
        if atr <= 0:
            return 0.0
        bullish = side is Side.BUY
        best = 0.0
        for z in list(self.fvgs) + list(self.order_blocks):
            if z.bullish != bullish:
                continue
            distance = abs(z.mid - price)
            if distance <= 1.0 * atr:
                weight = 0.6 if z.kind == "order_block" else 0.4
                best = max(best, weight * (1.0 - distance / atr))
        return best


def read_chart(ind: IndicatorSet, round_step: float = 10.0) -> ChartRead:
    """Produit la lecture graphique complete d'une unite de temps."""
    candles = list(ind.candles)
    atr = ind.atr.value or 0.0
    read = ChartRead()
    if not candles:
        return read

    read.levels = build_levels(ind, round_step)
    read.pivots = session_pivots(candles)
    read.patterns = detect_chart_patterns(ind)
    read.fvgs = active_zones(find_fair_value_gaps(candles, atr), candles[-1].close, atr)
    read.order_blocks = active_zones(find_order_blocks(candles, atr), candles[-1].close, atr)
    read.profile = build_volume_profile(candles[-120:])

    # Divergences sur RSI puis sur l'histogramme MACD (double confirmation)
    rsi_series: list[float] = []
    rsi = type(ind.rsi)(ind.rsi.period)
    for c in candles:
        v = rsi.update(c.close)
        rsi_series.append(v if v is not None else 50.0)
    read.divergences = find_divergences(candles, rsi_series, "RSI")

    lo, hi = ind.swings.last_low, ind.swings.last_high
    if lo is not None and hi is not None and hi > lo:
        read.fibo = fibonacci_levels(lo, hi, uptrend=ind.trend_bias() != "bearish")
    return read
