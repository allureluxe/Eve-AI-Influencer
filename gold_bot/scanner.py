"""Scanner multi-actifs.

Le robot est libre du produit qu'il traite : a chaque cycle il evalue tous
les instruments ouverts, ecarte ceux qui ne passent pas les filtres, et ne
retient que la meilleure opportunite validee. Si rien n'est valide, il ne
force pas : il attend le cycle suivant.

Optimisation importante pour le court terme : les indicateurs sont mis a
jour de facon INCREMENTALE. On ne recalcule pas 300 bougies a chaque
cycle, on ne pousse que les bougies nouvellement cloturees. Un cycle
complet sur une dizaine d'instruments coute alors quelques millisecondes
de calcul, le reste etant le temps reseau.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from .chart import ChartRead, read_chart
from .core import Candle, Side, Tick
from .datasources import DataRegistry
from .datasources.base import ProviderError
from .indicators import IndicatorSet
from .news import NewsFilter, NewsWindow
from .strategy import Evaluation, Strategy
from .universe import Instrument, Universe

logger = logging.getLogger(__name__)


@dataclass
class SymbolContext:
    """Etat persistant d'un instrument entre deux cycles."""

    symbol: str
    indicators: dict[str, IndicatorSet] = field(default_factory=dict)
    last_ts: dict[str, float] = field(default_factory=dict)
    charts: dict[str, ChartRead] = field(default_factory=dict)
    chart_refreshed: dict[str, float] = field(default_factory=dict)
    last_error: str = ""
    last_update: float = 0.0

    def feed(self, timeframe: str, candles: list[Candle], history: int = 300) -> int:
        """Injecte les nouvelles bougies cloturees. Retourne le nombre traite."""
        if not candles:
            return 0
        ind = self.indicators.get(timeframe)
        if ind is None:
            ind = IndicatorSet(history=history)
            self.indicators[timeframe] = ind
            self.last_ts[timeframe] = 0.0

        last_known = self.last_ts.get(timeframe, 0.0)
        # On ignore la derniere bougie : elle est encore en formation et ses
        # valeurs changent a chaque tick. On ne decide que sur du cloture.
        closed = candles[:-1] if len(candles) > 1 else candles
        fresh = [c for c in closed if c.ts > last_known]
        for c in fresh:
            ind.update(c)
        if fresh:
            self.last_ts[timeframe] = fresh[-1].ts
            self.last_update = time.time()
        return len(fresh)

    def chart(self, timeframe: str, round_step: float, max_age: float = 60.0) -> Optional[ChartRead]:
        """Lecture graphique, mise en cache (calcul plus lourd que les indicateurs)."""
        ind = self.indicators.get(timeframe)
        if ind is None or not ind.ready:
            return None
        now = time.time()
        if now - self.chart_refreshed.get(timeframe, 0.0) > max_age or timeframe not in self.charts:
            self.charts[timeframe] = read_chart(ind, round_step)
            self.chart_refreshed[timeframe] = now
        return self.charts[timeframe]


@dataclass(slots=True)
class ScanResult:
    """Resultat d'un cycle de scan complet."""

    best: Optional[Evaluation] = None
    evaluations: list[Evaluation] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)
    scanned: int = 0
    duration_ms: float = 0.0
    ts: float = field(default_factory=time.time)

    def valid_ones(self) -> list[Evaluation]:
        return [e for e in self.evaluations if e.valid]

    def summary(self) -> str:
        valid = self.valid_ones()
        if self.best:
            return (f"{self.scanned} instruments en {self.duration_ms:.0f} ms, "
                    f"{len(valid)} valide(s) -> {self.best.explain()}")
        blockers: dict[str, int] = {}
        for ev in self.evaluations:
            failed = ev.failed_gates()
            key = failed[0].name if failed else (ev.rejected_by or "score")
            blockers[key] = blockers.get(key, 0) + 1
        detail = ", ".join(f"{k} x{v}" for k, v in sorted(blockers.items(), key=lambda kv: -kv[1])[:4])
        return f"{self.scanned} instruments en {self.duration_ms:.0f} ms, aucune opportunite ({detail})"


class Scanner:
    """Parcourt l'univers et classe les opportunites."""

    def __init__(
        self,
        registry: DataRegistry,
        universe: Universe,
        strategy: Strategy,
        news: Optional[NewsFilter] = None,
        history: int = 300,
    ) -> None:
        self.registry = registry
        self.universe = universe
        self.strategy = strategy
        self.news = news
        self.history = history
        self.contexts: dict[str, SymbolContext] = {}
        # Instruments mis en sommeil : symbole -> (fin de la mise en sommeil, motif).
        # Quand un instrument est structurellement inexploitable pour le capital
        # courant (lot minimum trop lourd, cout d'execution disproportionne), le
        # redemander a chaque cycle ne sert a rien : on consomme du quota d'API
        # pour un refus certain. On le met de cote, et on le reessaie plus tard —
        # le capital change, les conditions aussi.
        self.dormant: dict[str, tuple[float, str]] = {}

    # ---------------------------------------------------------------
    def sleep_symbol(self, symbol: str, seconds: float, reason: str) -> None:
        """Met un instrument de cote pour un temps donne."""
        fin = time.time() + seconds
        connu = self.dormant.get(symbol)
        if connu is None or connu[0] < fin:
            self.dormant[symbol] = (fin, reason)
            logger.info("%s mis de cote %.0f min : %s", symbol, seconds / 60, reason)

    def wake_symbol(self, symbol: str) -> None:
        self.dormant.pop(symbol, None)

    def is_dormant(self, symbol: str, now: Optional[float] = None) -> tuple[bool, str]:
        fin_motif = self.dormant.get(symbol)
        if not fin_motif:
            return False, ""
        fin, motif = fin_motif
        if (now or time.time()) >= fin:
            self.dormant.pop(symbol, None)
            return False, ""
        return True, motif

    def context(self, symbol: str) -> SymbolContext:
        ctx = self.contexts.get(symbol)
        if ctx is None:
            ctx = SymbolContext(symbol=symbol)
            self.contexts[symbol] = ctx
        return ctx

    def refresh_symbol(self, instrument: Instrument) -> SymbolContext:
        """Met a jour les donnees d'un instrument (appels reseau minimises)."""
        ctx = self.context(instrument.symbol)
        timeframes = self.strategy.timeframes
        data = self.registry.multi_timeframe(
            instrument.symbol, instrument.asset_class, timeframes, self.history)
        for tf, candles in data.items():
            ctx.feed(tf, candles, self.history)
        ctx.last_error = ""
        return ctx

    # ---------------------------------------------------------------
    def evaluate_symbol(
        self,
        instrument: Instrument,
        score_bonus: float = 0.0,
        now: Optional[float] = None,
    ) -> Evaluation:
        """Evalue un seul instrument de bout en bout."""
        ctx = self.refresh_symbol(instrument)
        tick = self.registry.tick(instrument.symbol, instrument.asset_class)
        if tick is None:
            ev = Evaluation(symbol=instrument.symbol, asset_class=instrument.asset_class)
            ev.rejected_by = "aucune cotation disponible"
            from .strategy import Gate
            ev.gates.append(Gate("cotation", False, ev.rejected_by))
            return ev

        window: Optional[NewsWindow] = None
        if self.news is not None:
            window = self.news.check(instrument.asset_class, instrument.symbol, now)

        charts = {}
        entry_tf = self.strategy.config.entry_tf
        chart = ctx.chart(entry_tf, instrument.round_step)
        if chart is not None:
            charts[entry_tf] = chart

        return self.strategy.evaluate(
            instrument, ctx.indicators, tick, news=window,
            charts=charts, score_bonus=score_bonus, now=now)

    # ---------------------------------------------------------------
    def scan(
        self,
        score_bonus: float = 0.0,
        exclude: Optional[set[str]] = None,
        allow: Optional[Callable[[Instrument], tuple[bool, str]]] = None,
        now: Optional[float] = None,
    ) -> ScanResult:
        """Cycle complet : evalue tous les instruments ouverts et classe.

        `exclude` : symboles deja en position.
        `allow`   : filtre externe (regles d'exposition du gestionnaire de risque).
        """
        started = time.perf_counter()
        result = ScanResult(ts=now or time.time())
        exclude = exclude or set()

        for instrument in self.universe.tradable(now):
            if instrument.symbol in exclude:
                continue
            endormi, motif = self.is_dormant(instrument.symbol, now)
            if endormi:
                result.errors[instrument.symbol] = f"en sommeil : {motif}"
                continue
            if allow is not None:
                ok, why = allow(instrument)
                if not ok:
                    result.errors[instrument.symbol] = why
                    continue
            result.scanned += 1
            try:
                ev = self.evaluate_symbol(instrument, score_bonus, now)
                result.evaluations.append(ev)
            except ProviderError as exc:
                result.errors[instrument.symbol] = f"donnees indisponibles : {str(exc)[:120]}"
                self.context(instrument.symbol).last_error = str(exc)
            except Exception as exc:  # noqa: BLE001 - un instrument ne doit jamais casser le cycle
                logger.exception("erreur d'evaluation sur %s", instrument.symbol)
                result.errors[instrument.symbol] = f"erreur interne : {str(exc)[:120]}"

        valid = sorted(result.valid_ones(), key=lambda e: -e.priority_score)
        result.best = valid[0] if valid else None
        result.duration_ms = (time.perf_counter() - started) * 1000.0
        return result

    # ---------------------------------------------------------------
    def report(self, result: ScanResult, verbose: bool = False) -> list[str]:
        """Rapport lisible du cycle (journal, alertes, diagnostic)."""
        lines = [result.summary()]
        for ev in sorted(result.evaluations, key=lambda e: -e.priority_score):
            lines.append(f"  {ev.explain()}")
            if verbose:
                lines.extend(f"  {l}" for l in ev.detail_lines())
        for sym, err in result.errors.items():
            lines.append(f"  {sym} : {err}")
        return lines
