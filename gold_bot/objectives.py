"""Objectifs de performance par paliers hebdomadaires.

Principe demande : 100 EUR la premiere semaine, puis un niveau de plus
chaque semaine.

Point critique, et c'est la partie qui protege le compte : un objectif
chiffre ne doit JAMAIS augmenter le risque pour rattraper un retard.
C'est le mecanisme qui detruit les petits comptes (on double la mise apres
une mauvaise serie, et une seule sequence defavorable efface tout).

Ici l'objectif agit dans ce sens :

  - en retard  -> le robot devient PLUS SELECTIF (seuil de score releve),
                  la taille ne monte que dans une bande bornee et
                  uniquement si le capital a reellement progresse ;
  - en avance  -> le robot protege : risque reduit, seuil releve ;
  - objectif atteint -> mode preservation, il ne rend pas les gains.

Le palier suivant n'est debloque que si le precedent a ete atteint : le
defi monte avec les resultats, pas avec le calendrier.
"""
from __future__ import annotations

import json
import logging
import math
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from typing import Optional

from .state import chemin_par_instance

logger = logging.getLogger(__name__)


def week_key(ts: Optional[float] = None) -> str:
    """Identifiant de la semaine ISO (ex: '2026-W34'), en UTC."""
    dt = datetime.fromtimestamp(ts or time.time(), tz=timezone.utc)
    year, week, _ = dt.isocalendar()
    return f"{year}-W{week:02d}"


@dataclass(slots=True)
class ObjectiveConfig:
    """Parametrage du defi hebdomadaire."""

    base_target: float = 100.0        # objectif de la semaine 1, en devise du compte
    escalation: float = 1.5           # multiplicateur du palier suivant
    escalation_mode: str = "geometric"  # "geometric" (x1.5) ou "linear" (+base)
    max_level: int = 52
    # Garde-fous : un objectif ne peut pas depasser ce % du capital sur la semaine.
    max_weekly_target_pct: float = 8.0
    # Le palier ne monte que si l'objectif precedent a ete atteint.
    promote_only_on_success: bool = True
    # Retrogradation apres une semaine perdante : on redescend d'un cran.
    demote_on_losing_week: bool = True
    # Modulation autorisee du risque par l'objectif (bande fermee).
    min_multiplier: float = 0.4
    max_multiplier: float = 1.3
    # Une fois l'objectif atteint, on passe en preservation.
    protect_after_target: bool = True
    protect_multiplier: float = 0.4


@dataclass(slots=True)
class WeekRecord:
    """Resultat d'une semaine."""

    week: str
    level: int
    target: float
    realized: float = 0.0
    trades: int = 0
    achieved: bool = False


@dataclass(slots=True)
class ObjectiveState:
    """Etat courant du defi, persistable sur disque."""

    level: int = 1
    current_week: str = field(default_factory=week_key)
    week_start_equity: float = 0.0
    realized_this_week: float = 0.0
    trades_this_week: int = 0
    history: list[dict] = field(default_factory=list)
    achieved_this_week: bool = False


class ObjectiveTracker:
    """Suit le defi hebdomadaire et module le comportement du robot."""

    def __init__(self, config: Optional[ObjectiveConfig] = None, state_file: str = "",
                 instance: str = "") -> None:
        self.config = config or ObjectiveConfig()
        self.state_file = state_file or chemin_par_instance(
            "data/objectives.json", "GB_OBJECTIVE_FILE", instance)
        self.state = ObjectiveState()
        self.load()

    # ---------------------------------------------------------------
    # Calcul des paliers
    # ---------------------------------------------------------------
    def raw_target(self, level: int) -> float:
        """Objectif nominal du palier, avant plafonnement."""
        cfg = self.config
        level = max(1, min(level, cfg.max_level))
        if cfg.escalation_mode == "linear":
            return round(cfg.base_target * level, 2)
        return round(cfg.base_target * (cfg.escalation ** (level - 1)), 2)

    def target_for_level(self, level: int, equity: float = 0.0) -> float:
        """Objectif retenu : le nominal, plafonne par la capacite du compte.

        Viser 100 EUR sur un compte de 500 EUR revient a chercher +20 % en
        une semaine : statistiquement, cela impose un risque qui detruit le
        compte avant d'y arriver. Le plafond `max_weekly_target_pct` ramene
        l'objectif a ce que le capital peut reellement porter, et il monte
        tout seul a mesure que le compte grossit.
        """
        raw = self.raw_target(level)
        cfg = self.config
        if equity > 0 and cfg.max_weekly_target_pct > 0:
            cap = equity * cfg.max_weekly_target_pct / 100.0
            if raw > cap:
                return round(cap, 2)
        return raw

    def is_capped(self, equity: float = 0.0) -> bool:
        """L'objectif nominal depasse-t-il ce que le capital peut porter ?"""
        eq = equity or self.state.week_start_equity
        return eq > 0 and self.target_for_level(self.state.level, eq) < self.raw_target(self.state.level)

    def equity_needed(self, level: Optional[int] = None) -> float:
        """Capital necessaire pour viser le palier sans plafonnement."""
        lvl = level if level is not None else self.state.level
        pct = self.config.max_weekly_target_pct
        return round(self.raw_target(lvl) / (pct / 100.0), 2) if pct > 0 else 0.0

    @property
    def target(self) -> float:
        return self.target_for_level(self.state.level, self.state.week_start_equity)

    def ladder(self, equity: float, count: int = 8) -> list[dict]:
        """Apercu des prochains paliers : nominal, retenu, capital requis."""
        return [
            {
                "palier": lvl,
                "objectif_nominal": self.raw_target(lvl),
                "objectif_retenu": self.target_for_level(lvl, equity),
                "capital_requis": self.equity_needed(lvl),
                "plafonne": self.target_for_level(lvl, equity) < self.raw_target(lvl),
            }
            for lvl in range(self.state.level, self.state.level + count)
        ]

    # ---------------------------------------------------------------
    # Cycle de vie
    # ---------------------------------------------------------------
    def sync(self, equity: float, ts: Optional[float] = None) -> None:
        """Detecte le changement de semaine et fait evoluer le palier."""
        wk = week_key(ts)
        if not self.state.week_start_equity:
            self.state.week_start_equity = equity
        if wk == self.state.current_week:
            return

        # Cloture de la semaine ecoulee
        record = WeekRecord(
            week=self.state.current_week,
            level=self.state.level,
            target=self.target,
            realized=round(self.state.realized_this_week, 2),
            trades=self.state.trades_this_week,
            achieved=self.state.realized_this_week >= self.target,
        )
        self.state.history.append(asdict(record))
        cfg = self.config

        if record.achieved:
            self.state.level = min(cfg.max_level, self.state.level + 1)
            logger.info("objectif %s atteint (%.2f/%.2f) -> palier %d",
                        record.week, record.realized, record.target, self.state.level)
        elif record.realized < 0 and cfg.demote_on_losing_week:
            self.state.level = max(1, self.state.level - 1)
            logger.info("semaine %s perdante (%.2f) -> retour au palier %d",
                        record.week, record.realized, self.state.level)
        elif not cfg.promote_only_on_success:
            self.state.level = min(cfg.max_level, self.state.level + 1)
        else:
            logger.info("objectif %s non atteint (%.2f/%.2f) -> palier %d maintenu",
                        record.week, record.realized, record.target, self.state.level)

        self.state.current_week = wk
        self.state.realized_this_week = 0.0
        self.state.trades_this_week = 0
        self.state.week_start_equity = equity
        self.state.achieved_this_week = False
        self.save()

    def record_trade(self, profit: float) -> None:
        """Enregistre le resultat d'un trade cloture."""
        self.state.realized_this_week += profit
        self.state.trades_this_week += 1
        if self.state.realized_this_week >= self.target:
            self.state.achieved_this_week = True
        self.save()

    # ---------------------------------------------------------------
    # Modulation du comportement
    # ---------------------------------------------------------------
    def progress(self) -> float:
        """Avancement vers l'objectif de la semaine (peut etre negatif)."""
        tgt = self.target
        return self.state.realized_this_week / tgt if tgt > 0 else 0.0

    def expected_pace(self, ts: Optional[float] = None) -> float:
        """Avancement theorique attendu a cet instant de la semaine (0 a 1).

        On raisonne en jours de marche : le week-end ne compte quasiment pas
        (seules les cryptos tournent), donc la cadence attendue est lissee.
        """
        dt = datetime.fromtimestamp(ts or time.time(), tz=timezone.utc)
        elapsed = dt.weekday() + dt.hour / 24.0     # 0 (lundi 00h) a 6.99
        return max(0.0, min(1.0, elapsed / 5.0))    # objectif vise sur 5 jours

    def status(self, ts: Optional[float] = None) -> dict:
        pace = self.expected_pace(ts)
        prog = self.progress()
        return {
            "palier": self.state.level,
            "semaine": self.state.current_week,
            "objectif": self.target,
            "objectif_nominal": self.raw_target(self.state.level),
            "plafonne": self.is_capped(),
            "capital_requis": self.equity_needed(),
            "realise": round(self.state.realized_this_week, 2),
            "avancement": round(prog, 3),
            "cadence_attendue": round(pace, 3),
            "en_avance": prog >= pace,
            "atteint": self.state.achieved_this_week,
            "trades": self.state.trades_this_week,
        }

    def risk_multiplier(self, ts: Optional[float] = None) -> tuple[float, str]:
        """Multiplicateur de risque induit par l'objectif, toujours borne.

        Retourne (multiplicateur, explication). Jamais au-dessus de
        `max_multiplier` : l'objectif ne peut pas provoquer de sur-risque.
        """
        cfg = self.config
        prog = self.progress()
        pace = self.expected_pace(ts)

        if cfg.protect_after_target and self.state.achieved_this_week:
            return cfg.protect_multiplier, "objectif de la semaine atteint : mode preservation"

        if prog < 0:
            # Semaine deja negative : on reduit, on ne cherche pas a se refaire.
            severity = min(1.0, abs(prog))
            mult = max(cfg.min_multiplier, 1.0 - 0.6 * severity)
            return mult, f"semaine negative ({prog:+.0%} de l'objectif) : risque reduit"

        if prog >= pace + 0.25:
            return 0.75, "nettement en avance sur l'objectif : on securise"

        if pace > 0.35 and prog < pace - 0.25:
            # En retard : on NE monte PAS le risque. On devient selectif.
            return 1.0, "en retard sur l'objectif : selectivite renforcee (risque inchange)"

        return 1.0, "cadence conforme a l'objectif"

    def score_threshold_bonus(self, ts: Optional[float] = None) -> float:
        """Durcissement du seuil de validation selon l'avancement.

        C'est le vrai levier quand le robot est en retard : prendre MOINS de
        trades, mais meilleurs. Et quand l'objectif est atteint, ne garder
        que l'exceptionnel.
        """
        if self.state.achieved_this_week:
            return 0.15
        prog, pace = self.progress(), self.expected_pace(ts)
        if prog < 0:
            return 0.10          # semaine negative : on resserre
        if pace > 0.35 and prog < pace - 0.25:
            return 0.06          # en retard : on resserre un peu
        if prog >= pace + 0.25:
            return 0.05          # en avance : inutile de se disperser
        return 0.0

    def should_stop_trading(self) -> tuple[bool, str]:
        """Arret volontaire de la semaine (objectif largement depasse)."""
        if not self.config.protect_after_target:
            return False, ""
        if self.progress() >= 1.6:
            return True, "objectif de la semaine largement depasse : arret jusqu'a lundi"
        return False, ""

    # ---------------------------------------------------------------
    def save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.state_file) or ".", exist_ok=True)
            with open(self.state_file, "w", encoding="utf-8") as fh:
                json.dump(asdict(self.state), fh, indent=2, ensure_ascii=False)
        except OSError as exc:
            logger.warning("sauvegarde objectifs impossible : %s", exc)

    def load(self) -> None:
        if not os.path.exists(self.state_file):
            return
        try:
            with open(self.state_file, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            self.state = ObjectiveState(**data)
        except (OSError, ValueError, TypeError) as exc:
            logger.warning("etat objectifs illisible, reinitialisation : %s", exc)
