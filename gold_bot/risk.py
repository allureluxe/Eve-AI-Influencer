"""Money management : dimensionnement, limites et echelle adaptative."""
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
    base_risk_pct: float = 0.50
    min_risk_pct: float = 0.25
    max_risk_pct: float = 0.75
    daily_loss_limit_pct: float = 3.0
    weekly_loss_limit_pct: float = 7.0
    max_drawdown_pct: float = 35.0
    daily_profit_target_pct: float = 0.0
    max_positions: int = 9
    max_per_correlation_group: int = 2
    max_total_risk_pct: float = 4.5
    max_daily_trades: int = 0
    min_seconds_between_trades: float = 5.0
    max_capital_engaged_pct: float = 90.0
    max_leverage: float = 1.0
    max_consecutive_losses: int = 3
    pause_after_losses_minutes: float = 20.0
    min_rr: float = 1.20
    max_cost_ratio_pct: float = 15.0
    commission_per_lot: float = 0.0
    commission_pct: float = 0.0
    slippage_spread_ratio: float = 0.5

@dataclass(slots=True)
class LadderStep:
    threshold_pct: float
    multiplier: float

@dataclass(slots=True)
class EquityLadder:
    steps: list[LadderStep] = field(default_factory=lambda: [
        LadderStep(50.0, 1.80), LadderStep(25.0, 1.45), LadderStep(10.0, 1.20),
        LadderStep(0.0, 1.00), LadderStep(-5.0, 0.85), LadderStep(-8.0, 0.75),
        LadderStep(-15.0, 0.50), LadderStep(-25.0, 0.35)])
    floor: float = 0.30
    ceiling: float = 2.00
    def multiplier(self, equity: float, reference: float) -> tuple[float, str]:
        if reference <= 0: return 1.0, "reference de capital inconnue"
        change = (equity-reference)/reference*100.0
        for step in sorted(self.steps, key=lambda s: -s.threshold_pct):
            if change >= step.threshold_pct:
                m=max(self.floor,min(self.ceiling,step.multiplier))
                return m,f"capital {change:+.1f}% -> taille x{m:.2f}"
        return self.floor,f"capital {change:+.1f}% -> taille x{self.floor:.2f}"

@dataclass(slots=True)
class AccountState:
    equity: float = 0.0
    balance: float = 0.0
    currency: str = "EUR"
    reference_equity: float = 0.0
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
    def drawdown_pct(self):
        return max(0.0,(self.peak_equity-self.equity)/self.peak_equity*100.0) if self.peak_equity>0 else 0.0
    def daily_pnl_pct(self):
        return (self.equity-self.day_start_equity)/self.day_start_equity*100.0 if self.day_start_equity>0 else 0.0
    def weekly_pnl_pct(self):
        return (self.equity-self.week_start_equity)/self.week_start_equity*100.0 if self.week_start_equity>0 else 0.0

@dataclass(slots=True)
class SizingDecision:
    allowed: bool
    lots: float = 0.0
    risk_amount: float = 0.0
    risk_pct: float = 0.0
    stop_distance: float = 0.0
    cost: float = 0.0
    cost_ratio_pct: float = 0.0
    reason: str = ""
    factors: list[str] = field(default_factory=list)

class RiskManager:
    def __init__(self, config: Optional[RiskConfig]=None, ladder: Optional[EquityLadder]=None):
        self.config=config or RiskConfig(); self.ladder=ladder or EquityLadder(); self.account=AccountState()

    def sync_account(self,equity:float,balance:float,currency:str="EUR",ts:Optional[float]=None)->None:
        acc=self.account; now=ts or time.time(); dt=datetime.fromtimestamp(now,tz=timezone.utc)
        day=dt.strftime("%Y-%m-%d"); year,week,_=dt.isocalendar(); wk=f"{year}-W{week:02d}"
        acc.equity,acc.balance,acc.currency=equity,balance,currency
        if acc.reference_equity<=0: acc.reference_equity=equity
        if acc.peak_equity<=0: acc.peak_equity=equity
        acc.peak_equity=max(acc.peak_equity,equity)
        if acc.day_key!=day:
            acc.day_key=day; acc.day_start_equity=equity; acc.realized_today=0.0; acc.trades_today=0
        if acc.week_key!=wk:
            acc.week_key=wk; acc.week_start_equity=equity; acc.realized_this_week=0.0
            acc.reference_equity=max(acc.reference_equity,min(equity,acc.peak_equity))

    def record_close(self,trade:ClosedTrade)->None:
        acc=self.account; acc.realized_today+=trade.profit; acc.realized_this_week+=trade.profit; acc.trades_today+=1; acc.last_trade_ts=trade.closed_at
        if trade.profit<0:
            acc.consecutive_losses+=1; acc.consecutive_wins=0
            if acc.consecutive_losses>=self.config.max_consecutive_losses:
                acc.paused_until=time.time()+self.config.pause_after_losses_minutes*60
        else: acc.consecutive_wins+=1; acc.consecutive_losses=0

    def can_trade(self,open_positions:Optional[list[Position]]=None,ts:Optional[float]=None)->tuple[bool,str]:
        acc,cfg=self.account,self.config; now=ts or time.time(); positions=open_positions or []
        if acc.halted: return False,f"robot arrete : {acc.halt_reason}"
        if acc.equity<=0: return False,"capital inconnu ou nul"
        if acc.drawdown_pct()>=cfg.max_drawdown_pct:
            acc.halted=True; acc.halt_reason=f"drawdown maximal atteint ({acc.drawdown_pct():.1f}%)"; return False,acc.halt_reason
        if now<acc.paused_until: return False,f"pause apres pertes ({(acc.paused_until-now)/60:.0f} min restantes)"
        if acc.paused_until and acc.consecutive_losses>=cfg.max_consecutive_losses: acc.consecutive_losses=0; acc.paused_until=0.0
        if acc.daily_pnl_pct()<=-cfg.daily_loss_limit_pct: return False,f"limite de perte journaliere atteinte ({acc.daily_pnl_pct():.2f}%)"
        if acc.weekly_pnl_pct()<=-cfg.weekly_loss_limit_pct: return False,f"limite de perte hebdomadaire atteinte ({acc.weekly_pnl_pct():.2f}%)"
        if cfg.daily_profit_target_pct>0 and acc.daily_pnl_pct()>=cfg.daily_profit_target_pct: return False,f"objectif journalier atteint ({acc.daily_pnl_pct():+.2f}%)"
        if cfg.max_daily_trades>0 and acc.trades_today>=cfg.max_daily_trades: return False,f"quota de trades du jour atteint ({acc.trades_today})"
        if len(positions)>=cfg.max_positions: return False,f"nombre maximal de positions atteint ({len(positions)})"
        if now-acc.last_trade_ts<cfg.min_seconds_between_trades: return False,"delai minimal entre deux trades non ecoule"
        return True,""

    def check_exposure(self,instrument:Instrument,side:Side,open_positions:list[Position],universe_lookup)->tuple[bool,str]:
        same=0
        for pos in open_positions:
            if pos.symbol==instrument.symbol: return False,f"position deja ouverte sur {instrument.symbol}"
            other=universe_lookup(pos.symbol)
            if other and instrument.correlation_group and other.correlation_group==instrument.correlation_group: same+=1
        if instrument.correlation_group and same>=self.config.max_per_correlation_group: return False,f"exposition deja prise sur le groupe correle '{instrument.correlation_group}'"
        return True,""

    def open_risk_pct(self,open_positions:list[Position],universe_lookup)->float:
        if self.account.equity<=0:return 0.0
        total=0.0
        for pos in open_positions:
            inst=universe_lookup(pos.symbol)
            if not inst: continue
            risk_price=max(0.0,pos.side.sign*(pos.entry_price-pos.stop_loss))
            total+=risk_price*inst.value_per_price_unit(pos.volume)
        return total/self.account.equity*100.0

    def effective_risk_pct(self,extra_multiplier:float=1.0)->tuple[float,list[str]]:
        acc,cfg=self.account,self.config; factors=[]; risk=cfg.base_risk_pct
        factors.append(f"base {risk:.2f}%")
        mult,why=self.ladder.multiplier(acc.equity,acc.reference_equity); risk*=mult; factors.append(why)
        if extra_multiplier!=1: risk*=extra_multiplier; factors.append(f"modulation objectif x{extra_multiplier:.2f}")
        if acc.consecutive_losses>=2: risk*=max(0.5,1-0.15*acc.consecutive_losses)
        dd=acc.drawdown_pct()
        if dd>5: risk*=max(0.5,1-(dd-5)/30)
        risk=max(cfg.min_risk_pct,min(cfg.max_risk_pct,risk)); return risk,factors

    def size_position(self,instrument:Instrument,side:Side,entry_price:float,stop_loss:float,take_profit:float,open_positions:Optional[list[Position]]=None,universe_lookup=None,extra_multiplier:float=1.0,spread:float=0.0,available_cash:Optional[float]=None)->SizingDecision:
        acc,cfg=self.account,self.config; positions=open_positions or []; lookup=universe_lookup or (lambda _s:None)
        dist=abs(entry_price-stop_loss)
        if dist<=0:return SizingDecision(False,reason="stop-loss invalide")
        rr=abs(take_profit-entry_price)/dist if take_profit else 0
        if take_profit and rr<cfg.min_rr-1e-9:return SizingDecision(False,reason=f"ratio rendement/risque insuffisant ({rr:.2f} < {cfg.min_rr})")
        risk_pct,factors=self.effective_risk_pct(extra_multiplier)
        room=cfg.max_total_risk_pct-self.open_risk_pct(positions,lookup)
        if room<=0.05:return SizingDecision(False,reason=f"risque total deja engage ({cfg.max_total_risk_pct-room:.2f}%)",factors=factors)
        risk_pct=min(risk_pct,room); risk_amount=acc.equity*risk_pct/100
        vpu=instrument.value_per_price_unit(1.0)
        if vpu<=0:return SizingDecision(False,reason="taille de contrat invalide")
        raw=risk_amount/(dist*vpu)

        # Budget d'exposition dynamique : repartit le cash restant entre les places
        # encore disponibles. Cela empeche un seul ordre de consommer les 45 EUR
        # restants et laisse au moteur la possibilite de remplir plusieurs places.
        if available_cash is not None and available_cash>=0:
            slots=max(1,cfg.max_positions-len(positions))
            engagement_cap=acc.equity*cfg.max_capital_engaged_pct/100.0
            engaged=0.0
            for pos in positions:
                inst=lookup(pos.symbol)
                if inst: engaged+=abs(pos.entry_price*inst.contract_size*pos.volume)
            remaining_budget=max(0.0,engagement_cap-engaged)
            per_slot=min(available_cash,remaining_budget)/slots if slots>1 else min(available_cash,remaining_budget)
            unit_notional=entry_price*instrument.contract_size
            if unit_notional<=0:return SizingDecision(False,reason="notionnel unitaire invalide")
            max_cash_lots=per_slot/unit_notional
            if max_cash_lots<instrument.min_lot:
                # Ne pas mettre l'instrument en sommeil : le cash peut etre
                # libere par une cloture au prochain cycle.
                return SizingDecision(False,reason=f"budget de place insuffisant : {per_slot:.2f} {acc.currency} pour {instrument.symbol}",factors=factors)
            if raw>max_cash_lots: raw=max_cash_lots; factors.append(f"allocation par place : {per_slot:.2f} {acc.currency} ({slots} places restantes)")

        max_lots_leverage=None
        if cfg.max_leverage>0:
            max_lots_leverage=acc.equity*cfg.max_leverage/(entry_price*instrument.contract_size)
            raw=min(raw,max_lots_leverage)
        lots=instrument.normalize_lot(raw,round_down=True)
        if max_lots_leverage is not None and lots>max_lots_leverage:return SizingDecision(False,reason=f"lot minimum depasse le levier autorise ({cfg.max_leverage:.0f}x)",factors=factors)
        if lots<instrument.min_lot or lots<=0:return SizingDecision(False,reason=f"capital insuffisant pour le lot minimum sur {instrument.symbol}",factors=factors)
        real_risk=lots*dist*vpu; real_pct=real_risk/acc.equity*100 if acc.equity else 0
        if real_pct>cfg.max_risk_pct*1.15:return SizingDecision(False,reason=f"risque normalise trop eleve ({real_pct:.2f}%)",factors=factors)
        cost=self.execution_cost(instrument,lots,entry_price,spread); ratio=cost/real_risk*100 if real_risk>0 else 100
        if cfg.max_cost_ratio_pct>0 and ratio>cfg.max_cost_ratio_pct:return SizingDecision(False,lots=lots,cost=round(cost,4),cost_ratio_pct=round(ratio,1),stop_distance=dist,reason=f"cout d'execution trop lourd sur {instrument.symbol} : {ratio:.0f}% du risque",factors=factors)
        factors.append(f"cout {cost:.3f} = {ratio:.0f}% du risque")
        return SizingDecision(True,lots=lots,risk_amount=round(real_risk,2),risk_pct=round(real_pct,3),stop_distance=dist,cost=round(cost,4),cost_ratio_pct=round(ratio,1),factors=factors)

    def execution_cost(self,instrument:Instrument,lots:float,price:float,spread:float=0.0)->float:
        ecart=spread if spread>0 else instrument.typical_spread; value=instrument.value_per_price_unit(lots)
        return ecart*value+self.config.commission_per_lot*lots+price*instrument.contract_size*lots*self.config.commission_pct*2+ecart*value*max(0,self.config.slippage_spread_ratio)*2

    def cost_ratio_for(self,instrument:Instrument,stop_distance:float,price:float,spread:float=0.0)->float:
        if stop_distance<=0:return 100.0
        risk=stop_distance*instrument.value_per_price_unit(instrument.min_lot)
        return self.execution_cost(instrument,instrument.min_lot,price,spread)/risk*100 if risk>0 else 100.0

    def halt(self,reason:str)->None:
        self.account.halted=True; self.account.halt_reason=reason; logger.error("ARRET DU ROBOT : %s",reason)
    def resume(self)->None:
        self.account.halted=False; self.account.halt_reason=""; self.account.paused_until=0.0
    def snapshot(self)->dict:
        risk,_=self.effective_risk_pct(); acc=self.account
        return {"capital":round(acc.equity,2),"solde":round(acc.balance,2),"devise":acc.currency,"pnl_jour_pct":round(acc.daily_pnl_pct(),2),"pnl_semaine_pct":round(acc.weekly_pnl_pct(),2),"drawdown_pct":round(acc.drawdown_pct(),2),"risque_par_trade_pct":round(risk,3),"trades_du_jour":acc.trades_today,"pertes_consecutives":acc.consecutive_losses,"arrete":acc.halted,"raison_arret":acc.halt_reason}
