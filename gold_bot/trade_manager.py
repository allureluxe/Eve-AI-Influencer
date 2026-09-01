"""Gestion dynamique des positions : SL, TP, trailing et extension d'objectif.

Le gestionnaire protege le capital, encaisse les petits gains quand la
puissance du mouvement baisse et laisse courir les gagnants quand la
dynamique reste forte.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Sequence

from .candles import opposing_reversal, scan as scan_candles
from .chart import ChartRead
from .core import Candle, Position, Side, Tick
from .indicators import IndicatorSet
from .news import NewsWindow

logger = logging.getLogger(__name__)
COST_FLOOR_SAFETY = 0.90


class ActionType(str, Enum):
    MODIFY_STOP = "MODIFY_STOP"
    MODIFY_TARGET = "MODIFY_TARGET"
    PARTIAL_CLOSE = "PARTIAL_CLOSE"
    CLOSE = "CLOSE"


@dataclass(slots=True)
class TradeAction:
    type: ActionType
    position_id: str
    price: Optional[float] = None
    volume: Optional[float] = None
    reason: str = ""

    def __str__(self) -> str:  # pragma: no cover
        target = f" -> {self.price}" if self.price is not None else ""
        return f"{self.type.value}{target} ({self.reason})"


@dataclass(slots=True)
class TradeManagerConfig:
    atr_stop_mult: float = 1.6
    min_stop_atr: float = 0.8
    max_stop_atr: float = 3.0
    tp_r_multiple: float = 2.0
    spread_buffer_mult: float = 1.5
    max_cost_ratio_pct: float = 15.0
    max_stop_atr_for_cost: float = 4.0

    breakeven_at_r: float = 0.8
    breakeven_offset_r: float = 0.08

    partial_enabled: bool = True
    partial_at_r: float = 1.0
    partial_fraction: float = 0.4

    trail_start_r: float = 1.0
    trail_atr_mult: float = 1.8
    trail_tighten_atr_mult: float = 1.0

    extend_enabled: bool = True
    extend_at_progress: float = 0.85
    extend_by_atr: float = 1.2
    extend_by_r_min: float = 0.5
    max_extensions: int = 4
    extend_min_momentum: float = 0.35
    lock_r_on_extend: float = 0.35
    lock_back_atr: float = 1.1

    # Scalping : a ~1R, un petit gain est deja suffisamment significatif
    # pour le petit capital. On encaisse si la dynamique faiblit, mais on
    # laisse le runner vivre si le mouvement reste fort.
    micro_profit_enabled: bool = True
    micro_profit_at_r: float = 0.90
    micro_profit_min_momentum: float = 0.20

    time_stop_minutes: float = 240.0
    time_stop_min_r: float = 0.25
    reversal_exit_r: float = 0.5
    news_tighten_atr_mult: float = 0.9
    max_adverse_r: float = 1.0


@dataclass(slots=True)
class Momentum:
    score: float
    reasons: list[str] = field(default_factory=list)

    @property
    def favorable(self) -> bool:
        return self.score > 0


def compute_momentum(position: Position, ind: IndicatorSet,
                     chart: Optional[ChartRead] = None) -> Momentum:
    bullish = position.side is Side.BUY
    sign = 1.0 if bullish else -1.0
    score, reasons = 0.0, []
    if not ind.ready or not ind.last:
        return Momentum(0.0, ["indicateurs incomplets"])
    price = ind.last.close
    if ind.supertrend.ready:
        if (ind.supertrend.direction > 0) == bullish:
            score += 0.25; reasons.append("supertrend dans le sens")
        else:
            score -= 0.30; reasons.append("supertrend retourne contre la position")
    if ind.ema_fast.ready:
        if sign * (price - ind.ema_fast.value) > 0:
            score += 0.15; reasons.append("prix du bon cote de l'EMA rapide")
        else:
            score -= 0.15; reasons.append("prix sous l'EMA rapide")
    if ind.macd.ready:
        if sign * ind.macd.histogram > 0:
            score += 0.20; reasons.append("MACD impulsion favorable")
        else:
            score -= 0.18; reasons.append("MACD impulsion contraire")
    if ind.adx.ready:
        if ind.adx.value >= 20:
            score += 0.10; reasons.append("ADX confirme une vraie impulsion")
        elif ind.adx.value < 14:
            score -= 0.08; reasons.append("ADX faible")
    if ind.rsi.ready:
        rsi = ind.rsi.value
        if (bullish and rsi > 52) or ((not bullish) and rsi < 48):
            score += 0.10; reasons.append("RSI dans le sens")
        if (bullish and rsi > 74) or ((not bullish) and rsi < 26):
            score -= 0.10; reasons.append("RSI en zone d'epuisement")
    if chart is not None:
        room = chart.headroom(price, position.side)
        if room is not None:
            if room > 0:
                score += 0.08; reasons.append("espace devant")
            else:
                score -= 0.10; reasons.append("obstacle devant")
    return Momentum(max(-1.0, min(1.0, score)), reasons)


class TradeManager:
    def __init__(self, config: Optional[TradeManagerConfig] = None):
        self.config = config or TradeManagerConfig()

    def initial_levels(self, entry_price: float, side: Side, atr: float,
                       spread: float = 0.0, structure_stop_distance: float = 0.0,
                       digits: int = 2) -> tuple[float, float]:
        cfg = self.config
        sign = side.sign
        distance = structure_stop_distance or cfg.atr_stop_mult * atr
        distance = max(cfg.min_stop_atr * atr, min(cfg.max_stop_atr * atr, distance))
        distance += cfg.spread_buffer_mult * max(0.0, spread)
        if cfg.max_cost_ratio_pct > 0 and atr > 0:
            cible = cfg.max_cost_ratio_pct * COST_FLOOR_SAFETY / 100.0
            plancher = min(spread / cible if spread > 0 else 0.0, cfg.max_stop_atr_for_cost * atr)
            distance = max(distance, plancher)
        stop = entry_price - sign * distance
        target = entry_price + sign * distance * cfg.tp_r_multiple
        return round(stop, digits), round(target, digits)

    def cost_ratio(self, atr: float, spread: float, structure_stop_distance: float = 0.0) -> float:
        cfg = self.config
        if atr <= 0 or spread <= 0:
            return 0.0
        distance = structure_stop_distance or cfg.atr_stop_mult * atr
        distance = max(cfg.min_stop_atr * atr, min(cfg.max_stop_atr * atr, distance))
        distance += cfg.spread_buffer_mult * spread
        if cfg.max_cost_ratio_pct > 0:
            cible = cfg.max_cost_ratio_pct * COST_FLOOR_SAFETY / 100.0
            plancher = min(spread / cible, cfg.max_stop_atr_for_cost * atr)
            distance = max(distance, plancher)
        return spread / distance * 100.0

    def manage(self, position: Position, tick: Tick, ind: IndicatorSet,
               chart: Optional[ChartRead] = None, news: Optional[NewsWindow] = None,
               digits: int = 2, now: Optional[float] = None) -> list[TradeAction]:
        cfg = self.config
        now = now or time.time()
        actions: list[TradeAction] = []
        price = tick.exit_price_for(position.side)
        position.track(price)
        atr = ind.atr.value or 0.0
        if atr <= 0:
            return actions
        r_now = position.r_multiple(price)
        sign = position.side.sign
        momentum = compute_momentum(position, ind, chart)

        exit_action = self._safety_exits(position, price, r_now, momentum, now)
        if exit_action:
            return [exit_action]

        # Micro-profit : vers 0.90R, encaisser quand l'impulsion retombe.
        # Si l'impulsion est encore bonne, aucune fermeture : le runner
        # reste ouvert et le moteur d'entrees peut ajouter un etage protege.
        if (cfg.micro_profit_enabled and r_now >= cfg.micro_profit_at_r
                and momentum.score < cfg.micro_profit_min_momentum):
            return [TradeAction(
                ActionType.CLOSE, position.id,
                reason=(f"micro-profit {r_now:+.2f}R : dynamique faible "
                        f"({momentum.score:+.2f}), gain encaisse"))]

        new_stop = position.stop_loss
        if not position.breakeven_done and r_now >= cfg.breakeven_at_r:
            be = position.entry_price + sign * cfg.breakeven_offset_r * position.initial_risk
            if sign * (be - new_stop) > 0:
                new_stop = be
                position.breakeven_done = True
                actions.append(TradeAction(
                    ActionType.MODIFY_STOP, position.id, round(be, digits),
                    reason=f"break-even a {r_now:.2f}R : le trade ne peut plus perdre"))

        if r_now >= cfg.trail_start_r:
            mult = cfg.trail_atr_mult if momentum.favorable else cfg.trail_tighten_atr_mult
            trail = position.max_favorable - sign * mult * atr
            if sign * (trail - new_stop) > 0:
                new_stop = trail

        if news is not None and news.tighten_stops and r_now > 0:
            protective = price - sign * cfg.news_tighten_atr_mult * atr
            if sign * (protective - new_stop) > 0:
                new_stop = protective
                actions.append(TradeAction(
                    ActionType.MODIFY_STOP, position.id, round(new_stop, digits),
                    reason=f"annonce imminente : stop resserre ({news.reason or 'calendrier'})"))

        if (cfg.partial_enabled and not position.partial_done
                and r_now >= cfg.partial_at_r and position.volume > 0):
            volume = position.volume * cfg.partial_fraction
            if volume > 0:
                position.partial_done = True
                actions.append(TradeAction(
                    ActionType.PARTIAL_CLOSE, position.id, volume=round(volume, 8),
                    reason=f"prise partielle de {cfg.partial_fraction:.0%} a {r_now:.2f}R"))

        progress = position.progress_to_tp(price)
        if (cfg.extend_enabled and progress >= cfg.extend_at_progress
                and position.tp_extensions < cfg.max_extensions):
            if momentum.score >= cfg.extend_min_momentum:
                step = max(cfg.extend_by_atr * atr, cfg.extend_by_r_min * position.initial_risk)
                new_tp = position.take_profit + sign * step
                if chart is not None:
                    room = chart.headroom(price, position.side)
                    if room is not None and room > 0:
                        ceiling = price + sign * room * 0.9
                        if sign * (new_tp - ceiling) > 0:
                            new_tp = ceiling
                if sign * (new_tp - position.take_profit) > 0:
                    position.take_profit = round(new_tp, digits)
                    position.tp_extensions += 1
                    actions.append(TradeAction(
                        ActionType.MODIFY_TARGET, position.id, position.take_profit,
                        reason=(f"objectif repousse #{position.tp_extensions} "
                                f"(dynamique {momentum.score:+.2f} : "
                                f"{momentum.reasons[0] if momentum.reasons else 'favorable'})")))
                    locked = position.entry_price + sign * cfg.lock_r_on_extend * position.initial_risk
                    follow = price - sign * cfg.lock_back_atr * atr
                    candidate = follow if sign * (follow - locked) > 0 else locked
                    if sign * (candidate - new_stop) > 0:
                        new_stop = candidate
            else:
                protective = price - sign * cfg.trail_tighten_atr_mult * atr
                if sign * (protective - new_stop) > 0:
                    new_stop = protective
                    actions.append(TradeAction(
                        ActionType.MODIFY_STOP, position.id, round(new_stop, digits),
                        reason=(f"proche du TP mais dynamique faible ({momentum.score:+.2f}) : "
                                "stop resserre, objectif inchange")))

        new_stop = round(new_stop, digits)
        if sign * (new_stop - position.stop_loss) > 0:
            already = any(a.type is ActionType.MODIFY_STOP and a.price == new_stop for a in actions)
            if not already:
                actions.append(TradeAction(
                    ActionType.MODIFY_STOP, position.id, new_stop,
                    reason=f"stop suiveur a {position.locked_r():+.2f}R -> "
                           f"{(sign * (new_stop - position.entry_price) / position.initial_risk):+.2f}R verrouille"))
            position.stop_loss = new_stop
        return actions

    def _safety_exits(self, position: Position, price: float, r_now: float,
                      momentum: Momentum, now: float) -> Optional[TradeAction]:
        cfg = self.config
        if r_now >= cfg.reversal_exit_r and momentum.score <= -0.45:
            return TradeAction(
                ActionType.CLOSE, position.id,
                reason=(f"retournement confirme a {r_now:+.2f}R "
                        f"(dynamique {momentum.score:+.2f} : "
                        f"{momentum.reasons[0] if momentum.reasons else ''})"))
        age_min = (now - position.opened_at) / 60.0
        if age_min >= cfg.time_stop_minutes and r_now < cfg.time_stop_min_r:
            return TradeAction(
                ActionType.CLOSE, position.id,
                reason=f"stop temporel : {age_min:.0f} min sans progression ({r_now:+.2f}R)")
        if r_now <= -cfg.max_adverse_r * 1.5:
            return TradeAction(
                ActionType.CLOSE, position.id,
                reason=f"perte anormale {r_now:.2f}R : sortie de securite")
        return None
