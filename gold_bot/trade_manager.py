"""Gestion dynamique des positions : SL, TP, trailing et extension d'objectif.

Le gestionnaire protege le capital, encaisse les petits gains quand la
dynamique baisse et laisse courir les gagnants quand le mouvement reste fort.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

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
    def __str__(self) -> str:
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
    micro_profit_enabled: bool = True
    micro_profit_at_r: float = 0.90
    micro_profit_min_momentum: float = 0.20
    time_stop_minutes: float = 240.0
    time_stop_min_r: float = 0.25
    reversal_exit_r: float = 0.5
    news_tighten_atr_mult: float = 0.9
    max_adverse_r: float = 1.0

    # --- Stop COMMUN a une pyramide ---
    #
    # LE DEFAUT QUI FAIT PERDRE LE PYRAMIDAGE, ET IL EST A L'ENVERS.
    #
    # Chaque etage suit son PROPRE plus-haut, avec la meme distance ATR.
    # L'etage 2 etant entre plus haut, son stop se retrouve AU-DESSUS de
    # celui de l'etage 1 : au moindre repli c'est lui qui saute — celui
    # qu'on venait d'ajouter parce que ca montait — pendant que la base
    # survit. Il paie l'aller-retour complet (~50 % de son risque en frais
    # au M30) pour un mouvement de bruit. On perd le renfort et on garde
    # la position d'origine : exactement l'inverse de ce qu'on veut.
    #
    # Arme, tous les etages partagent le meme niveau de sortie — le plus
    # LACHE de la pyramide — et sortent donc ENSEMBLE quand la tendance
    # casse vraiment, pas un par un par le haut.
    #
    # La garde qui rend ca tenable : ce niveau partage ne descend jamais
    # sous le point mort COLLECTIF de la pyramide. Un etage haut peut donc
    # rendre plus que son propre R, mais l'ensemble ne peut pas passer
    # perdant. C'est la meme promesse qu'avant, deplacee de l'etage vers
    # la pyramide — la seule echelle a laquelle elle ait un sens.
    pyramide_stop_commun: bool = False

@dataclass(slots=True)
class Momentum:
    score: float
    reasons: list[str] = field(default_factory=list)
    @property
    def favorable(self) -> bool:
        return self.score > 0

def compute_momentum(position: Position, ind: IndicatorSet, chart: Optional[ChartRead] = None) -> Momentum:
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
            score -= 0.20; reasons.append("prix repasse de l'autre cote de l'EMA rapide")
    if ind.macd.ready:
        if (ind.macd.rising and bullish) or (ind.macd.falling and not bullish):
            score += 0.15; reasons.append("histogramme MACD en expansion")
        elif (ind.macd.falling and bullish) or (ind.macd.rising and not bullish):
            score -= 0.15; reasons.append("histogramme MACD en contraction")
    if ind.adx.ready and ind.adx.value is not None:
        if ind.adx.value >= 25:
            score += 0.15; reasons.append(f"ADX {ind.adx.value:.0f} : tendance soutenue")
        elif ind.adx.value < 18:
            score -= 0.10; reasons.append(f"ADX {ind.adx.value:.0f} : tendance molle")
    if ind.rsi.ready and ind.rsi.value is not None:
        r = ind.rsi.value
        if (bullish and r > 78) or (not bullish and r < 22):
            score -= 0.15; reasons.append(f"RSI {r:.0f} en zone d'epuisement")
        elif 45 <= r <= 70 if bullish else 30 <= r <= 55:
            score += 0.10; reasons.append(f"RSI {r:.0f} sain")
    hits = scan_candles(list(ind.candles)[-3:], ind.atr.value or 0.0)
    if hits:
        if opposing_reversal(hits, bullish):
            score -= 0.25; reasons.append(f"bougie de retournement contraire ({hits[0].name})")
        else:
            net = sum(h.score for h in hits)
            if sign * net > 0.3:
                score += 0.12; reasons.append("bougies dans le sens de la position")
    if chart is not None:
        room = chart.headroom(price, position.side)
        atr = ind.atr.value or 0.0
        if room is not None and atr > 0:
            if room < 0.5 * atr:
                score -= 0.15; reasons.append("niveau majeur juste devant : peu de marge")
            elif room > 2.0 * atr:
                score += 0.10; reasons.append("champ libre jusqu'au prochain niveau")
    if score > 0:
        adx = ind.adx.value if ind.adx.ready else None
        if adx is not None and adx < 20:
            score *= 0.5; reasons.append(f"ADX {adx:.0f} < 20 : marche sans tendance, dynamique amortie")
        if ind.hurst.regime == "mean_revert":
            score *= 0.6; reasons.append("regime de retour a la moyenne : dynamique amortie")
        if ind.squeeze():
            score *= 0.7; reasons.append("compression de volatilite : dynamique amortie")
    return Momentum(max(-1.0, min(1.0, score)), reasons)

class TradeManager:
    def __init__(self, config: Optional[TradeManagerConfig] = None) -> None:
        self.config = config or TradeManagerConfig()

    def initial_levels(self, side: Side, entry_price: float, atr: float, spread: float = 0.0,
                       structure_stop: Optional[float] = None, digits: int = 2) -> tuple[float, float]:
        cfg = self.config
        sign = side.sign
        atr = max(atr, 1e-9)
        distance = cfg.atr_stop_mult * atr
        if structure_stop is not None:
            struct_distance = abs(entry_price - structure_stop)
            if cfg.min_stop_atr * atr <= struct_distance <= cfg.max_stop_atr * atr:
                distance = struct_distance
        distance = max(cfg.min_stop_atr * atr, min(cfg.max_stop_atr * atr, distance))
        distance += cfg.spread_buffer_mult * max(spread, 0.0)
        if cfg.max_cost_ratio_pct > 0 and spread > 0:
            cible = cfg.max_cost_ratio_pct * COST_FLOOR_SAFETY / 100.0
            plancher = spread / cible
            if plancher > distance:
                distance = min(plancher, cfg.max_stop_atr_for_cost * atr)
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

    @staticmethod
    def point_mort_collectif(etages: list[Position]) -> Optional[float]:
        """Prix auquel la pyramide entiere sort a zero, frais exclus.

        Somme des volumes ponderee par les entrees : le niveau ou les gains
        des etages bas compensent exactement les pertes des etages hauts.
        Sous ce prix la pyramide est collectivement perdante.
        """
        volume = sum(p.volume for p in etages)
        if volume <= 0:
            return None
        return sum(p.entry_price * p.volume for p in etages) / volume

    def stop_partage(self, position: Position,
                     etages: list[Position]) -> Optional[float]:
        """Niveau de sortie commun a tous les etages d'une pyramide.

        Le plus LACHE des stops en place (le plus bas a l'achat), borne par
        le point mort collectif : les etages sortent ensemble sur une vraie
        cassure, jamais dans le rouge pour l'ensemble.
        """
        famille = [p for p in etages if p.symbol == position.symbol
                   and p.side is position.side]
        if len(famille) < 2:
            return None
        sign = position.side.sign
        # Le plus lache = le moins avance dans le sens du trade.
        partage = min((p.stop_loss for p in famille), key=lambda s: sign * s)
        mort = self.point_mort_collectif(famille)
        if mort is not None and sign * (mort - partage) > 0:
            partage = mort          # jamais sous le point mort collectif
        return partage

    def manage(self, position: Position, tick: Tick, ind: IndicatorSet,
               chart: Optional[ChartRead] = None, news: Optional[NewsWindow] = None,
               digits: int = 2, now: Optional[float] = None,
               etages: Optional[list[Position]] = None) -> list[TradeAction]:
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
        micro_profit = (
            cfg.micro_profit_enabled
            and r_now >= cfg.micro_profit_at_r
            and momentum.score < cfg.micro_profit_min_momentum
        )
        new_stop = position.stop_loss
        if not position.breakeven_done and r_now >= cfg.breakeven_at_r:
            be = position.entry_price + sign * cfg.breakeven_offset_r * position.initial_risk
            if sign * (be - new_stop) > 0:
                new_stop = be; position.breakeven_done = True
                actions.append(TradeAction(ActionType.MODIFY_STOP, position.id, round(be, digits),
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
                actions.append(TradeAction(ActionType.MODIFY_STOP, position.id, round(new_stop, digits),
                    reason=f"annonce imminente : stop resserre ({news.reason or 'calendrier'})"))
        if (cfg.partial_enabled and not position.partial_done
                and r_now >= cfg.partial_at_r and position.volume > 0):
            volume = position.volume * cfg.partial_fraction
            if volume > 0:
                position.partial_done = True
                actions.append(TradeAction(ActionType.PARTIAL_CLOSE, position.id, volume=round(volume, 8),
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
                    actions.append(TradeAction(ActionType.MODIFY_TARGET, position.id, position.take_profit,
                        reason=(f"objectif repousse #{position.tp_extensions} (dynamique {momentum.score:+.2f} : "
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
                    actions.append(TradeAction(ActionType.MODIFY_STOP, position.id, round(new_stop, digits),
                        reason=(f"proche du TP mais dynamique faible ({momentum.score:+.2f}) : "
                                "stop resserre, objectif inchange")))
        # Stop COMMUN : on empeche cet etage de se resserrer AU-DELA du
        # niveau partage. Sans ce plafond, l'etage haut court devant les
        # autres et se fait sortir seul au premier repli (voir le
        # commentaire de `pyramide_stop_commun`). On ne desserre jamais un
        # stop deja pose — le cliquet plus bas s'en charge — on evite
        # seulement de le serrer trop tot.
        if cfg.pyramide_stop_commun and etages:
            partage = self.stop_partage(position, etages)
            if partage is not None and sign * (new_stop - partage) > 0:
                new_stop = partage

        new_stop = round(new_stop, digits)
        if sign * (new_stop - position.stop_loss) > 0:
            already = any(a.type is ActionType.MODIFY_STOP and a.price == new_stop for a in actions)
            if not already:
                actions.append(TradeAction(ActionType.MODIFY_STOP, position.id, new_stop,
                    reason=f"stop suiveur a {position.locked_r():+.2f}R -> "
                           f"{(sign * (new_stop - position.entry_price) / position.initial_risk):+.2f}R verrouille"))
            position.stop_loss = new_stop

        if micro_profit:
            actions.append(
                TradeAction(
                    ActionType.CLOSE,
                    position.id,
                    reason=(
                        f"micro-profit {r_now:+.2f}R : dynamique faible "
                        f"({momentum.score:+.2f}), gain encaisse"
                    ),
                )
            )

        return actions

    def _safety_exits(self, position: Position, price: float, r_now: float,
                      momentum: Momentum, now: float) -> Optional[TradeAction]:
        cfg = self.config
        if r_now >= cfg.reversal_exit_r and momentum.score <= -0.45:
            return TradeAction(ActionType.CLOSE, position.id,
                reason=(f"retournement confirme a {r_now:+.2f}R (dynamique {momentum.score:+.2f} : "
                        f"{momentum.reasons[0] if momentum.reasons else ''})"))
        age_min = (now - position.opened_at) / 60.0
        if age_min >= cfg.time_stop_minutes and r_now < cfg.time_stop_min_r:
            return TradeAction(ActionType.CLOSE, position.id,
                reason=f"stop temporel : {age_min:.0f} min sans progression ({r_now:+.2f}R)")
        if r_now <= -cfg.max_adverse_r * 1.5:
            return TradeAction(ActionType.CLOSE, position.id,
                reason=f"perte anormale {r_now:.2f}R : sortie de securite")
        return None
