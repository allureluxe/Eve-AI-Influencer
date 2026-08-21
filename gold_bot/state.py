"""Persistance de l'etat et statistiques.

Le robot tourne en continu : il doit survivre a un redemarrage, une coupure
reseau ou un reboot du serveur. Tout ce qui ne peut pas etre relu depuis le
broker est sauvegarde ici (etat de gestion des positions, compteurs,
historique des trades).
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from .core import ClosedTrade, Position, Side

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class BotState:
    """Ce qui doit survivre a un redemarrage."""

    started_at: float = field(default_factory=time.time)
    last_cycle: float = 0.0
    cycles: int = 0
    trades_opened: int = 0
    trades_closed: int = 0
    errors: int = 0
    # Etat de gestion par position (extensions, break-even...) que le broker
    # ne connait pas : sans lui, une position reprise apres redemarrage
    # repartirait de zero et pourrait voir son stop recule.
    position_meta: dict[str, dict] = field(default_factory=dict)
    account_reference: float = 0.0
    peak_equity: float = 0.0
    halted: bool = False
    halt_reason: str = ""


class StateStore:
    """Lecture/ecriture atomique de l'etat sur disque."""

    def __init__(self, path: str = "") -> None:
        self.path = path or os.getenv("GB_STATE_FILE", "data/state.json")
        self.state = BotState()
        self.load()

    def load(self) -> BotState:
        if not os.path.exists(self.path):
            return self.state
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            self.state = BotState(**data)
            logger.info("etat repris : %d cycles, %d trades, demarre le %s",
                        self.state.cycles, self.state.trades_closed,
                        time.strftime("%d/%m %H:%M", time.gmtime(self.state.started_at)))
        except (OSError, ValueError, TypeError) as exc:
            logger.warning("etat illisible, redemarrage a neuf : %s", exc)
        return self.state

    def save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            tmp = f"{self.path}.tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(asdict(self.state), fh, indent=2, ensure_ascii=False)
            os.replace(tmp, self.path)      # ecriture atomique
        except OSError as exc:
            logger.warning("etat non sauvegarde : %s", exc)

    # ---------------------------------------------------------------
    def remember_position(self, pos: Position) -> None:
        """Memorise l'etat de gestion d'une position."""
        self.state.position_meta[pos.id] = {
            "initial_stop": pos.initial_stop,
            "initial_tp": pos.initial_tp,
            "initial_risk": pos.initial_risk,
            "max_favorable": pos.max_favorable,
            "max_adverse": pos.max_adverse,
            "tp_extensions": pos.tp_extensions,
            "breakeven_done": pos.breakeven_done,
            "partial_done": pos.partial_done,
            "opened_at": pos.opened_at,
        }

    def restore_position(self, pos: Position) -> bool:
        """Reapplique l'etat de gestion memorise. True si retrouve."""
        meta = self.state.position_meta.get(pos.id)
        if not meta:
            return False
        pos.initial_stop = meta.get("initial_stop", pos.stop_loss)
        pos.initial_tp = meta.get("initial_tp", pos.take_profit)
        pos.initial_risk = meta.get("initial_risk") or abs(pos.entry_price - pos.initial_stop)
        pos.max_favorable = meta.get("max_favorable", pos.entry_price)
        pos.max_adverse = meta.get("max_adverse", pos.entry_price)
        pos.tp_extensions = meta.get("tp_extensions", 0)
        pos.breakeven_done = meta.get("breakeven_done", False)
        pos.partial_done = meta.get("partial_done", False)
        pos.opened_at = meta.get("opened_at", pos.opened_at)
        return True

    def forget_position(self, position_id: str) -> None:
        self.state.position_meta.pop(position_id, None)


class TradeJournal:
    """Historique des trades et statistiques de performance."""

    def __init__(self, path: str = "") -> None:
        self.path = path or os.getenv("GB_TRADES_FILE", "data/trades.jsonl")
        self.trades: list[ClosedTrade] = []
        self.load()

    def load(self) -> None:
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    row = json.loads(line)
                    row["side"] = Side(row["side"])
                    self.trades.append(ClosedTrade(**row))
        except (OSError, ValueError, TypeError) as exc:
            logger.warning("historique de trades partiellement illisible : %s", exc)

    def append(self, trade: ClosedTrade) -> None:
        self.trades.append(trade)
        try:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            row = asdict(trade)
            row["side"] = trade.side.value
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        except OSError as exc:
            logger.warning("trade non journalise : %s", exc)

    # ---------------------------------------------------------------
    def stats(self, since: float = 0.0) -> dict[str, Any]:
        """Statistiques de performance sur la periode."""
        rows = [t for t in self.trades if t.closed_at >= since]
        if not rows:
            return {"trades": 0}

        # Une prise partielle n'est pas un trade : la compter comme un
        # gagnant a part entiere gonflerait artificiellement le taux de
        # reussite. On ne juge que les trades reellement termines, tout en
        # gardant le resultat des partielles dans le profit net.
        partials = [t for t in rows if t.partial]
        trades = [t for t in rows if not t.partial]
        if not trades:
            return {"trades": 0, "prises_partielles": len(partials),
                    "profit_net": round(sum(t.profit for t in rows), 2)}

        wins = [t for t in trades if t.profit > 0]
        losses = [t for t in trades if t.profit <= 0]
        gross_win = sum(t.profit for t in wins)
        gross_loss = abs(sum(t.profit for t in losses))
        rs = [t.r_multiple for t in trades]

        # Drawdown sur la courbe des gains cumules
        equity, peak, max_dd = 0.0, 0.0, 0.0
        for t in rows:
            equity += t.profit
            peak = max(peak, equity)
            max_dd = max(max_dd, peak - equity)

        return {
            "trades": len(trades),
            "prises_partielles": len(partials),
            "gagnants": len(wins),
            "perdants": len(losses),
            "taux_reussite_pct": round(len(wins) / len(trades) * 100.0, 2),
            "profit_net": round(sum(t.profit for t in rows), 2),
            "gain_brut": round(gross_win, 2),
            "perte_brute": round(gross_loss, 2),
            "facteur_profit": round(gross_win / gross_loss, 2) if gross_loss > 0 else None,
            "esperance_R": round(sum(rs) / len(rs), 3),
            "R_moyen_gagnant": round(sum(t.r_multiple for t in wins) / len(wins), 3) if wins else 0.0,
            "R_moyen_perdant": round(sum(t.r_multiple for t in losses) / len(losses), 3) if losses else 0.0,
            "meilleur": round(max(t.profit for t in trades), 2),
            "pire": round(min(t.profit for t in trades), 2),
            "drawdown_max": round(max_dd, 2),
            "extensions_tp_totales": sum(t.tp_extensions for t in trades),
            "trades_avec_extension": sum(1 for t in trades if t.tp_extensions > 0),
        }

    def by_symbol(self, since: float = 0.0) -> dict[str, dict]:
        """Performance ventilee par instrument : sert a desactiver ce qui ne marche pas."""
        out: dict[str, dict] = {}
        for t in self.trades:
            if t.closed_at < since:
                continue
            row = out.setdefault(t.symbol, {"trades": 0, "profit": 0.0, "gagnants": 0, "R": 0.0})
            row["trades"] += 1
            row["profit"] = round(row["profit"] + t.profit, 2)
            row["R"] = round(row["R"] + t.r_multiple, 3)
            if t.profit > 0:
                row["gagnants"] += 1
        for row in out.values():
            row["taux_reussite_pct"] = round(row["gagnants"] / row["trades"] * 100.0, 1)
        return out
