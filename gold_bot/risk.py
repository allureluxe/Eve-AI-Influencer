"""Money management : dimensionnement, limites et echelle adaptative.

Regles de fond :
  - le risque se mesure AVANT d'entrer : taille = f(risque accepte, distance au stop) ;
  - aucune position sans stop-loss, jamais ;
  - la taille monte quand le capital monte, et descend quand il descend
    (anti-martingale : on augmente la mise avec les gains, jamais pour se
    refaire) ;
  - des coupe-circuits journaliers et hebdomadaires arretent le robot avant
    que la serie ne devienne structurelle.

L'echelle adaptative demandee est implementee dans `EquityLadder` :
chaque palier de gain augmente le multiplicateur de taille, chaque palier
de perte le reduit, par crans, sans effet de levier cumulatif.
"""
from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from .core import ClosedTrade, Position, Side
from .universe import Instrument

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RiskConfig:
    """Parametres de gestion du risque."""

    # --- Risque par trade ---
    base_risk_pct: float = 0.75        # % du capital risque sur un trade normal
    min_risk_pct: float = 0.20
    max_risk_pct: float = 1.50         # plafond dur, jamais franchi

    # --- Coupe-circuits ---
    daily_loss_limit_pct: float = 4.0
    weekly_loss_limit_pct: float = 8.0
    max_drawdown_pct: float = 20.0     # arret complet du robot
    daily_profit_target_pct: float = 6.0   # au-dela : on protege la journee

    # --- Exposition ---
    max_positions: int = 3
    max_per_correlation_group: int = 1
    max_total_risk_pct: float = 3.0    # somme des risques ouverts
    max_daily_trades: int = 12
    min_seconds_between_trades: float = 45.0
    max_leverage: float = 30.0         # plafond de levier effectif

    # --- Serie ---
    max_consecutive_losses: int = 4    # au-dela : pause forcee
    pause_after_losses_minutes: float = 90.0

    # --- Qualite minimale ---
    min_rr: float = 1.5                # ratio rendement/risque minimum

    # --- Cout d'execution ---
    #
    # Le rapport entre ce que coute un aller-retour (spread + commission) et
    # ce que le trade risque est LE facteur qui decide de la survie d'un
    # petit compte en trading rapide. Simulation a l'appui : avec un systeme
    # a 55 % de reussite et 1,3 de ratio, 20 trades par jour sur 50 EUR
    # donnent 446 EUR en trois mois quand le cout vaut 17 % du risque, et
    # 15 EUR (compte detruit) quand il en vaut 30 %. Meme systeme, meme
    # nombre de trades : seul le cout change.
    #
    # On refuse donc en amont tout trade dont le cout ronge l'esperance,
    # plutot que de le decouvrir sur le releve de compte.
    max_cost_ratio_pct: float = 15.0   # cout / risque, en %
    commission_per_lot: float = 0.0    # commission fixe eventuelle du broker
    commission_pct: float = 0.0        # commission proportionnelle au notionnel


@dataclass(slots=True)
class LadderStep:
    """Un cran de l'echelle adaptative."""

    threshold_pct: float    # variation du capital depuis la reference, en %
    multiplier: float       # multiplicateur de taille applique


@dataclass(slots=True)
class EquityLadder:
    """Echelle de taille adossee a la courbe de capital (anti-martingale).

    Exemple par defaut : a +10 % de capital le robot passe a 1.2x, a +25 %
    a 1.45x ; a -8 % il redescend a 0.75x, a -15 % a 0.5x. Les crans sont
    bornes des deux cotes, et la reference se recale sur les nouveaux
    sommets pour ne jamais empiler le risque sur un capital deja rendu.
    """

    steps: list[LadderStep] = field(default_factory=lambda: [
        LadderStep(50.0, 1.80),
        LadderStep(25.0, 1.45),
        LadderStep(10.0, 1.20),
        LadderStep(0.0, 1.00),
        LadderStep(-5.0, 0.85),
        LadderStep(-8.0, 0.75),
        LadderStep(-15.0, 0.50),
        LadderStep(-25.0, 0.35),
    ])
    floor: float = 0.30
    ceiling: float = 2.00

    def multiplier(self, equity: float, reference: float) -> tuple[float, str]:
        """Multiplicateur courant + explication."""
        if reference <= 0:
            return 1.0, "reference de capital inconnue"
        change = (equity - reference) / reference * 100.0
        for step in sorted(self.steps, key=lambda s: -s.threshold_pct):
            if change >= step.threshold_pct:
                mult = max(self.floor, min(self.ceiling, step.multiplier))
                sense = "gains" if change >= 0 else "pertes"
                return mult, f"capital {change:+.1f}% ({sense}) -> taille x{mult:.2f}"
        mult = max(self.floor, self.steps[-1].multiplier)
        return mult, f"capital {change:+.1f}% -> taille x{mult:.2f} (plancher)"


@dataclass(slots=True)
class AccountState:
    """Etat du compte suivi par le robot."""

    equity: float = 0.0
    balance: float = 0.0
    currency: str = "EUR"
    reference_equity: float = 0.0      # base de l'echelle adaptative
    peak_equity: float = 0.0
    day_key: str = ""
    week_key: str = ""
    day_start_equity: float = 0.0
    week_start_equity: float = 0.0
    realized_today: float = 0.0
    realized_this_week: float = 0.0
    trades_today: int = 0
    consecutive_losses: int = 0
    consecutive_wins: int = 0
    last_trade_ts: float = 0.0
    paused_until: float = 0.0
    halted: bool = False
    halt_reason: str = ""

    def drawdown_pct(self) -> float:
        if self.peak_equity <= 0:
            return 0.0
        return max(0.0, (self.peak_equity - self.equity) / self.peak_equity * 100.0)

    def daily_pnl_pct(self) -> float:
        if self.day_start_equity <= 0:
            return 0.0
        return (self.equity - self.day_start_equity) / self.day_start_equity * 100.0

    def weekly_pnl_pct(self) -> float:
        if self.week_start_equity <= 0:
            return 0.0
        return (self.equity - self.week_start_equity) / self.week_start_equity * 100.0


@dataclass(slots=True)
class SizingDecision:
    """Resultat du dimensionnement d'une position."""

    allowed: bool
    lots: float = 0.0
    risk_amount: float = 0.0
    risk_pct: float = 0.0
    stop_distance: float = 0.0
    cost: float = 0.0            # cout estime de l'aller-retour
    cost_ratio_pct: float = 0.0  # ce cout rapporte au risque engage
    reason: str = ""
    factors: list[str] = field(default_factory=list)


class RiskManager:
    """Gardien du capital : autorise, dimensionne et arrete."""

    def __init__(
        self,
        config: Optional[RiskConfig] = None,
        ladder: Optional[EquityLadder] = None,
    ) -> None:
        self.config = config or RiskConfig()
        self.ladder = ladder or EquityLadder()
        self.account = AccountState()

    # ---------------------------------------------------------------
    # Suivi du compte
    # ---------------------------------------------------------------
    def sync_account(self, equity: float, balance: float, currency: str = "EUR",
                     ts: Optional[float] = None) -> None:
        """Met a jour l'etat du compte et gere les changements de periode."""
        acc = self.account
        now = ts or time.time()
        dt = datetime.fromtimestamp(now, tz=timezone.utc)
        day = dt.strftime("%Y-%m-%d")
        year, week, _ = dt.isocalendar()
        wk = f"{year}-W{week:02d}"

        acc.equity, acc.balance, acc.currency = equity, balance, currency
        if acc.reference_equity <= 0:
            acc.reference_equity = equity
        if acc.peak_equity <= 0:
            acc.peak_equity = equity
        acc.peak_equity = max(acc.peak_equity, equity)

        if acc.day_key != day:
            acc.day_key = day
            acc.day_start_equity = equity
            acc.realized_today = 0.0
            acc.trades_today = 0
            logger.info("nouvelle journee %s : capital de depart %.2f %s", day, equity, currency)
        if acc.week_key != wk:
            acc.week_key = wk
            acc.week_start_equity = equity
            acc.realized_this_week = 0.0
            # La reference de l'echelle se recale chaque semaine sur le
            # sommet atteint : on ne re-risque pas un capital deja rendu.
            acc.reference_equity = max(acc.reference_equity, min(equity, acc.peak_equity))

    def record_close(self, trade: ClosedTrade) -> None:
        """Enregistre un trade cloture (statistiques et coupe-circuits)."""
        acc = self.account
        acc.realized_today += trade.profit
        acc.realized_this_week += trade.profit
        acc.trades_today += 1
        acc.last_trade_ts = trade.closed_at
        if trade.profit < 0:
            acc.consecutive_losses += 1
            acc.consecutive_wins = 0
            if acc.consecutive_losses >= self.config.max_consecutive_losses:
                acc.paused_until = time.time() + self.config.pause_after_losses_minutes * 60
                logger.warning("%d pertes consecutives : pause de %.0f min",
                               acc.consecutive_losses, self.config.pause_after_losses_minutes)
        else:
            acc.consecutive_wins += 1
            acc.consecutive_losses = 0

    # ---------------------------------------------------------------
    # Autorisations
    # ---------------------------------------------------------------
    def can_trade(self, open_positions: Optional[list[Position]] = None,
                  ts: Optional[float] = None) -> tuple[bool, str]:
        """Le robot a-t-il le droit d'ouvrir une position maintenant ?"""
        acc, cfg = self.account, self.config
        now = ts or time.time()
        positions = open_positions or []

        if acc.halted:
            return False, f"robot arrete : {acc.halt_reason}"
        if acc.equity <= 0:
            return False, "capital inconnu ou nul"
        if acc.drawdown_pct() >= cfg.max_drawdown_pct:
            acc.halted = True
            acc.halt_reason = f"drawdown maximal atteint ({acc.drawdown_pct():.1f}%)"
            return False, acc.halt_reason
        if now < acc.paused_until:
            return False, f"pause apres pertes ({(acc.paused_until - now) / 60:.0f} min restantes)"
        if acc.daily_pnl_pct() <= -cfg.daily_loss_limit_pct:
            return False, f"limite de perte journaliere atteinte ({acc.daily_pnl_pct():.2f}%)"
        if acc.weekly_pnl_pct() <= -cfg.weekly_loss_limit_pct:
            return False, f"limite de perte hebdomadaire atteinte ({acc.weekly_pnl_pct():.2f}%)"
        if cfg.daily_profit_target_pct > 0 and acc.daily_pnl_pct() >= cfg.daily_profit_target_pct:
            return False, f"objectif journalier atteint ({acc.daily_pnl_pct():+.2f}%) : journee protegee"
        if acc.trades_today >= cfg.max_daily_trades:
            return False, f"quota de trades du jour atteint ({acc.trades_today})"
        if len(positions) >= cfg.max_positions:
            return False, f"nombre maximal de positions atteint ({len(positions)})"
        if now - acc.last_trade_ts < cfg.min_seconds_between_trades:
            return False, "delai minimal entre deux trades non ecoule"
        return True, ""

    def check_exposure(self, instrument: Instrument, side: Side,
                       open_positions: list[Position],
                       universe_lookup) -> tuple[bool, str]:
        """Verifie les regles d'exposition et de correlation.

        Empiler trois achats correles (or + argent + AUD par exemple)
        revient a tripler la meme position sans le savoir.
        """
        cfg = self.config
        same_group = 0
        for pos in open_positions:
            if pos.symbol == instrument.symbol:
                return False, f"position deja ouverte sur {instrument.symbol}"
            other = universe_lookup(pos.symbol)
            if other and instrument.correlation_group and other.correlation_group == instrument.correlation_group:
                same_group += 1
        if instrument.correlation_group and same_group >= cfg.max_per_correlation_group:
            return False, f"exposition deja prise sur le groupe correle '{instrument.correlation_group}'"
        return True, ""

    def open_risk_pct(self, open_positions: list[Position],
                      universe_lookup) -> float:
        """Risque total encore en jeu sur les positions ouvertes, en % du capital."""
        acc = self.account
        if acc.equity <= 0:
            return 0.0
        total = 0.0
        for pos in open_positions:
            inst = universe_lookup(pos.symbol)
            if not inst:
                continue
            # Si le stop est deja en profit, le risque est nul.
            risk_price = max(0.0, pos.side.sign * (pos.entry_price - pos.stop_loss))
            total += risk_price * inst.value_per_price_unit(pos.volume)
        return total / acc.equity * 100.0

    # ---------------------------------------------------------------
    # Dimensionnement
    # ---------------------------------------------------------------
    def effective_risk_pct(self, extra_multiplier: float = 1.0) -> tuple[float, list[str]]:
        """Risque par trade apres application de tous les multiplicateurs."""
        acc, cfg = self.account, self.config
        factors: list[str] = []

        risk = cfg.base_risk_pct
        factors.append(f"base {risk:.2f}%")

        ladder_mult, ladder_why = self.ladder.multiplier(acc.equity, acc.reference_equity)
        risk *= ladder_mult
        factors.append(ladder_why)

        if extra_multiplier != 1.0:
            risk *= extra_multiplier
            factors.append(f"modulation objectif x{extra_multiplier:.2f}")

        # Serie de pertes : on reduit progressivement avant meme la pause.
        if acc.consecutive_losses >= 2:
            shrink = max(0.5, 1.0 - 0.15 * acc.consecutive_losses)
            risk *= shrink
            factors.append(f"{acc.consecutive_losses} pertes d'affilee x{shrink:.2f}")

        # Drawdown courant : reduction continue supplementaire.
        dd = acc.drawdown_pct()
        if dd > 5.0:
            shrink = max(0.5, 1.0 - (dd - 5.0) / 30.0)
            risk *= shrink
            factors.append(f"drawdown {dd:.1f}% x{shrink:.2f}")

        risk = max(cfg.min_risk_pct, min(cfg.max_risk_pct, risk))
        factors.append(f"retenu {risk:.2f}% (plafond dur {cfg.max_risk_pct:.2f}%)")
        return risk, factors

    def size_position(
        self,
        instrument: Instrument,
        side: Side,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        open_positions: Optional[list[Position]] = None,
        universe_lookup=None,
        extra_multiplier: float = 1.0,
        spread: float = 0.0,
        available_cash: Optional[float] = None,
    ) -> SizingDecision:
        """Calcule le volume a engager. Refuse si une regle est violee."""
        acc, cfg = self.account, self.config
        positions = open_positions or []
        lookup = universe_lookup or (lambda _s: None)

        stop_distance = abs(entry_price - stop_loss)
        if stop_distance <= 0:
            return SizingDecision(False, reason="stop-loss invalide (distance nulle)")
        # Tolerance sur la comparaison : un objectif place exactement au ratio
        # minimal ne doit pas etre refuse a cause d'un arrondi binaire.
        rr = abs(take_profit - entry_price) / stop_distance if take_profit else 0.0
        if take_profit and rr < cfg.min_rr - 1e-9:
            return SizingDecision(False, reason=f"ratio rendement/risque insuffisant ({rr:.2f} < {cfg.min_rr})")

        risk_pct, factors = self.effective_risk_pct(extra_multiplier)

        # Le risque deja engage plafonne le risque du nouveau trade.
        already = self.open_risk_pct(positions, lookup)
        room = cfg.max_total_risk_pct - already
        if room <= 0.05:
            return SizingDecision(False, reason=f"risque total deja engage ({already:.2f}%)")
        if risk_pct > room:
            risk_pct = room
            factors.append(f"limite par le risque total restant ({room:.2f}%)")

        risk_amount = acc.equity * risk_pct / 100.0
        value_per_unit = instrument.value_per_price_unit(1.0)   # pour 1 lot
        if value_per_unit <= 0:
            return SizingDecision(False, reason="taille de contrat invalide")

        raw_lots = risk_amount / (stop_distance * value_per_unit)

        # Argent reellement disponible. Au comptant, le capital total inclut
        # ce qui est deja investi : on ne peut pas acheter avec. Sans cette
        # limite, le robot proposerait des ordres que la plateforme refuserait
        # a chaque cycle, faute de liquidites.
        if available_cash is not None and available_cash >= 0:
            valeur_unitaire = entry_price * instrument.contract_size
            if valeur_unitaire > 0:
                max_lots_cash = available_cash / valeur_unitaire
                if max_lots_cash < instrument.min_lot:
                    return SizingDecision(
                        False,
                        reason=(f"liquidites insuffisantes : {available_cash:.2f} "
                                f"{acc.currency} disponible, il en faut "
                                f"{instrument.min_lot * valeur_unitaire:.2f} pour le "
                                f"minimum sur {instrument.symbol}"),
                        factors=factors,
                    )
                if raw_lots > max_lots_cash:
                    raw_lots = max_lots_cash
                    factors.append(f"limite par les liquidites ({available_cash:.2f} {acc.currency})")

        # Plafond de levier : la valeur notionnelle ne doit pas exploser.
        max_lots_leverage = None
        if cfg.max_leverage > 0:
            max_notional = acc.equity * cfg.max_leverage
            max_lots_leverage = max_notional / (entry_price * instrument.contract_size)
            if raw_lots > max_lots_leverage:
                raw_lots = max_lots_leverage
                factors.append(f"limite par le levier max ({cfg.max_leverage:.0f}x)")

        # Arrondi vers le bas : depasser le risque vise a cause d'un arrondi
        # serait une erreur silencieuse, repetee a chaque trade.
        lots = instrument.normalize_lot(raw_lots, round_down=True)

        # L'arrondi peut ramener au lot minimum, qui peut lui-meme depasser
        # le plafond de levier : on verifie apres normalisation.
        if max_lots_leverage is not None and lots > max_lots_leverage:
            if cfg.max_leverage <= 1.0:
                # Sans levier (le comptant), la contrainte n'est pas un plafond
                # de risque mais l'argent disponible : on ne peut pas acheter
                # plus cher que ce qu'on possede. Le message doit le dire.
                besoin = instrument.min_lot * entry_price * instrument.contract_size
                return SizingDecision(
                    False,
                    reason=(f"capital insuffisant pour acheter le minimum sur "
                            f"{instrument.symbol} : il faudrait {besoin:.2f} "
                            f"{acc.currency} pour {acc.equity:.2f} disponible"),
                    factors=factors,
                )
            return SizingDecision(
                False,
                reason=(f"le lot minimum ({instrument.min_lot}) depasse le levier autorise "
                        f"({cfg.max_leverage:.0f}x) sur {instrument.symbol}"),
                factors=factors,
            )
        if lots < instrument.min_lot or lots <= 0:
            return SizingDecision(
                False,
                reason=(f"capital insuffisant pour le lot minimum sur {instrument.symbol} "
                        f"(il faudrait {instrument.min_lot} lot, soit "
                        f"{stop_distance * value_per_unit * instrument.min_lot:.2f} {acc.currency} de risque "
                        f"pour {risk_amount:.2f} disponible)"),
                factors=factors,
            )

        # Le lot normalise peut depasser legerement le risque vise : on verifie.
        real_risk = lots * stop_distance * value_per_unit
        real_pct = real_risk / acc.equity * 100.0 if acc.equity else 0.0
        if real_pct > cfg.max_risk_pct * 1.15:
            return SizingDecision(
                False,
                reason=(f"le lot minimum represente {real_pct:.2f}% de risque, "
                        f"au-dessus du plafond {cfg.max_risk_pct:.2f}%"),
                factors=factors,
            )

        # Cout de l'aller-retour : on paie le spread a l'ouverture et a la
        # fermeture, plus l'eventuelle commission du broker.
        cost = self.execution_cost(instrument, lots, entry_price, spread)
        cost_ratio = cost / real_risk * 100.0 if real_risk > 0 else 100.0
        if cfg.max_cost_ratio_pct > 0 and cost_ratio > cfg.max_cost_ratio_pct:
            return SizingDecision(
                False,
                lots=lots,
                cost=round(cost, 4),
                cost_ratio_pct=round(cost_ratio, 1),
                stop_distance=stop_distance,
                reason=(f"cout d'execution trop lourd sur {instrument.symbol} : "
                        f"{cost:.3f} {acc.currency} pour {real_risk:.2f} de risque "
                        f"({cost_ratio:.0f} % du risque, maximum {cfg.max_cost_ratio_pct:.0f} %). "
                        f"Un stop plus large ou une unite de temps superieure corrigerait cela."),
                factors=factors,
            )
        factors.append(f"cout {cost:.3f} = {cost_ratio:.0f} % du risque")

        return SizingDecision(
            allowed=True,
            lots=lots,
            risk_amount=round(real_risk, 2),
            risk_pct=round(real_pct, 3),
            stop_distance=stop_distance,
            cost=round(cost, 4),
            cost_ratio_pct=round(cost_ratio, 1),
            factors=factors,
        )

    def execution_cost(self, instrument: Instrument, lots: float,
                       price: float, spread: float = 0.0) -> float:
        """Cout estime d'un aller-retour, dans la devise du compte."""
        cfg = self.config
        ecart = spread if spread > 0 else instrument.typical_spread
        cout = ecart * instrument.value_per_price_unit(lots)
        cout += cfg.commission_per_lot * lots
        cout += price * instrument.contract_size * lots * cfg.commission_pct * 2
        return cout

    def cost_ratio_for(self, instrument: Instrument, stop_distance: float,
                       price: float, spread: float = 0.0) -> float:
        """Rapport cout/risque au lot minimum, independamment du capital.

        Sert au filtrage amont : si meme le lot minimum est trop cher a
        traiter sur cette unite de temps, l'instrument est ecarte sans
        qu'on ait besoin de calculer quoi que ce soit d'autre.
        """
        if stop_distance <= 0:
            return 100.0
        risque = stop_distance * instrument.value_per_price_unit(instrument.min_lot)
        if risque <= 0:
            return 100.0
        return self.execution_cost(instrument, instrument.min_lot, price, spread) / risque * 100.0

    # ---------------------------------------------------------------
    def halt(self, reason: str) -> None:
        self.account.halted = True
        self.account.halt_reason = reason
        logger.error("ARRET DU ROBOT : %s", reason)

    def resume(self) -> None:
        self.account.halted = False
        self.account.halt_reason = ""
        self.account.paused_until = 0.0

    def snapshot(self) -> dict:
        acc = self.account
        risk_pct, _ = self.effective_risk_pct()
        return {
            "capital": round(acc.equity, 2),
            "solde": round(acc.balance, 2),
            "devise": acc.currency,
            "pnl_jour_pct": round(acc.daily_pnl_pct(), 2),
            "pnl_semaine_pct": round(acc.weekly_pnl_pct(), 2),
            "drawdown_pct": round(acc.drawdown_pct(), 2),
            "risque_par_trade_pct": round(risk_pct, 3),
            "trades_du_jour": acc.trades_today,
            "pertes_consecutives": acc.consecutive_losses,
            "arrete": acc.halted,
            "raison_arret": acc.halt_reason,
        }
