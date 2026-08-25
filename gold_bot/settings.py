"""Configuration du robot, Bitvavo uniquement."""
from __future__ import annotations
import json, logging, os
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from typing import Any
from .objectives import ObjectiveConfig
from .risk import RiskConfig
from .strategy import StrategyConfig
from .trade_manager import TradeManagerConfig
logger=logging.getLogger(__name__)
RACINE=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
@dataclass(slots=True)
class EngineConfig:
    broker:str="bitvavo"
    poll_seconds:float=5.0
    idle_poll_seconds:float=20.0
    closed_market_seconds:float=300.0
    max_consecutive_errors:int=12
    error_backoff_seconds:float=15.0
    heartbeat_minutes:float=60.0
    daily_report_hour:int=21
    symbols:list[str]=field(default_factory=list)
    start_balance:float=1000.0
    currency:str="EUR"
    dry_run:bool=False
    offline:bool=False
    verbose_scan:bool=False
    scan_workers:int=8
@dataclass(slots=True)
class BotConfig:
    engine:EngineConfig=field(default_factory=EngineConfig)
    strategy:StrategyConfig=field(default_factory=StrategyConfig)
    risk:RiskConfig=field(default_factory=RiskConfig)
    trade:TradeManagerConfig=field(default_factory=TradeManagerConfig)
    promotion:dict=field(default_factory=dict)
    objectives:ObjectiveConfig=field(default_factory=ObjectiveConfig)
    @classmethod
    def load(cls,path:str="")->"BotConfig":
        cfg=cls(); path=path or os.getenv("GB_CONFIG_FILE",os.path.join(RACINE,"robot.bitvavo.json"))
        if not os.path.isabs(path): path=os.path.join(RACINE,path)
        if os.path.exists(path):
            try:
                with open(path,encoding="utf-8") as f: cfg.apply(json.load(f))
            except (OSError,ValueError) as exc: logger.error("configuration illisible: %s",exc)
        cfg.apply_env(); return cfg
    def apply(self,data:dict[str,Any])->None:
        for name,values in (data or {}).items():
            if name.startswith("_"): continue
            if name=="promotion" and isinstance(values,dict): self.promotion=dict(values); continue
            section=getattr(self,name,None)
            if section is None or not is_dataclass(section) or not isinstance(values,dict): continue
            valid={f.name for f in fields(section)}
            for key,value in values.items():
                if key in valid: setattr(section,key,value)
    def apply_env(self)->None:
        for name in ("engine","strategy","risk","trade","objectives"):
            section=getattr(self,name)
            for f in fields(section):
                raw=os.getenv(f"GB_{name.upper()}_{f.name.upper()}")
                if raw is None: continue
                try:
                    cur=getattr(section,f.name)
                    if isinstance(cur,bool): value=raw.lower() in ("1","true","yes","oui")
                    elif isinstance(cur,int) and not isinstance(cur,bool): value=int(raw)
                    elif isinstance(cur,float): value=float(raw)
                    elif isinstance(cur,list): value=[x.strip() for x in raw.split(",") if x.strip()]
                    else: value=raw
                    setattr(section,f.name,value)
                except ValueError: logger.warning("valeur invalide: %s",f"GB_{name.upper()}_{f.name.upper()}")
    def to_dict(self)->dict[str,Any]:
        out={n:asdict(getattr(self,n)) for n in ("engine","strategy","risk","trade","objectives")}
        if self.promotion: out["promotion"]=dict(self.promotion)
        return out
    def save(self,path:str)->None:
        os.makedirs(os.path.dirname(path) or ".",exist_ok=True)
        with open(path,"w",encoding="utf-8") as f: json.dump(self.to_dict(),f,indent=2,ensure_ascii=False)
    def validate(self)->list[str]:
        p=[]; r,t,s,e=self.risk,self.trade,self.strategy,self.engine
        if e.broker!="bitvavo": p.append(f"broker interdit: {e.broker}; Bitvavo uniquement")
        if e.offline: p.append("mode offline interdit en execution Bitvavo")
        if r.max_risk_pct>3: p.append(f"risque maximal trop eleve: {r.max_risk_pct}%")
        if r.base_risk_pct>r.max_risk_pct: p.append("risque de base superieur au plafond")
        if r.min_risk_pct>r.base_risk_pct: p.append("risque minimal superieur au risque de base")
        if r.daily_loss_limit_pct>=r.weekly_loss_limit_pct: p.append("limite journaliere >= limite hebdomadaire")
        if r.max_total_risk_pct<r.max_risk_pct: p.append("risque total inferieur au risque d'un trade")
        if t.tp_r_multiple<r.min_rr: p.append("TP sous le ratio minimal")
        if t.breakeven_at_r>=t.tp_r_multiple: p.append("break-even apres TP")
        if t.extend_at_progress>=1: p.append("seuil extension invalide")
        if t.min_stop_atr>t.atr_stop_mult: p.append("stop minimal > stop nominal")
        if s.min_score>0.95: p.append("score minimal quasi inatteignable")
        if e.poll_seconds<1: p.append("poll trop agressif")
        return p
