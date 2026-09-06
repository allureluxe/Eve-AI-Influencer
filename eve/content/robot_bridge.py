"""Pont entre le robot de trading et le récit d'Eve.

Le robot et Eve vivent dans le même dépôt, sur deux branches. Le robot tient
déjà son journal — `data/trades.jsonl`, une ligne par trade fermé — avec tout
ce dont Eve a besoin : profit, date, drawdown calculable.

Ce module lit ce fichier et en dérive un `story.Journal`. Aucun chiffre n'est
saisi à la main, aucune conversation n'a besoin d'être transférée : la vérité
est dans le fichier du robot, Eve ne fait que la raconter.

Le fichier est cherché, dans l'ordre :
  1. `ROBOT_TRADES_FILE` (chemin explicite)
  2. `GB_TRADES_FILE`    (la variable du robot lui-même)
  3. `data/trades.jsonl` sous la racine du projet
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from eve.config import settings
from eve.content.story import Entree, Journal

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Trade:
    closed_at: float
    profit: float
    symbol: str = ""
    partial: bool = False

    @property
    def jour(self) -> str:
        return datetime.fromtimestamp(self.closed_at, tz=timezone.utc).date().isoformat()


def chemin_trades() -> Path | None:
    """Emplacement du journal du robot, s'il existe."""
    candidats = [os.getenv("ROBOT_TRADES_FILE", ""),
                 os.getenv("GB_TRADES_FILE", ""),
                 str(settings.paths.data / "trades.jsonl")]
    for brut in candidats:
        if brut and Path(brut).exists():
            return Path(brut)
    return None


def lire_trades(chemin: Path | None = None) -> list[Trade]:
    """Lit le journal ligne à ligne. Une ligne illisible est ignorée, pas fatale."""
    src = chemin or chemin_trades()
    if src is None or not src.exists():
        return []

    trades: list[Trade] = []
    for numero, ligne in enumerate(src.read_text(encoding="utf-8").splitlines(), start=1):
        ligne = ligne.strip()
        if not ligne:
            continue
        try:
            brut = json.loads(ligne)
            trades.append(Trade(
                closed_at=float(brut["closed_at"]),
                profit=float(brut["profit"]),
                symbol=str(brut.get("symbol", "")),
                partial=bool(brut.get("partial", False)),
            ))
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            log.warning("%s ligne %d illisible, ignorée.", src.name, numero)
    trades.sort(key=lambda t: t.closed_at)
    return trades


def journal_depuis_robot(capital_depart: float | None = None,
                         chemin: Path | None = None) -> Journal | None:
    """Construit le journal d'Eve à partir des trades réels du robot.

    Une entrée par jour de trading, avec le solde en fin de journée. Le
    `plus_bas_eur` du récit se calcule alors tout seul sur ces soldes — la
    baisse ne peut pas être masquée.
    """
    trades = [t for t in lire_trades(chemin) if not t.partial]
    if not trades:
        return None

    capital = capital_depart
    if capital is None:
        from eve.persona.persona import load_persona
        capital = float(load_persona().raw().get("story", {})
                        .get("capital_depart_eur", 100))

    aujourdhui = date.today().isoformat()
    solde = capital
    par_jour: dict[str, float] = {}
    for trade in trades:
        if trade.jour > aujourdhui:      # jamais de trade daté du futur
            continue
        solde = round(solde + trade.profit, 2)
        par_jour[trade.jour] = solde

    if not par_jour:
        return None

    jours = sorted(par_jour)
    entrees = [Entree(date=jours[0], etape="cent_euros", solde_eur=capital,
                      note="Compte réel ouvert.")]
    entrees += [Entree(date=jour, etape="", solde_eur=par_jour[jour], note="")
                for jour in jours]
    # La première semaine de données réelles franchit l'étape correspondante.
    if len(jours) >= 5:
        entrees[-1] = Entree(entrees[-1].date, "premiere_semaine",
                             entrees[-1].solde_eur,
                             f"{len(trades)} trades depuis l'ouverture.")
    return Journal(capital, entrees)


def resume() -> dict[str, object]:
    """Diagnostic lisible : d'où viennent les chiffres, et que disent-ils."""
    src = chemin_trades()
    journal = journal_depuis_robot()
    return {
        "fichier": str(src) if src else "aucun",
        "trades": len(lire_trades()),
        "solde": journal.solde_actuel if journal else None,
        "variation_pct": journal.variation_pct if journal else None,
        "plus_bas": journal.plus_bas_eur if journal else None,
    }
