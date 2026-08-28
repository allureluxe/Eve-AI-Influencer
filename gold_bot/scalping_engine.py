"""Extensions de moteur pour scalping continu.

Le moteur de base garde tous ses coupe-circuits. Cette couche ajoute uniquement
la capacite a reutiliser le capital libre et a pyramider une tendance quand une
nouvelle confirmation forte apparait.
"""
from __future__ import annotations

import logging
import time

from .core import Side
from .engine import TradingEngine

logger = logging.getLogger(__name__)


class ContinuousScalpingMixin:
    """Recherche continue et pyramiding prudent sur mouvement confirme."""

    max_pyramid_entries = 3
    min_pyramid_atr_move = 0.25
    min_pyramid_score_margin = 0.10
    min_pyramid_extra_confirmations = 1

    def _look_for_entry(self) -> None:
        positions = self.broker.positions()
        allowed, why = self.risk.can_trade(positions)
        if not allowed:
            logger.debug("pas de recherche : %s", why)
            return

        stop, stop_why = self.objectives.should_stop_trading()
        if stop:
            logger.info("recherche suspendue : %s", stop_why)
            return

        bonus = self.objectives.score_threshold_bonus()
        sens = None if getattr(self.broker, "supports_short", True) else {Side.BUY}

        def exposure_ok(inst):
            same = [p for p in positions if p.symbol == inst.symbol]
            if not same:
                return True, ""
            if len(same) >= self.max_pyramid_entries:
                return False, f"pyramiding limite a {self.max_pyramid_entries} sur {inst.symbol}"
            # On laisse le scanner analyser le symbole deja ouvert : le sens
            # sera controle apres evaluation pour ne jamais hedger par accident.
            return True, "pyramiding candidat"

        result = self.scanner.scan(
            score_bonus=bonus,
            exclude=set(),
            allow=exposure_ok,
            allowed_sides=sens,
        )
        logger.info("%s", result.summary())
        if self.config.engine.verbose_scan:
            for line in self.scanner.report(result, verbose=True)[1:]:
                logger.info("%s", line)

        ev = result.best
        if ev is None:
            return

        same_symbol = [p for p in positions if p.symbol == ev.symbol]
        if same_symbol:
            # Une nouvelle position sur le meme actif doit etre dans le meme
            # sens et correspondre a une vraie continuation, pas a du bruit.
            side = same_symbol[0].side
            if ev.side is not side:
                logger.info("pyramiding refuse sur %s : sens oppose", ev.symbol)
                return
            if not self._strong_continuation(ev, same_symbol):
                logger.info("pyramiding refuse sur %s : continuation insuffisante", ev.symbol)
                return

        self._execute(ev)

    def _strong_continuation(self, ev, positions) -> bool:
        """Exige une acceleration mesurable avant une nouvelle entree."""
        last = max(positions, key=lambda p: p.entry_time)
        atr = float(getattr(ev, "atr", 0.0) or 0.0)
        if atr <= 0:
            return False
        move = (ev.entry - last.entry_price) if ev.side is Side.BUY else (last.entry_price - ev.entry)
        if move < self.min_pyramid_atr_move * atr:
            return False

        if getattr(ev, "mode", "") == "quorum":
            required = int(getattr(ev, "required", 0) or 0)
            confirmed = int(getattr(ev, "confirmed", 0) or 0)
            if confirmed < required + self.min_pyramid_extra_confirmations:
                return False
        else:
            if ev.score < ev.threshold + self.min_pyramid_score_margin:
                return False

        # Une continuation doit aussi garder un ratio exploitable.
        if ev.rr < max(1.20, self.config.risk.min_rr):
            return False
        return True

    def _execute(self, ev) -> None:
        # Le moteur historique pouvait endormir un symbole une heure apres un
        # refus de dimensionnement. Pour un scalpeur, le capital se libere au
        # fil des secondes : on reveille donc toujours le symbole apres cet
        # appel afin qu'il soit reevalue au cycle suivant.
        try:
            super()._execute(ev)
        finally:
            try:
                self.scanner.wake_symbol(ev.symbol)
            except Exception:
                pass


class ContinuousScalpingEngine(ContinuousScalpingMixin, TradingEngine):
    """TradingEngine avec recherche continue et pyramiding confirme."""

    pass
