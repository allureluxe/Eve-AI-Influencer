"""Configuration globale du robot.

Trois niveaux, du plus faible au plus fort :
  1. les valeurs par defaut ci-dessous,
  2. un fichier JSON (`--config robot.json`),
  3. les variables d'environnement (prefixe GB_).

Les parametres sensibles (cles API) ne passent QUE par l'environnement :
aucune cle ne doit se retrouver dans un fichier de configuration versionne.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from typing import Any, Optional

from .objectives import ObjectiveConfig
from .risk import RiskConfig
from .strategy import StrategyConfig
from .trade_manager import TradeManagerConfig

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class EngineConfig:
    """Parametres de la boucle principale."""

    broker: str = "paper"       # "paper" | "moonx" | "binance" | "binance_spot"
    poll_seconds: float = 5.0             # cadence quand une position est ouverte
    idle_poll_seconds: float = 20.0       # cadence en recherche d'opportunite
    closed_market_seconds: float = 300.0  # cadence quand tout est ferme
    max_consecutive_errors: int = 12
    error_backoff_seconds: float = 15.0
    heartbeat_minutes: float = 60.0
    daily_report_hour: int = 21           # heure UTC du rapport quotidien
    symbols: list[str] = field(default_factory=list)   # vide = tout l'univers
    start_balance: float = 1000.0         # capital initial en simulation
    currency: str = "EUR"
    dry_run: bool = False                 # analyse sans envoyer d'ordre
    offline: bool = False                 # source synthetique (tests uniquement)
    verbose_scan: bool = False


@dataclass(slots=True)
class BotConfig:
    """Configuration complete du robot."""

    engine: EngineConfig = field(default_factory=EngineConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    trade: TradeManagerConfig = field(default_factory=TradeManagerConfig)
    objectives: ObjectiveConfig = field(default_factory=ObjectiveConfig)

    # ---------------------------------------------------------------
    @classmethod
    def load(cls, path: str = "") -> "BotConfig":
        cfg = cls()
        path = path or os.getenv("GB_CONFIG_FILE", "")
        if path and os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                cfg.apply(data)
                logger.info("configuration chargee depuis %s", path)
            except (OSError, ValueError) as exc:
                logger.error("configuration illisible (%s), valeurs par defaut : %s", path, exc)
        cfg.apply_env()
        return cfg

    def apply(self, data: dict[str, Any]) -> None:
        """Applique un dictionnaire de configuration (imbrique par section)."""
        for section_name, values in (data or {}).items():
            # Les cles prefixees par "_" sont des commentaires du fichier de
            # configuration (JSON n'en accepte pas nativement).
            if section_name.startswith("_"):
                continue
            section = getattr(self, section_name, None)
            if section is None or not is_dataclass(section) or not isinstance(values, dict):
                continue
            valid = {f.name for f in fields(section)}
            for key, value in values.items():
                if key in valid:
                    setattr(section, key, value)
                else:
                    logger.warning("parametre inconnu ignore : %s.%s", section_name, key)

    def apply_env(self) -> None:
        """Surcharge par variables d'environnement (GB_<SECTION>_<PARAM>)."""
        for section_name in ("engine", "strategy", "risk", "trade", "objectives"):
            section = getattr(self, section_name)
            for f in fields(section):
                env_key = f"GB_{section_name.upper()}_{f.name.upper()}"
                raw = os.getenv(env_key)
                if raw is None:
                    continue
                try:
                    current = getattr(section, f.name)
                    if isinstance(current, bool):
                        value: Any = raw.strip().lower() in ("1", "true", "yes", "oui")
                    elif isinstance(current, int) and not isinstance(current, bool):
                        value = int(raw)
                    elif isinstance(current, float):
                        value = float(raw)
                    elif isinstance(current, list):
                        value = [x.strip() for x in raw.split(",") if x.strip()]
                    else:
                        value = raw
                    setattr(section, f.name, value)
                    logger.debug("%s.%s surcharge par %s", section_name, f.name, env_key)
                except ValueError:
                    logger.warning("valeur invalide pour %s : %r", env_key, raw)

    def to_dict(self) -> dict[str, Any]:
        return {name: asdict(getattr(self, name))
                for name in ("engine", "strategy", "risk", "trade", "objectives")}

    def save(self, path: str) -> None:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=2, ensure_ascii=False)

    # ---------------------------------------------------------------
    def validate(self) -> list[str]:
        """Verifie la coherence de la configuration. Retourne les problemes."""
        problems: list[str] = []
        r, t, s, e = self.risk, self.trade, self.strategy, self.engine

        if r.max_risk_pct > 3.0:
            problems.append(f"risque maximal par trade tres eleve ({r.max_risk_pct}%) : "
                            f"au-dela de 2 %, une serie normale de pertes devient dangereuse")
        if r.base_risk_pct > r.max_risk_pct:
            problems.append("risque de base superieur au plafond")
        if r.min_risk_pct > r.base_risk_pct:
            problems.append("risque minimal superieur au risque de base")
        if r.daily_loss_limit_pct >= r.weekly_loss_limit_pct:
            problems.append("la limite journaliere doit etre inferieure a la limite hebdomadaire")
        if r.max_total_risk_pct < r.max_risk_pct:
            problems.append("le risque total autorise est inferieur au risque d'un seul trade")
        if t.tp_r_multiple < r.min_rr:
            problems.append(f"l'objectif initial ({t.tp_r_multiple}R) est sous le ratio minimal "
                            f"exige ({r.min_rr}) : aucun trade ne passera le filtre")
        if t.breakeven_at_r >= t.tp_r_multiple:
            problems.append("le break-even se declenche apres l'objectif : il ne servira jamais")
        if t.extend_at_progress >= 1.0:
            problems.append("le seuil d'extension doit etre inferieur a 1 (fraction du chemin vers le TP)")
        if t.min_stop_atr > t.atr_stop_mult:
            problems.append("le stop minimal est plus large que le stop nominal")
        if s.min_score > 0.95:
            problems.append("seuil de score quasi inatteignable : le robot ne tradera jamais")
        if e.poll_seconds < 1.0:
            problems.append("cadence trop agressive : risque de saturation des sources de donnees")
        if e.broker in ("moonx", "binance", "binance_spot") and e.offline:
            problems.append("mode hors ligne incompatible avec une execution reelle")
        if e.broker not in ("paper", "moonx", "binance", "binance_spot"):
            problems.append(f"lieu d'execution inconnu : {e.broker}")
        return problems
