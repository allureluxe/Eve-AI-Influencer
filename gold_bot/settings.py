"""Configuration globale du robot.

Les secrets restent uniquement dans l'environnement.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from typing import Any

from .objectives import ObjectiveConfig
from .risk import RiskConfig
from .strategy import StrategyConfig
from .trade_manager import TradeManagerConfig

logger = logging.getLogger(__name__)
RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

@dataclass(slots=True)
class EngineConfig:
    broker: str = "multi"
    poll_seconds: float = 5.0
    idle_poll_seconds: float = 20.0
    closed_market_seconds: float = 300.0
    max_consecutive_errors: int = 12
    error_backoff_seconds: float = 15.0
    heartbeat_minutes: float = 60.0
    daily_report_hour: int = 21
    symbols: list[str] = field(default_factory=list)
    start_balance: float = 1000.0
    currency: str = "EUR"
    dry_run: bool = True
    offline: bool = False
    verbose_scan: bool = False
    scan_workers: int = 8
    scan_max_instruments: int = 8

@dataclass(slots=True)
class BotConfig:
    engine: EngineConfig = field(default_factory=EngineConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    trade: TradeManagerConfig = field(default_factory=TradeManagerConfig)
    promotion: dict = field(default_factory=dict)
    objectives: ObjectiveConfig = field(default_factory=ObjectiveConfig)

    @classmethod
    def load(cls, path: str = "") -> "BotConfig":
        cfg = cls()
        path = path or os.getenv("GB_CONFIG_FILE") or os.getenv("GB_CONFIG", "")
        if path and not os.path.isabs(path): path = os.path.join(RACINE, path)
        if path and os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as fh: cfg.apply(json.load(fh))
                logger.info("configuration chargee depuis %s", path)
            except (OSError, ValueError) as exc: logger.error("configuration illisible (%s): %s", path, exc)
        elif path: logger.error("configuration introuvable : %s", path)
        cfg.apply_env()
        return cfg

    def apply(self, data: dict[str, Any]) -> None:
        for section_name, values in (data or {}).items():
            if section_name.startswith("_"): continue
            if section_name == "promotion" and isinstance(values, dict): self.promotion = dict(values); continue
            section = getattr(self, section_name, None)
            if section is None or not is_dataclass(section) or not isinstance(values, dict): continue
            valid = {f.name for f in fields(section)}
            for key, value in values.items():
                if key in valid: setattr(section, key, value)
                else: logger.warning("parametre inconnu ignore : %s.%s", section_name, key)

    def apply_env(self) -> None:
        for section_name in ("engine", "strategy", "risk", "trade", "objectives"):
            section = getattr(self, section_name)
            for f in fields(section):
                raw = os.getenv(f"GB_{section_name.upper()}_{f.name.upper()}")
                if raw is None: continue
                try:
                    current = getattr(section, f.name)
                    if isinstance(current, bool): value: Any = raw.strip().lower() in ("1", "true", "yes", "oui")
                    elif isinstance(current, int) and not isinstance(current, bool): value = int(raw)
                    elif isinstance(current, float): value = float(raw)
                    elif isinstance(current, list): value = [x.strip() for x in raw.split(",") if x.strip()]
                    else: value = raw
                    setattr(section, f.name, value)
                except ValueError: logger.warning("valeur invalide pour %s.%s: %r", section_name, f.name, raw)

    def to_dict(self) -> dict[str, Any]:
        sortie = {name: asdict(getattr(self, name)) for name in ("engine", "strategy", "risk", "trade", "objectives")}
        if self.promotion: sortie["promotion"] = dict(self.promotion)
        return sortie

    def save(self, path: str) -> None:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh: json.dump(self.to_dict(), fh, indent=2, ensure_ascii=False)

    def validate(self) -> list[str]:
        problems: list[str] = []
        r, t, s, e = self.risk, self.trade, self.strategy, self.engine
        brokers_valides = {"paper", "bitvavo", "pionex", "coinbase", "bitstamp", "multi", "ibkr"}
        if e.broker not in brokers_valides: problems.append(f"broker invalide : {e.broker}")
        if e.offline and e.broker != "paper":
            problems.append(f"mode hors ligne incompatible avec une execution reelle ({e.broker})")
        if e.scan_max_instruments < 1: problems.append("scan_max_instruments doit etre >= 1")
        if e.scan_max_instruments > 50: problems.append("scan_max_instruments trop eleve pour le quota API")
        if r.max_risk_pct > 1.5: problems.append(f"risque maximal au-dessus du plafond de securite ({r.max_risk_pct}% > 1.5%)")
        if r.base_risk_pct > r.max_risk_pct: problems.append("risque de base superieur au plafond")
        if r.min_risk_pct > r.base_risk_pct: problems.append("risque minimal superieur au risque de base")
        if r.daily_loss_limit_pct >= r.weekly_loss_limit_pct: problems.append("la limite journaliere doit etre inferieure a la limite hebdomadaire")
        if r.max_total_risk_pct < r.max_risk_pct: problems.append("le risque total autorise est inferieur au risque d'un seul trade")
        if t.tp_r_multiple < r.min_rr: problems.append(f"l'objectif initial ({t.tp_r_multiple}R) est sous le ratio minimal exige ({r.min_rr})")
        if t.breakeven_at_r >= t.tp_r_multiple: problems.append("le break-even se declenche apres l'objectif")
        if t.extend_at_progress >= 1.0: problems.append("le seuil d'extension doit etre inferieur a 1")
        if t.min_stop_atr > t.atr_stop_mult: problems.append("le stop minimal est plus large que le stop nominal")
        if s.min_score > 0.95: problems.append("seuil de score quasi inatteignable")
        if e.poll_seconds < 1.0: problems.append("cadence trop agressive")
        if t.atr_stop_mult > 0:
            spread_en_r = s.max_spread_atr_ratio / t.atr_stop_mult
            plafond_en_r = r.max_cost_ratio_pct / 100.0
            if spread_en_r > plafond_en_r:
                problems.append(
                    f"le filtre de spread autorise {spread_en_r:.2f} R de spread alors que le plafond de cout n'admet que {plafond_en_r:.2f} R : baisser strategy.max_spread_atr_ratio sous {plafond_en_r * t.atr_stop_mult:.2f}")
        return problems
