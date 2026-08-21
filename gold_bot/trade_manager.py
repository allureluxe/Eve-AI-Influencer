"""Gestion dynamique des positions : SL, TP, trailing et extension d'objectif.

C'est le module qui repond a la demande centrale : quand le prix approche
du take-profit et que la dynamique reste favorable, le robot RECULE le TP
d'un cran ET REMONTE le stop dans la foulee. Le trade continue de courir,
mais avec un gain deja verrouille. Si la dynamique se degrade, il ne
touche pas au TP et resserre au contraire le stop pour encaisser.

Le mecanisme est strictement symetrique a l'achat et a la vente : sur une
vente, "monter le TP" veut dire le descendre plus bas, et "monter le stop"
veut dire le faire descendre — dans les deux cas on suit le prix.

Cycle de vie d'une position :

  0R ─────────► 0.8R : passage a break-even (stop a l'entree + frais)
  0.8R ────────► 1R  : prise partielle optionnelle
  1R ──────────► ... : trailing chandelier sur ATR
  85 % du TP ──► ... : extension du TP + verrouillage du stop  ◄── coeur
  dynamique KO ────► : resserrage du stop, sortie propre
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

# Marge du plancher de cout : on vise 90 % du plafond autorise pour que
# l'arrondi au tick de l'instrument ne fasse jamais franchir la limite.
COST_FLOOR_SAFETY = 0.90


class ActionType(str, Enum):
    MODIFY_STOP = "MODIFY_STOP"
    MODIFY_TARGET = "MODIFY_TARGET"
    PARTIAL_CLOSE = "PARTIAL_CLOSE"
    CLOSE = "CLOSE"


@dataclass(slots=True)
class TradeAction:
    """Ordre de gestion a transmettre au broker."""

    type: ActionType
    position_id: str
    price: Optional[float] = None      # nouveau SL ou TP
    volume: Optional[float] = None     # pour une fermeture partielle
    reason: str = ""

    def __str__(self) -> str:  # pragma: no cover
        target = f" -> {self.price}" if self.price is not None else ""
        return f"{self.type.value}{target} ({self.reason})"


@dataclass(slots=True)
class TradeManagerConfig:
    """Parametrage de la gestion de position."""

    # --- Stop et objectif initiaux ---
    atr_stop_mult: float = 1.6         # SL = entree -/+ 1.6 x ATR
    min_stop_atr: float = 0.8          # jamais plus serre que 0.8 ATR
    max_stop_atr: float = 3.0
    tp_r_multiple: float = 2.0         # TP initial = 2R
    spread_buffer_mult: float = 1.5    # marge de spread ajoutee au stop

    # --- Plancher de stop impose par le cout d'execution ---
    #
    # Le rapport cout/risque se simplifie exactement :
    #
    #     cout / risque = (spread x valeur) / (stop x valeur) = spread / stop
    #
    # Ni le capital ni le volume n'y entrent. Pour qu'un aller-retour coute
    # au plus X % de ce que le trade risque, il suffit donc que :
    #
    #     stop >= spread / X
    #
    # A 15 %, cela veut dire un stop d'au moins 6,67 fois le spread. C'est ce
    # qui rend le forex traitable en unite de temps courte : sur EURUSD le
    # stop passe de 2,4 a 2,7 ATR et le cout retombe sous le seuil, sans rien
    # changer d'autre. Quand le plancher exige un stop plus large que
    # `max_stop_atr_for_cost`, c'est que l'unite de temps est trop fine pour
    # cet instrument : mieux vaut monter d'un cran que d'elargir a l'absurde.
    max_cost_ratio_pct: float = 15.0
    max_stop_atr_for_cost: float = 4.0

    # --- Break-even ---
    breakeven_at_r: float = 0.8        # a 0.8R, le stop passe a l'entree
    breakeven_offset_r: float = 0.08   # petit gain verrouille (couvre les frais)

    # --- Prise partielle ---
    partial_enabled: bool = True
    partial_at_r: float = 1.0
    partial_fraction: float = 0.4      # part du volume fermee

    # --- Trailing chandelier ---
    trail_start_r: float = 1.0         # le trailing demarre a 1R
    trail_atr_mult: float = 1.8        # distance du stop suiveur
    trail_tighten_atr_mult: float = 1.0  # version resserree (dynamique faible)

    # --- Extension automatique de l'objectif ---
    extend_enabled: bool = True
    extend_at_progress: float = 0.85   # a 85 % du chemin vers le TP
    extend_by_atr: float = 1.2         # on recule le TP de 1.2 ATR
    extend_by_r_min: float = 0.5       # ... avec au moins 0.5R de plus
    max_extensions: int = 4            # pas d'extension infinie
    extend_min_momentum: float = 0.35  # dynamique minimale exigee
    lock_r_on_extend: float = 0.35     # gain minimal verrouille a chaque extension
    lock_back_atr: float = 1.1         # stop place a 1.1 ATR sous le prix

    # --- Sorties de securite ---
    time_stop_minutes: float = 240.0   # position qui stagne trop longtemps
    time_stop_min_r: float = 0.25      # ... et n'a pas atteint ce gain
    reversal_exit_r: float = 0.5       # au-dela de ce gain, un retournement fait sortir
    news_tighten_atr_mult: float = 0.9 # stop resserre avant une annonce
    max_adverse_r: float = 1.0         # securite : jamais au-dela de 1R de perte


@dataclass(slots=True)
class Momentum:
    """Mesure de la dynamique en faveur de la position."""

    score: float                       # -1 (contre) a +1 (pour)
    reasons: list[str] = field(default_factory=list)

    @property
    def favorable(self) -> bool:
        return self.score > 0


def compute_momentum(position: Position, ind: IndicatorSet,
                     chart: Optional[ChartRead] = None) -> Momentum:
    """Evalue si la dynamique soutient encore la position.

    C'est cette mesure qui decide si le TP est repousse ou non. On combine
    des lectures independantes pour eviter qu'un seul indicateur ne dicte
    une decision : tendance (Supertrend, EMA), impulsion (MACD, ADX),
    epuisement (RSI), price action (bougies) et structure.
    """
    bullish = position.side is Side.BUY
    sign = 1.0 if bullish else -1.0
    score, reasons = 0.0, []

    if not ind.ready or not ind.last:
        return Momentum(0.0, ["indicateurs incomplets"])

    price = ind.last.close

    # 1. Supertrend : filtre directionnel principal (poids 0.25)
    if ind.supertrend.ready:
        if (ind.supertrend.direction > 0) == bullish:
            score += 0.25
            reasons.append("supertrend dans le sens")
        else:
            score -= 0.30
            reasons.append("supertrend retourne contre la position")

    # 2. Position vs EMA rapide (poids 0.15)
    if ind.ema_fast.ready:
        if sign * (price - ind.ema_fast.value) > 0:
            score += 0.15
            reasons.append("prix du bon cote de l'EMA rapide")
        else:
            score -= 0.20
            reasons.append("prix repasse de l'autre cote de l'EMA rapide")

    # 3. Impulsion MACD (poids 0.15)
    if ind.macd.ready:
        if (ind.macd.rising and bullish) or (ind.macd.falling and not bullish):
            score += 0.15
            reasons.append("histogramme MACD en expansion")
        elif (ind.macd.falling and bullish) or (ind.macd.rising and not bullish):
            score -= 0.15
            reasons.append("histogramme MACD en contraction")

    # 4. Force de tendance ADX (poids 0.15)
    if ind.adx.ready and ind.adx.value is not None:
        if ind.adx.value >= 25:
            score += 0.15
            reasons.append(f"ADX {ind.adx.value:.0f} : tendance soutenue")
        elif ind.adx.value < 18:
            score -= 0.10
            reasons.append(f"ADX {ind.adx.value:.0f} : tendance molle")

    # 5. Epuisement RSI (poids 0.15) — un RSI extreme annonce une pause
    if ind.rsi.ready and ind.rsi.value is not None:
        r = ind.rsi.value
        if (bullish and r > 78) or (not bullish and r < 22):
            score -= 0.15
            reasons.append(f"RSI {r:.0f} en zone d'epuisement")
        elif 45 <= r <= 70 if bullish else 30 <= r <= 55:
            score += 0.10
            reasons.append(f"RSI {r:.0f} sain")

    # 6. Price action : un retournement contraire pese lourd (poids 0.25)
    hits = scan_candles(list(ind.candles)[-3:], ind.atr.value or 0.0)
    if hits:
        if opposing_reversal(hits, bullish):
            score -= 0.25
            reasons.append(f"bougie de retournement contraire ({hits[0].name})")
        else:
            net = sum(h.score for h in hits)
            if sign * net > 0.3:
                score += 0.12
                reasons.append("bougies dans le sens de la position")

    # 7. Obstacle graphique juste devant (poids 0.15)
    if chart is not None:
        room = chart.headroom(price, position.side)
        atr = ind.atr.value or 0.0
        if room is not None and atr > 0:
            if room < 0.5 * atr:
                score -= 0.15
                reasons.append("niveau majeur juste devant : peu de marge")
            elif room > 2.0 * atr:
                score += 0.10
                reasons.append("champ libre jusqu'au prochain niveau")

    # 8. Amortissement par le regime de marche.
    #
    # Un score de dynamique eleve n'a de sens que dans un marche qui tend.
    # En range (ADX faible) ou en regime de retour a la moyenne, prolonger
    # un objectif revient a parier que le prix va sortir d'un canal ou il
    # revient justement toujours : on ecrase le score pour interdire
    # l'extension, sans pour autant declencher de sortie.
    if score > 0:
        adx = ind.adx.value if ind.adx.ready else None
        if adx is not None and adx < 20:
            score *= 0.5
            reasons.append(f"ADX {adx:.0f} < 20 : marche sans tendance, dynamique amortie")
        if ind.hurst.regime == "mean_revert":
            score *= 0.6
            reasons.append("regime de retour a la moyenne : dynamique amortie")
        if ind.squeeze():
            score *= 0.7
            reasons.append("compression de volatilite : dynamique amortie")

    return Momentum(max(-1.0, min(1.0, score)), reasons)


class TradeManager:
    """Applique les regles de gestion a chaque position ouverte."""

    def __init__(self, config: Optional[TradeManagerConfig] = None) -> None:
        self.config = config or TradeManagerConfig()

    # ---------------------------------------------------------------
    # Construction des niveaux initiaux
    # ---------------------------------------------------------------
    def initial_levels(
        self,
        side: Side,
        entry_price: float,
        atr: float,
        spread: float = 0.0,
        structure_stop: Optional[float] = None,
        digits: int = 2,
    ) -> tuple[float, float]:
        """Calcule le SL et le TP d'ouverture.

        Le stop est place au-dela du dernier point de structure (swing) si
        celui-ci est coherent, sinon a un multiple d'ATR. On y ajoute une
        marge de spread : se faire sortir par l'elargissement du spread est
        l'erreur la plus courante sur l'or.
        """
        cfg = self.config
        sign = side.sign
        atr = max(atr, 1e-9)

        distance = cfg.atr_stop_mult * atr
        if structure_stop is not None:
            struct_distance = abs(entry_price - structure_stop)
            # On retient la structure si elle est dans une fourchette raisonnable.
            if cfg.min_stop_atr * atr <= struct_distance <= cfg.max_stop_atr * atr:
                distance = struct_distance
        distance = max(cfg.min_stop_atr * atr, min(cfg.max_stop_atr * atr, distance))
        distance += cfg.spread_buffer_mult * max(spread, 0.0)

        # Plancher de cout : un stop si serre que le spread en represente une
        # part enorme transforme un bon systeme en systeme perdant, quel que
        # soit le capital engage.
        #
        # On vise volontairement un peu SOUS le plafond (marge de securite) :
        # viser la limite exacte donnait un stop qui, une fois le prix arrondi
        # au tick de l'instrument, repassait de quelques millioniemes au-dessus
        # du seuil — et le trade etait refuse a chaque fois. Le forex etait
        # ainsi integralement bloque alors qu'il n'en manquait presque rien.
        if cfg.max_cost_ratio_pct > 0 and spread > 0:
            cible = cfg.max_cost_ratio_pct * COST_FLOOR_SAFETY / 100.0
            plancher = spread / cible
            if plancher > distance:
                distance = min(plancher, cfg.max_stop_atr_for_cost * atr)

        stop = entry_price - sign * distance
        target = entry_price + sign * distance * cfg.tp_r_multiple
        return round(stop, digits), round(target, digits)

    def cost_ratio(self, atr: float, spread: float, structure_stop_distance: float = 0.0) -> float:
        """Part du risque que represente le spread, pour cette volatilite.

        Sert au choix de l'unite de temps : on retient la plus fine ou ce
        rapport reste acceptable.
        """
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

    # ---------------------------------------------------------------
    # Gestion en cours de vie
    # ---------------------------------------------------------------
    def manage(
        self,
        position: Position,
        tick: Tick,
        ind: IndicatorSet,
        chart: Optional[ChartRead] = None,
        news: Optional[NewsWindow] = None,
        digits: int = 2,
        now: Optional[float] = None,
    ) -> list[TradeAction]:
        """Retourne les actions a appliquer sur la position.

        Ordre de priorite : securite d'abord (sorties), puis verrouillage
        du gain (stop), puis extension de l'objectif.
        """
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

        # ---------------- 1. Sorties de securite ----------------
        exit_action = self._safety_exits(position, price, r_now, momentum, now)
        if exit_action:
            return [exit_action]

        # ---------------- 2. Stop : break-even, trailing, news ----------------
        new_stop = position.stop_loss

        # 2a. Break-even
        if not position.breakeven_done and r_now >= cfg.breakeven_at_r:
            be = position.entry_price + sign * cfg.breakeven_offset_r * position.initial_risk
            if sign * (be - new_stop) > 0:
                new_stop = be
                position.breakeven_done = True
                actions.append(TradeAction(
                    ActionType.MODIFY_STOP, position.id, round(be, digits),
                    reason=f"break-even a {r_now:.2f}R : le trade ne peut plus perdre"))

        # 2b. Trailing chandelier a partir de trail_start_r
        if r_now >= cfg.trail_start_r:
            mult = cfg.trail_atr_mult
            if not momentum.favorable:
                mult = cfg.trail_tighten_atr_mult   # dynamique faible : on serre
            trail = position.max_favorable - sign * mult * atr
            if sign * (trail - new_stop) > 0:
                new_stop = trail

        # 2c. Resserrage avant une annonce economique
        if news is not None and news.tighten_stops and r_now > 0:
            protective = price - sign * cfg.news_tighten_atr_mult * atr
            if sign * (protective - new_stop) > 0:
                new_stop = protective
                actions.append(TradeAction(
                    ActionType.MODIFY_STOP, position.id, round(new_stop, digits),
                    reason=f"annonce imminente : stop resserre ({news.reason or 'calendrier'})"))

        # ---------------- 3. Prise partielle ----------------
        if (cfg.partial_enabled and not position.partial_done
                and r_now >= cfg.partial_at_r and position.volume > 0):
            volume = position.volume * cfg.partial_fraction
            if volume > 0:
                position.partial_done = True
                actions.append(TradeAction(
                    ActionType.PARTIAL_CLOSE, position.id, volume=round(volume, 8),
                    reason=f"prise partielle de {cfg.partial_fraction:.0%} a {r_now:.2f}R"))

        # ---------------- 4. Extension de l'objectif ----------------
        # C'est ici que le TP est repousse et le stop remonte simultanement.
        progress = position.progress_to_tp(price)
        if (cfg.extend_enabled
                and progress >= cfg.extend_at_progress
                and position.tp_extensions < cfg.max_extensions):

            if momentum.score >= cfg.extend_min_momentum:
                # 4a. On recule l'objectif d'un cran.
                step = max(cfg.extend_by_atr * atr, cfg.extend_by_r_min * position.initial_risk)
                new_tp = position.take_profit + sign * step

                # Un niveau majeur devant limite l'ambition : on s'arrete
                # juste avant plutot que de viser au travers.
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
                                f"(dynamique {momentum.score:+.2f} : {momentum.reasons[0] if momentum.reasons else 'favorable'})")))

                    # 4b. ET on remonte le stop dans le meme mouvement :
                    # l'extension ne doit jamais rendre le trade plus risque.
                    locked = position.entry_price + sign * cfg.lock_r_on_extend * position.initial_risk
                    follow = price - sign * cfg.lock_back_atr * atr
                    candidate = follow if sign * (follow - locked) > 0 else locked
                    if sign * (candidate - new_stop) > 0:
                        new_stop = candidate
            else:
                # Dynamique insuffisante : on ne touche pas au TP, on serre
                # le stop pour securiser ce qui est acquis.
                protective = price - sign * cfg.trail_tighten_atr_mult * atr
                if sign * (protective - new_stop) > 0:
                    new_stop = protective
                    actions.append(TradeAction(
                        ActionType.MODIFY_STOP, position.id, round(new_stop, digits),
                        reason=(f"proche du TP mais dynamique faible ({momentum.score:+.2f}) : "
                                f"stop resserre, objectif inchange")))

        # ---------------- 5. Emission du stop final ----------------
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

    # ---------------------------------------------------------------
    def _safety_exits(self, position: Position, price: float, r_now: float,
                      momentum: Momentum, now: float) -> Optional[TradeAction]:
        """Sorties prioritaires : retournement franc, stagnation, derive."""
        cfg = self.config

        # Retournement net alors qu'un gain correct est acquis : on encaisse.
        if r_now >= cfg.reversal_exit_r and momentum.score <= -0.45:
            return TradeAction(
                ActionType.CLOSE, position.id,
                reason=(f"retournement confirme a {r_now:+.2f}R "
                        f"(dynamique {momentum.score:+.2f} : {momentum.reasons[0] if momentum.reasons else ''})"))

        # Position qui n'avance pas : le capital immobilise coute.
        age_min = (now - position.opened_at) / 60.0
        if age_min >= cfg.time_stop_minutes and r_now < cfg.time_stop_min_r:
            return TradeAction(
                ActionType.CLOSE, position.id,
                reason=f"stop temporel : {age_min:.0f} min sans progression ({r_now:+.2f}R)")

        # Filet : perte anormalement profonde (gap, stop non honore).
        if r_now <= -cfg.max_adverse_r * 1.5:
            return TradeAction(
                ActionType.CLOSE, position.id,
                reason=f"perte anormale {r_now:.2f}R : sortie de securite")

        return None
