"""Indicateurs techniques incrementaux (O(1) par bougie).

Chaque indicateur garde son etat interne : on appelle `update(...)` a chaque
nouvelle bougie cloturee et on lit `.value`. C'est ce qui permet au robot de
reagir en quelques microsecondes sur du court terme, sans recalculer une
serie complete a chaque tick.

Conventions academiques respectees :
  - RSI et ATR utilisent le lissage de Wilder (et non une SMA),
  - ADX suit la formule originale de J. Welles Wilder (1978),
  - les bandes de Bollinger utilisent l'ecart-type de population sur N periodes.
"""
from __future__ import annotations

import math
from collections import deque
from typing import Deque, Iterable, Optional, Sequence

from .core import Candle


class SMA:
    """Moyenne mobile simple."""

    def __init__(self, period: int) -> None:
        self.period = period
        self._buf: Deque[float] = deque(maxlen=period)
        self._sum = 0.0
        self.value: Optional[float] = None

    def update(self, x: float) -> Optional[float]:
        if len(self._buf) == self.period:
            self._sum -= self._buf[0]
        self._buf.append(x)
        self._sum += x
        if len(self._buf) == self.period:
            self.value = self._sum / self.period
        return self.value

    @property
    def ready(self) -> bool:
        return self.value is not None


class EMA:
    """Moyenne mobile exponentielle, amorcee par une SMA (pratique standard)."""

    def __init__(self, period: int) -> None:
        self.period = period
        self.k = 2.0 / (period + 1.0)
        self._seed = SMA(period)
        self.value: Optional[float] = None

    def update(self, x: float) -> Optional[float]:
        if self.value is None:
            if self._seed.update(x) is not None:
                self.value = self._seed.value
        else:
            self.value += self.k * (x - self.value)
        return self.value

    @property
    def ready(self) -> bool:
        return self.value is not None


class WilderMA:
    """Lissage de Wilder : val = val + (x - val) / period."""

    def __init__(self, period: int) -> None:
        self.period = period
        self._seed = SMA(period)
        self.value: Optional[float] = None

    def update(self, x: float) -> Optional[float]:
        if self.value is None:
            if self._seed.update(x) is not None:
                self.value = self._seed.value
        else:
            self.value += (x - self.value) / self.period
        return self.value

    @property
    def ready(self) -> bool:
        return self.value is not None


class StdDev:
    """Ecart-type de population sur N periodes."""

    def __init__(self, period: int) -> None:
        self.period = period
        self._buf: Deque[float] = deque(maxlen=period)
        self.value: Optional[float] = None
        self.mean: Optional[float] = None

    def update(self, x: float) -> Optional[float]:
        self._buf.append(x)
        if len(self._buf) == self.period:
            mean = sum(self._buf) / self.period
            var = sum((v - mean) ** 2 for v in self._buf) / self.period
            self.mean = mean
            self.value = math.sqrt(var)
        return self.value

    @property
    def ready(self) -> bool:
        return self.value is not None


class ATR:
    """Average True Range (Wilder). Mesure de volatilite = base du SL/TP."""

    def __init__(self, period: int = 14) -> None:
        self.period = period
        self._ma = WilderMA(period)
        self._prev_close: Optional[float] = None
        self.value: Optional[float] = None

    def update(self, c: Candle) -> Optional[float]:
        if self._prev_close is None:
            tr = c.high - c.low
        else:
            tr = max(
                c.high - c.low,
                abs(c.high - self._prev_close),
                abs(c.low - self._prev_close),
            )
        self._prev_close = c.close
        self.value = self._ma.update(tr)
        return self.value

    @property
    def ready(self) -> bool:
        return self.value is not None


class RSI:
    """Relative Strength Index (Wilder, 14 par defaut)."""

    def __init__(self, period: int = 14) -> None:
        self.period = period
        self._gain = WilderMA(period)
        self._loss = WilderMA(period)
        self._prev: Optional[float] = None
        self.value: Optional[float] = None

    def update(self, close: float) -> Optional[float]:
        if self._prev is not None:
            delta = close - self._prev
            g = self._gain.update(max(delta, 0.0))
            l = self._loss.update(max(-delta, 0.0))
            if g is not None and l is not None:
                if l == 0:
                    self.value = 100.0
                else:
                    rs = g / l
                    self.value = 100.0 - (100.0 / (1.0 + rs))
        self._prev = close
        return self.value

    @property
    def ready(self) -> bool:
        return self.value is not None


class MACD:
    """MACD (12, 26, 9) : ligne, signal et histogramme."""

    def __init__(self, fast: int = 12, slow: int = 26, signal: int = 9) -> None:
        self.fast = EMA(fast)
        self.slow = EMA(slow)
        self.signal = EMA(signal)
        self.line: Optional[float] = None
        self.signal_value: Optional[float] = None
        self.hist: Optional[float] = None
        self.prev_hist: Optional[float] = None

    def update(self, close: float) -> Optional[float]:
        f = self.fast.update(close)
        s = self.slow.update(close)
        if f is not None and s is not None:
            self.line = f - s
            sig = self.signal.update(self.line)
            if sig is not None:
                self.prev_hist = self.hist
                self.signal_value = sig
                self.hist = self.line - sig
        return self.hist

    @property
    def ready(self) -> bool:
        return self.hist is not None

    @property
    def rising(self) -> bool:
        return self.hist is not None and self.prev_hist is not None and self.hist > self.prev_hist

    @property
    def falling(self) -> bool:
        return self.hist is not None and self.prev_hist is not None and self.hist < self.prev_hist


class Bollinger:
    """Bandes de Bollinger (20, 2). Sert au filtre de volatilite (squeeze)."""

    def __init__(self, period: int = 20, mult: float = 2.0) -> None:
        self.mult = mult
        self._sd = StdDev(period)
        self.middle: Optional[float] = None
        self.upper: Optional[float] = None
        self.lower: Optional[float] = None

    def update(self, close: float) -> Optional[float]:
        sd = self._sd.update(close)
        if sd is not None and self._sd.mean is not None:
            self.middle = self._sd.mean
            self.upper = self.middle + self.mult * sd
            self.lower = self.middle - self.mult * sd
        return self.middle

    @property
    def ready(self) -> bool:
        return self.middle is not None

    @property
    def width(self) -> float:
        """Largeur relative des bandes (proxy de compression de volatilite)."""
        if not self.ready or not self.middle:
            return 0.0
        return (self.upper - self.lower) / self.middle


class ADX:
    """ADX + DI+ / DI- (Wilder). Filtre : tendance vs range."""

    def __init__(self, period: int = 14) -> None:
        self.period = period
        self._tr = WilderMA(period)
        self._plus = WilderMA(period)
        self._minus = WilderMA(period)
        self._dx = WilderMA(period)
        self._prev: Optional[Candle] = None
        self.plus_di: Optional[float] = None
        self.minus_di: Optional[float] = None
        self.value: Optional[float] = None

    def update(self, c: Candle) -> Optional[float]:
        if self._prev is not None:
            up = c.high - self._prev.high
            down = self._prev.low - c.low
            plus_dm = up if (up > down and up > 0) else 0.0
            minus_dm = down if (down > up and down > 0) else 0.0
            tr = max(
                c.high - c.low,
                abs(c.high - self._prev.close),
                abs(c.low - self._prev.close),
            )
            atr = self._tr.update(tr)
            pdm = self._plus.update(plus_dm)
            mdm = self._minus.update(minus_dm)
            if atr and atr > 0 and pdm is not None and mdm is not None:
                self.plus_di = 100.0 * pdm / atr
                self.minus_di = 100.0 * mdm / atr
                denom = self.plus_di + self.minus_di
                dx = 100.0 * abs(self.plus_di - self.minus_di) / denom if denom > 0 else 0.0
                self.value = self._dx.update(dx)
        self._prev = c
        return self.value

    @property
    def ready(self) -> bool:
        return self.value is not None


class Donchian:
    """Canal de Donchian : plus haut / plus bas sur N periodes (breakout)."""

    def __init__(self, period: int = 20) -> None:
        self.period = period
        self._highs: Deque[float] = deque(maxlen=period)
        self._lows: Deque[float] = deque(maxlen=period)
        self.upper: Optional[float] = None
        self.lower: Optional[float] = None

    def update(self, c: Candle) -> None:
        self._highs.append(c.high)
        self._lows.append(c.low)
        if len(self._highs) == self.period:
            self.upper = max(self._highs)
            self.lower = min(self._lows)

    def exclude_last(self) -> tuple[Optional[float], Optional[float]]:
        """Bornes du canal SANS la bougie courante (evite le look-ahead)."""
        if len(self._highs) < 2:
            return None, None
        return max(list(self._highs)[:-1]), min(list(self._lows)[:-1])

    @property
    def ready(self) -> bool:
        return self.upper is not None


class VWAP:
    """VWAP de session, remis a zero a chaque nouvelle journee UTC."""

    def __init__(self) -> None:
        self._pv = 0.0
        self._vol = 0.0
        self._day: Optional[int] = None
        self.value: Optional[float] = None

    def update(self, c: Candle) -> Optional[float]:
        day = int(c.ts // 86400)
        if self._day != day:
            self._day = day
            self._pv = 0.0
            self._vol = 0.0
        typical = (c.high + c.low + c.close) / 3.0
        vol = c.volume if c.volume > 0 else 1.0
        self._pv += typical * vol
        self._vol += vol
        if self._vol > 0:
            self.value = self._pv / self._vol
        return self.value

    @property
    def ready(self) -> bool:
        return self.value is not None


class SwingDetector:
    """Detecte les swings (fractales) pour lire la structure de marche.

    Un swing haut = un plus haut entoure de `left`/`right` bougies plus basses.
    On en deduit la structure HH/HL (haussiere) ou LH/LL (baissiere), au coeur
    de l'analyse technique classique (Dow) et du price action moderne.
    """

    def __init__(self, left: int = 2, right: int = 2, keep: int = 12) -> None:
        self.left = left
        self.right = right
        self._window: Deque[Candle] = deque(maxlen=left + right + 1)
        self.swing_highs: Deque[float] = deque(maxlen=keep)
        self.swing_lows: Deque[float] = deque(maxlen=keep)

    def update(self, c: Candle) -> None:
        self._window.append(c)
        if len(self._window) < self._window.maxlen:
            return
        pivot = self._window[self.left]
        others = [x for i, x in enumerate(self._window) if i != self.left]
        if all(pivot.high >= o.high for o in others):
            self.swing_highs.append(pivot.high)
        if all(pivot.low <= o.low for o in others):
            self.swing_lows.append(pivot.low)

    @property
    def last_high(self) -> Optional[float]:
        return self.swing_highs[-1] if self.swing_highs else None

    @property
    def last_low(self) -> Optional[float]:
        return self.swing_lows[-1] if self.swing_lows else None

    def structure(self) -> str:
        """Retourne 'bullish', 'bearish' ou 'range'."""
        if len(self.swing_highs) < 2 or len(self.swing_lows) < 2:
            return "range"
        hh = self.swing_highs[-1] > self.swing_highs[-2]
        hl = self.swing_lows[-1] > self.swing_lows[-2]
        lh = self.swing_highs[-1] < self.swing_highs[-2]
        ll = self.swing_lows[-1] < self.swing_lows[-2]
        if hh and hl:
            return "bullish"
        if lh and ll:
            return "bearish"
        return "range"


class IndicatorSet:
    """Paquet d'indicateurs applique a une unite de temps donnee."""

    def __init__(
        self,
        ema_fast: int = 9,
        ema_mid: int = 21,
        ema_slow: int = 50,
        rsi_period: int = 14,
        atr_period: int = 14,
        adx_period: int = 14,
        bb_period: int = 20,
        donchian_period: int = 20,
        history: int = 300,
    ) -> None:
        self.ema_fast = EMA(ema_fast)
        self.ema_mid = EMA(ema_mid)
        self.ema_slow = EMA(ema_slow)
        self.rsi = RSI(rsi_period)
        self.atr = ATR(atr_period)
        self.adx = ADX(adx_period)
        self.bb = Bollinger(bb_period)
        self.macd = MACD()
        self.donchian = Donchian(donchian_period)
        self.vwap = VWAP()
        self.swings = SwingDetector()
        self.stoch = Stochastic()
        self.cci = CCI()
        self.willr = WilliamsR()
        self.obv = OBV()
        self.mfi = MFI()
        self.keltner = Keltner()
        self.supertrend = Supertrend()
        self.ichimoku = Ichimoku()
        self.hurst = HurstRegime()
        self.candles: Deque[Candle] = deque(maxlen=history)
        self.atr_history: Deque[float] = deque(maxlen=100)
        self._prev_ema_fast: Optional[float] = None
        self._prev_ema_mid: Optional[float] = None

    def update(self, c: Candle) -> None:
        self._prev_ema_fast = self.ema_fast.value
        self._prev_ema_mid = self.ema_mid.value
        self.candles.append(c)
        self.ema_fast.update(c.close)
        self.ema_mid.update(c.close)
        self.ema_slow.update(c.close)
        self.rsi.update(c.close)
        self.atr.update(c)
        self.adx.update(c)
        self.bb.update(c.close)
        self.macd.update(c.close)
        self.donchian.update(c)
        self.vwap.update(c)
        self.swings.update(c)
        self.stoch.update(c)
        self.cci.update(c)
        self.willr.update(c)
        self.obv.update(c)
        self.mfi.update(c)
        self.keltner.update(c)
        self.supertrend.update(c)
        self.ichimoku.update(c)
        self.hurst.update(c.close)
        if self.atr.value:
            self.atr_history.append(self.atr.value)

    @property
    def ready(self) -> bool:
        return (
            self.ema_slow.ready
            and self.rsi.ready
            and self.atr.ready
            and self.adx.ready
            and self.bb.ready
        )

    @property
    def last(self) -> Optional[Candle]:
        return self.candles[-1] if self.candles else None

    def ema_cross_up(self) -> bool:
        """Croisement haussier EMA rapide / EMA moyenne sur la derniere bougie."""
        if None in (self._prev_ema_fast, self._prev_ema_mid, self.ema_fast.value, self.ema_mid.value):
            return False
        return self._prev_ema_fast <= self._prev_ema_mid and self.ema_fast.value > self.ema_mid.value

    def ema_cross_down(self) -> bool:
        if None in (self._prev_ema_fast, self._prev_ema_mid, self.ema_fast.value, self.ema_mid.value):
            return False
        return self._prev_ema_fast >= self._prev_ema_mid and self.ema_fast.value < self.ema_mid.value

    def atr_percentile(self) -> float:
        """Position de l'ATR courant dans son historique (0..1).

        Sert a eviter d'entrer quand la volatilite est anormalement basse
        (marche mort) ou explosive (post-news chaotique).
        """
        if not self.atr.value or len(self.atr_history) < 20:
            return 0.5
        below = sum(1 for v in self.atr_history if v <= self.atr.value)
        return below / len(self.atr_history)

    def squeeze(self) -> bool:
        """Squeeze de Carter : bandes de Bollinger a l'interieur des canaux de Keltner.

        Compression de volatilite -> expansion imminente. On ne prend pas
        d'entree de tendance dedans, on attend la sortie du squeeze.
        """
        if not (self.bb.ready and self.keltner.ready):
            return False
        return self.bb.upper < self.keltner.upper and self.bb.lower > self.keltner.lower

    def trend_bias(self) -> str:
        """Biais de tendance combinant EMA, structure et ADX."""
        if not self.ready:
            return "neutral"
        price = self.candles[-1].close
        up = price > self.ema_slow.value and self.ema_mid.value > self.ema_slow.value
        down = price < self.ema_slow.value and self.ema_mid.value < self.ema_slow.value
        struct = self.swings.structure()
        if up and struct != "bearish":
            return "bullish"
        if down and struct != "bullish":
            return "bearish"
        return "neutral"


# ==========================================================================
# Batterie etendue : oscillateurs, volatilite, volume, regime de marche
# ==========================================================================
class Stochastic:
    """Stochastique %K / %D (14, 3, 3) — surachat / survente court terme."""

    def __init__(self, k_period: int = 14, k_smooth: int = 3, d_period: int = 3) -> None:
        self._highs: Deque[float] = deque(maxlen=k_period)
        self._lows: Deque[float] = deque(maxlen=k_period)
        self._k_raw = SMA(k_smooth)
        self._d = SMA(d_period)
        self.k: Optional[float] = None
        self.d: Optional[float] = None
        self.prev_k: Optional[float] = None

    def update(self, c: Candle) -> Optional[float]:
        self._highs.append(c.high)
        self._lows.append(c.low)
        if len(self._highs) < self._highs.maxlen:
            return None
        hh, ll = max(self._highs), min(self._lows)
        raw = 50.0 if hh == ll else 100.0 * (c.close - ll) / (hh - ll)
        self.prev_k = self.k
        self.k = self._k_raw.update(raw)
        if self.k is not None:
            self.d = self._d.update(self.k)
        return self.k

    @property
    def ready(self) -> bool:
        return self.k is not None and self.d is not None

    def cross_up(self) -> bool:
        return self.ready and self.prev_k is not None and self.prev_k <= self.d < self.k

    def cross_down(self) -> bool:
        return self.ready and self.prev_k is not None and self.prev_k >= self.d > self.k


class CCI:
    """Commodity Channel Index (Lambert, 1980) — concu a l'origine pour les matieres premieres."""

    def __init__(self, period: int = 20) -> None:
        self.period = period
        self._buf: Deque[float] = deque(maxlen=period)
        self.value: Optional[float] = None

    def update(self, c: Candle) -> Optional[float]:
        tp = (c.high + c.low + c.close) / 3.0
        self._buf.append(tp)
        if len(self._buf) == self.period:
            mean = sum(self._buf) / self.period
            mad = sum(abs(v - mean) for v in self._buf) / self.period
            self.value = 0.0 if mad == 0 else (tp - mean) / (0.015 * mad)
        return self.value

    @property
    def ready(self) -> bool:
        return self.value is not None


class WilliamsR:
    """Williams %R (-100 a 0)."""

    def __init__(self, period: int = 14) -> None:
        self._highs: Deque[float] = deque(maxlen=period)
        self._lows: Deque[float] = deque(maxlen=period)
        self.value: Optional[float] = None

    def update(self, c: Candle) -> Optional[float]:
        self._highs.append(c.high)
        self._lows.append(c.low)
        if len(self._highs) == self._highs.maxlen:
            hh, ll = max(self._highs), min(self._lows)
            self.value = -50.0 if hh == ll else -100.0 * (hh - c.close) / (hh - ll)
        return self.value

    @property
    def ready(self) -> bool:
        return self.value is not None


class OBV:
    """On-Balance Volume (Granville) — confirmation par le volume."""

    def __init__(self, slope_period: int = 10) -> None:
        self.value = 0.0
        self._prev_close: Optional[float] = None
        self._hist: Deque[float] = deque(maxlen=slope_period)

    def update(self, c: Candle) -> float:
        vol = c.volume if c.volume > 0 else 1.0
        if self._prev_close is not None:
            if c.close > self._prev_close:
                self.value += vol
            elif c.close < self._prev_close:
                self.value -= vol
        self._prev_close = c.close
        self._hist.append(self.value)
        return self.value

    @property
    def slope(self) -> float:
        """Pente normalisee de l'OBV sur la fenetre (-1..1)."""
        if len(self._hist) < 3:
            return 0.0
        first, last = self._hist[0], self._hist[-1]
        span = max(abs(v) for v in self._hist) or 1.0
        return max(-1.0, min(1.0, (last - first) / span))


class MFI:
    """Money Flow Index — RSI pondere par le volume."""

    def __init__(self, period: int = 14) -> None:
        self.period = period
        self._pos: Deque[float] = deque(maxlen=period)
        self._neg: Deque[float] = deque(maxlen=period)
        self._prev_tp: Optional[float] = None
        self.value: Optional[float] = None

    def update(self, c: Candle) -> Optional[float]:
        tp = (c.high + c.low + c.close) / 3.0
        flow = tp * (c.volume if c.volume > 0 else 1.0)
        if self._prev_tp is not None:
            self._pos.append(flow if tp > self._prev_tp else 0.0)
            self._neg.append(flow if tp < self._prev_tp else 0.0)
            if len(self._pos) == self.period:
                neg = sum(self._neg)
                self.value = 100.0 if neg == 0 else 100.0 - 100.0 / (1.0 + sum(self._pos) / neg)
        self._prev_tp = tp
        return self.value

    @property
    def ready(self) -> bool:
        return self.value is not None


class Keltner:
    """Canaux de Keltner (EMA + n x ATR). Couple aux Bollinger = squeeze de Carter."""

    def __init__(self, period: int = 20, atr_period: int = 10, mult: float = 1.5) -> None:
        self._ema = EMA(period)
        self._atr = ATR(atr_period)
        self.mult = mult
        self.middle: Optional[float] = None
        self.upper: Optional[float] = None
        self.lower: Optional[float] = None

    def update(self, c: Candle) -> Optional[float]:
        mid = self._ema.update(c.close)
        atr = self._atr.update(c)
        if mid is not None and atr is not None:
            self.middle, self.upper, self.lower = mid, mid + self.mult * atr, mid - self.mult * atr
        return self.middle

    @property
    def ready(self) -> bool:
        return self.middle is not None


class Supertrend:
    """Supertrend (ATR) — filtre directionnel robuste, tres utilise sur l'or."""

    def __init__(self, period: int = 10, mult: float = 3.0) -> None:
        self._atr = ATR(period)
        self.mult = mult
        self.direction = 0          # +1 haussier, -1 baissier
        self.value: Optional[float] = None
        self._final_upper: Optional[float] = None
        self._final_lower: Optional[float] = None
        self._prev_close: Optional[float] = None

    def update(self, c: Candle) -> Optional[float]:
        atr = self._atr.update(c)
        if atr is None:
            self._prev_close = c.close
            return None
        hl2 = (c.high + c.low) / 2.0
        basic_upper = hl2 + self.mult * atr
        basic_lower = hl2 - self.mult * atr

        if self._final_upper is None or self._prev_close is None:
            self._final_upper, self._final_lower = basic_upper, basic_lower
            self.direction = 1 if c.close >= hl2 else -1
        else:
            self._final_upper = (
                basic_upper if basic_upper < self._final_upper or self._prev_close > self._final_upper
                else self._final_upper
            )
            self._final_lower = (
                basic_lower if basic_lower > self._final_lower or self._prev_close < self._final_lower
                else self._final_lower
            )
            if self.direction == 1 and c.close < self._final_lower:
                self.direction = -1
            elif self.direction == -1 and c.close > self._final_upper:
                self.direction = 1

        self.value = self._final_lower if self.direction == 1 else self._final_upper
        self._prev_close = c.close
        return self.value

    @property
    def ready(self) -> bool:
        return self.value is not None


class Ichimoku:
    """Ichimoku Kinko Hyo (9, 26, 52) — vision structurelle complete."""

    def __init__(self, tenkan: int = 9, kijun: int = 26, senkou_b: int = 52) -> None:
        self._h_t: Deque[float] = deque(maxlen=tenkan)
        self._l_t: Deque[float] = deque(maxlen=tenkan)
        self._h_k: Deque[float] = deque(maxlen=kijun)
        self._l_k: Deque[float] = deque(maxlen=kijun)
        self._h_s: Deque[float] = deque(maxlen=senkou_b)
        self._l_s: Deque[float] = deque(maxlen=senkou_b)
        self._shift = kijun
        self._span_a: Deque[float] = deque(maxlen=kijun + 1)
        self._span_b: Deque[float] = deque(maxlen=kijun + 1)
        self.tenkan: Optional[float] = None
        self.kijun: Optional[float] = None
        self.cloud_top: Optional[float] = None
        self.cloud_bottom: Optional[float] = None

    @staticmethod
    def _mid(highs: Deque[float], lows: Deque[float]) -> Optional[float]:
        if len(highs) < highs.maxlen:
            return None
        return (max(highs) + min(lows)) / 2.0

    def update(self, c: Candle) -> None:
        for h, l in ((self._h_t, self._l_t), (self._h_k, self._l_k), (self._h_s, self._l_s)):
            h.append(c.high)
            l.append(c.low)
        self.tenkan = self._mid(self._h_t, self._l_t)
        self.kijun = self._mid(self._h_k, self._l_k)
        span_b = self._mid(self._h_s, self._l_s)
        if self.tenkan is not None and self.kijun is not None:
            self._span_a.append((self.tenkan + self.kijun) / 2.0)
        if span_b is not None:
            self._span_b.append(span_b)
        # Le nuage projete a 26 periodes : la valeur active aujourd'hui est
        # celle calculee il y a 26 bougies.
        if len(self._span_a) == self._span_a.maxlen and len(self._span_b) == self._span_b.maxlen:
            a, b = self._span_a[0], self._span_b[0]
            self.cloud_top, self.cloud_bottom = max(a, b), min(a, b)

    @property
    def ready(self) -> bool:
        return self.cloud_top is not None

    def position(self, price: float) -> str:
        """'above' (haussier), 'below' (baissier) ou 'inside' (zone neutre)."""
        if not self.ready:
            return "inside"
        if price > self.cloud_top:
            return "above"
        if price < self.cloud_bottom:
            return "below"
        return "inside"


class HurstRegime:
    """Exposant de Hurst par R/S — classe le marche : tendance, aleatoire, retour a la moyenne.

    H > 0.55 : persistant (suivi de tendance pertinent)
    H ~ 0.5  : marche aleatoire (rester a l'ecart)
    H < 0.45 : anti-persistant (jouer les retours a la moyenne)
    """

    def __init__(self, window: int = 96) -> None:
        self._buf: Deque[float] = deque(maxlen=window)
        self.value: Optional[float] = None

    def update(self, close: float) -> Optional[float]:
        self._buf.append(close)
        if len(self._buf) < self._buf.maxlen:
            return None
        series = list(self._buf)
        rets = [series[i] - series[i - 1] for i in range(1, len(series))]
        n = len(rets)
        scales = [s for s in (8, 16, 32, 64) if s <= n]
        if len(scales) < 2:
            return None
        logs_x, logs_y = [], []
        for s in scales:
            rs_vals = []
            for start in range(0, n - s + 1, s):
                chunk = rets[start:start + s]
                mean = sum(chunk) / s
                dev, cum = 0.0, []
                for v in chunk:
                    dev += v - mean
                    cum.append(dev)
                rng = max(cum) - min(cum)
                sd = math.sqrt(sum((v - mean) ** 2 for v in chunk) / s)
                if sd > 0 and rng > 0:
                    rs_vals.append(rng / sd)
            if rs_vals:
                logs_x.append(math.log(s))
                logs_y.append(math.log(sum(rs_vals) / len(rs_vals)))
        if len(logs_x) < 2:
            return None
        mx = sum(logs_x) / len(logs_x)
        my = sum(logs_y) / len(logs_y)
        denom = sum((x - mx) ** 2 for x in logs_x)
        if denom == 0:
            return None
        self.value = sum((x - mx) * (y - my) for x, y in zip(logs_x, logs_y)) / denom
        return self.value

    @property
    def regime(self) -> str:
        if self.value is None:
            return "unknown"
        if self.value > 0.55:
            return "trend"
        if self.value < 0.45:
            return "mean_revert"
        return "random"


def correlation(a: Sequence[float], b: Sequence[float]) -> float:
    """Correlation de Pearson entre deux series de meme longueur."""
    n = min(len(a), len(b))
    if n < 3:
        return 0.0
    a, b = list(a)[-n:], list(b)[-n:]
    ma, mb = sum(a) / n, sum(b) / n
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    da = math.sqrt(sum((x - ma) ** 2 for x in a))
    db = math.sqrt(sum((y - mb) ** 2 for y in b))
    if da == 0 or db == 0:
        return 0.0
    return max(-1.0, min(1.0, num / (da * db)))
