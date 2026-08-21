"""Moteur autonome.

Boucle unique, qui tourne 24h/24 sans intervention :

    synchroniser le compte
      -> gerer les positions ouvertes (stop, objectif, extension)
      -> encaisser les cloturees
      -> si le risque le permet : scanner l'univers
      -> si une opportunite passe TOUS les filtres : envoyer l'ordre
      -> dormir le temps utile, recommencer

Le robot ne demande jamais de validation : il analyse, decide et execute.
Les seules choses qui l'arretent sont ses propres coupe-circuits (limite de
perte, drawdown maximal) ou un arret explicite.

Robustesse : toute exception d'un cycle est capturee, comptee et suivie
d'une temporisation croissante. Un cycle en echec n'arrete pas le robot ;
seule une serie continue d'echecs declenche une alerte critique et une
mise en pause.
"""
from __future__ import annotations

import logging
import signal
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from .brokers import Broker, BrokerError, MoonXBroker, MoonXConfig, PaperBroker, PaperConfig
from .core import ClosedTrade, Position, Side, Tick
from .datasources import DataRegistry, build_registry
from .macro import MacroEngine
from .news import NewsFilter
from .notifiers import Notifier
from .objectives import ObjectiveTracker
from .risk import RiskManager
from .scanner import Scanner, ScanResult
from .settings import BotConfig
from .state import StateStore, TradeJournal
from .strategy import Evaluation, Strategy
from .trade_manager import ActionType, TradeAction, TradeManager
from .universe import Instrument, Universe

logger = logging.getLogger(__name__)


class TradingEngine:
    """Orchestrateur : assemble tous les modules et fait tourner la boucle."""

    def __init__(self, config: Optional[BotConfig] = None,
                 notifier: Optional[Notifier] = None) -> None:
        self.config = config or BotConfig.load()
        cfg = self.config

        problems = cfg.validate()
        if problems:
            for p in problems:
                logger.error("configuration : %s", p)
            raise ValueError("configuration incoherente : " + " | ".join(problems))

        self.notifier = notifier or Notifier()
        self.universe = Universe()
        if cfg.engine.symbols:
            self.universe.enable_only([s.upper() for s in cfg.engine.symbols])

        self.registry: DataRegistry = build_registry(offline=cfg.engine.offline)
        self.macro = MacroEngine(self.registry)
        self.news = NewsFilter()
        self.trade_manager = TradeManager(cfg.trade)
        self.strategy = Strategy(cfg.strategy, self.trade_manager, self.macro)
        self.scanner = Scanner(self.registry, self.universe, self.strategy,
                               self.news, cfg.strategy.history)
        self.risk = RiskManager(cfg.risk)
        self.objectives = ObjectiveTracker(cfg.objectives)
        self.store = StateStore()
        self.journal = TradeJournal()
        self.broker: Broker = self._build_broker()

        self._running = False
        self._stop_requested = False
        self._consecutive_errors = 0
        self._last_heartbeat = 0.0
        self._last_report_day = ""

    # ---------------------------------------------------------------
    def _build_broker(self) -> Broker:
        cfg = self.config.engine
        if cfg.broker == "moonx":
            mx = MoonXConfig.from_env()
            if cfg.dry_run:
                mx.dry_run = True
            broker = MoonXBroker(mx)
        else:
            broker = PaperBroker(PaperConfig(start_balance=cfg.start_balance,
                                             currency=cfg.currency))
        for inst in self.universe:
            if hasattr(broker, "register_instrument"):
                broker.register_instrument(inst)
        return broker

    # ---------------------------------------------------------------
    # Demarrage
    # ---------------------------------------------------------------
    def start(self) -> bool:
        """Prepare le robot. Retourne False si le demarrage est impossible."""
        cfg = self.config.engine

        if cfg.broker == "moonx" and cfg.offline:
            self.notifier.critical("Demarrage refuse",
                                   "execution reelle demandee avec des donnees synthetiques")
            return False

        if not self.broker.connect():
            self.notifier.critical("Connexion au broker impossible",
                                   f"broker={cfg.broker} — verifier la configuration")
            return False

        acc = self.broker.account()
        self.risk.sync_account(acc.equity, acc.balance, acc.currency)
        if self.store.state.account_reference:
            self.risk.account.reference_equity = self.store.state.account_reference
        if self.store.state.peak_equity:
            self.risk.account.peak_equity = self.store.state.peak_equity
        if self.store.state.halted:
            self.risk.halt(self.store.state.halt_reason or "arret memorise")

        self.objectives.sync(acc.equity)
        self._restore_positions()

        n_events = self.news.refresh(force=True)
        sources = [s["source"] for s in self.registry.status() if s["configuree"]]

        obj = self.objectives.status()
        body = "\n".join([
            f"Execution      : {cfg.broker}" + (" (DRY-RUN, aucun ordre envoye)" if cfg.dry_run else ""),
            f"Capital        : {acc.equity:.2f} {acc.currency}",
            f"Instruments    : {len(self.universe)} suivis, {len(self.universe.tradable())} ouverts maintenant",
            f"Sources prix   : {', '.join(sources) or 'aucune'}",
            f"Calendrier     : {n_events} evenements charges",
            f"Alertes        : {', '.join(self.notifier.active_channels())}",
            f"Objectif       : palier {obj['palier']}, {obj['objectif']:.2f} {acc.currency} cette semaine"
            + (f" (nominal {obj['objectif_nominal']:.2f}, plafonne par le capital)" if obj["plafonne"] else ""),
            f"Risque/trade   : {self.risk.effective_risk_pct()[0]:.2f} % "
            f"(plafond {self.config.risk.max_risk_pct:.2f} %)",
            f"Positions      : {len(self.broker.positions())} reprises",
        ])
        self.notifier.info("Robot demarre", body)
        self._running = True
        return True

    def _restore_positions(self) -> None:
        """Reprend la gestion des positions deja ouvertes apres un redemarrage."""
        for pos in self.broker.positions():
            if self.store.restore_position(pos):
                logger.info("gestion reprise sur %s %s (%d extension(s), stop a %.5f)",
                            pos.side.value, pos.symbol, pos.tp_extensions, pos.stop_loss)
            else:
                # Position inconnue du robot : on la reprend avec prudence,
                # en deduisant le risque initial des niveaux actuels.
                if not pos.initial_risk:
                    pos.initial_risk = abs(pos.entry_price - pos.stop_loss)
                self.store.remember_position(pos)
                logger.info("position externe adoptee : %s %s", pos.side.value, pos.symbol)
        self.store.save()

    # ---------------------------------------------------------------
    # Boucle principale
    # ---------------------------------------------------------------
    def run(self) -> None:
        """Boucle infinie. Ne rend la main que sur arret demande."""
        if not self._running and not self.start():
            return

        self._install_signal_handlers()
        logger.info("boucle demarree — cadence %.0fs / %.0fs (position ouverte / recherche)",
                    self.config.engine.poll_seconds, self.config.engine.idle_poll_seconds)

        while not self._stop_requested:
            cycle_start = time.time()
            try:
                self.run_cycle()
                self._consecutive_errors = 0
            except KeyboardInterrupt:
                break
            except Exception as exc:  # noqa: BLE001 - le robot ne doit jamais mourir sur un cycle
                self._handle_cycle_error(exc)

            self._sleep_until_next(cycle_start)

        self.shutdown()

    def run_cycle(self) -> None:
        """Un cycle complet de decision."""
        cfg = self.config.engine
        state = self.store.state
        state.cycles += 1
        state.last_cycle = time.time()

        # 1. Etat reel du compte et des positions
        self.broker.sync()
        acc = self.broker.account()
        self.risk.sync_account(acc.equity, acc.balance, acc.currency)
        self.objectives.sync(acc.equity)
        state.account_reference = self.risk.account.reference_equity
        state.peak_equity = self.risk.account.peak_equity

        positions = self.broker.positions()

        # 2. Gestion des positions ouvertes (priorite absolue)
        self._manage_positions(positions)

        # 3. Detection des cloturees
        self._collect_closed()

        # 4. Recherche d'une nouvelle opportunite
        self._look_for_entry()

        # 5. Suivi periodique
        self._heartbeat()
        self._daily_report()
        self.store.save()

    # ---------------------------------------------------------------
    # Gestion des positions
    # ---------------------------------------------------------------
    def _manage_positions(self, positions: list[Position]) -> None:
        """Applique le trailing, les extensions d'objectif et les sorties."""
        for pos in positions:
            instrument = self.universe.get(pos.symbol)
            if instrument is None:
                continue
            ctx = self.scanner.context(pos.symbol)
            try:
                self.scanner.refresh_symbol(instrument)
            except Exception as exc:  # noqa: BLE001
                logger.warning("donnees indisponibles pour gerer %s : %s", pos.symbol, str(exc)[:120])
                continue

            ind = ctx.indicators.get(self.config.strategy.entry_tf)
            if ind is None or not ind.ready:
                continue
            tick = self.registry.tick(pos.symbol, instrument.asset_class)
            if tick is None:
                continue

            # Le simulateur a besoin du prix pour evaluer SL/TP lui-meme.
            if isinstance(self.broker, PaperBroker):
                self.broker.set_price(pos.symbol, tick, ind.atr.value or 0.0)
                for trade in self.broker.check_tick(pos.symbol, tick):
                    self._on_trade_closed(trade)
                if pos.id not in {p.id for p in self.broker.positions()}:
                    continue

            chart = ctx.chart(self.config.strategy.entry_tf, instrument.round_step)
            window = self.news.check(instrument.asset_class, pos.symbol)

            actions = self.trade_manager.manage(
                pos, tick, ind, chart=chart, news=window, digits=instrument.digits)
            for action in actions:
                self._apply_action(pos, action, instrument)

            self.store.remember_position(pos)

    def _apply_action(self, pos: Position, action: TradeAction, instrument: Instrument) -> None:
        """Transmet une action de gestion au broker."""
        try:
            if action.type is ActionType.MODIFY_STOP:
                if self.broker.modify_position(pos.id, stop_loss=action.price):
                    logger.info("%s : stop -> %.5f (%s)", pos.symbol, action.price, action.reason)

            elif action.type is ActionType.MODIFY_TARGET:
                if self.broker.modify_position(pos.id, take_profit=action.price):
                    self.notifier.trade(
                        f"Objectif repousse — {pos.symbol}",
                        f"{pos.side.value} : TP {pos.initial_tp} -> {action.price}\n"
                        f"Stop a {pos.stop_loss} ({pos.locked_r():+.2f}R verrouille)\n"
                        f"{action.reason}",
                        data={"symbole": pos.symbol, "tp": action.price,
                              "extensions": pos.tp_extensions})

            elif action.type is ActionType.PARTIAL_CLOSE:
                trade = self.broker.close_position(pos.id, action.volume, action.reason)
                if trade:
                    self._on_trade_closed(trade)

            elif action.type is ActionType.CLOSE:
                trade = self.broker.close_position(pos.id, None, action.reason)
                if trade:
                    self._on_trade_closed(trade)

        except BrokerError as exc:
            logger.error("action %s refusee sur %s : %s", action.type.value, pos.symbol, exc)
            self.notifier.warning(f"Action refusee — {pos.symbol}",
                                  f"{action.type.value} : {exc}",
                                  throttle_key=f"action_{pos.symbol}", throttle_seconds=300)

    def _collect_closed(self) -> None:
        """Recupere les trades cloturees par le broker (stop ou objectif touche)."""
        known = {t.position_id for t in self.journal.trades}
        for trade in self.broker.closed_trades():
            key = f"{trade.position_id}_{trade.closed_at}"
            if trade.position_id in known and any(
                    t.position_id == trade.position_id and abs(t.closed_at - trade.closed_at) < 1
                    for t in self.journal.trades):
                continue
            self._on_trade_closed(trade)

    def _on_trade_closed(self, trade: ClosedTrade) -> None:
        """Comptabilise un trade termine."""
        if any(t.position_id == trade.position_id and abs(t.closed_at - trade.closed_at) < 1
               for t in self.journal.trades):
            return

        self.journal.append(trade)
        self.risk.record_close(trade)
        self.objectives.record_trade(trade.profit)
        self.store.state.trades_closed += 1
        self.store.forget_position(trade.position_id)

        obj = self.objectives.status()
        acc = self.risk.account
        level = "trade" if trade.profit >= 0 else "warning"
        self.notifier.notify(
            level,
            f"{'Gain' if trade.profit >= 0 else 'Perte'} {trade.profit:+.2f} {acc.currency} — {trade.symbol}",
            "\n".join([
                f"{trade.side.value} {trade.volume} lots : {trade.entry_price} -> {trade.exit_price}",
                f"Resultat : {trade.r_multiple:+.2f}R ({trade.reason})",
                f"Extensions d'objectif : {trade.tp_extensions}",
                f"Semaine : {obj['realise']:+.2f} / {obj['objectif']:.2f} "
                f"({obj['avancement']:.0%} du palier {obj['palier']})",
                f"Journee : {acc.daily_pnl_pct():+.2f} % | drawdown {acc.drawdown_pct():.2f} %",
            ]),
            data={"symbole": trade.symbol, "profit": trade.profit, "R": trade.r_multiple},
        )

        # Coupe-circuits atteints : on previent immediatement.
        ok, why = self.risk.can_trade(self.broker.positions())
        if not ok and any(k in why for k in ("limite", "drawdown", "pause")):
            self.notifier.warning("Trading suspendu", why,
                                  throttle_key="suspendu", throttle_seconds=1800)

    # ---------------------------------------------------------------
    # Recherche d'entree
    # ---------------------------------------------------------------
    def _look_for_entry(self) -> None:
        """Scanne l'univers et execute la meilleure opportunite validee."""
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
        held = {p.symbol for p in positions}

        def exposure_ok(inst: Instrument) -> tuple[bool, str]:
            return self.risk.check_exposure(inst, Side.BUY, positions, self.universe.get)

        result = self.scanner.scan(score_bonus=bonus, exclude=held, allow=exposure_ok)
        logger.info("%s", result.summary())
        if self.config.engine.verbose_scan:
            for line in self.scanner.report(result, verbose=True)[1:]:
                logger.info("%s", line)

        if result.best is None:
            return
        self._execute(result.best)

    def _execute(self, ev: Evaluation) -> None:
        """Dimensionne et envoie l'ordre. Aucune validation manuelle."""
        instrument = self.universe.get(ev.symbol)
        if instrument is None or ev.side is None:
            return

        positions = self.broker.positions()
        multiplier, why = self.objectives.risk_multiplier()
        sizing = self.risk.size_position(
            instrument, ev.side, ev.entry, ev.stop_loss, ev.take_profit,
            open_positions=positions, universe_lookup=self.universe.get,
            extra_multiplier=multiplier)

        if not sizing.allowed:
            logger.info("%s ecarte au dimensionnement : %s", ev.symbol, sizing.reason)
            self.notifier.notify("debug", f"Trade non dimensionnable — {ev.symbol}", sizing.reason)
            return

        try:
            pos = self.broker.open_position(
                instrument, ev.side, sizing.lots, ev.stop_loss, ev.take_profit,
                comment=f"{ev.setup} score={ev.score:.2f}")
        except BrokerError as exc:
            logger.error("ordre refuse sur %s : %s", ev.symbol, exc)
            self.notifier.warning(f"Ordre refuse — {ev.symbol}", str(exc))
            self.store.state.errors += 1
            return

        pos.initial_risk = abs(pos.entry_price - pos.stop_loss) or sizing.stop_distance
        self.store.remember_position(pos)
        self.store.state.trades_opened += 1
        self.risk.account.last_trade_ts = time.time()

        obj = self.objectives.status()
        self.notifier.trade(
            f"Position ouverte — {ev.side.value} {ev.symbol}",
            "\n".join([
                f"Scenario  : {ev.setup} (score {ev.score:.2f} / seuil {ev.threshold:.2f})",
                f"Entree    : {pos.entry_price} | SL {pos.stop_loss} | TP {pos.take_profit} (RR {ev.rr:.2f})",
                f"Volume    : {sizing.lots} lots — risque {sizing.risk_amount:.2f} "
                f"{self.risk.account.currency} ({sizing.risk_pct:.2f} %)",
                f"Taille    : {why}",
                f"Objectif  : palier {obj['palier']}, {obj['realise']:+.2f}/{obj['objectif']:.2f}",
                "Facteurs valides : " + ", ".join(g.name for g in ev.gates if g.passed),
                "Confluence : " + ", ".join(
                    f"{c.name} {c.value:+.2f}" for c in ev.components if abs(c.value) > 0.01),
            ]),
            data={"symbole": ev.symbol, "sens": ev.side.value, "lots": sizing.lots,
                  "entree": pos.entry_price, "sl": pos.stop_loss, "tp": pos.take_profit,
                  "score": ev.score, "setup": ev.setup},
        )

    # ---------------------------------------------------------------
    # Rythme et supervision
    # ---------------------------------------------------------------
    def _sleep_until_next(self, cycle_start: float) -> None:
        """Cadence adaptative : rapide en position, lente marche ferme."""
        cfg = self.config.engine
        if self.broker.positions():
            target = cfg.poll_seconds
        elif self.universe.tradable():
            target = cfg.idle_poll_seconds
        else:
            target = cfg.closed_market_seconds
        if self._consecutive_errors:
            target = max(target, cfg.error_backoff_seconds * min(self._consecutive_errors, 8))

        elapsed = time.time() - cycle_start
        delay = max(1.0, target - elapsed)
        end = time.time() + delay
        while time.time() < end and not self._stop_requested:
            time.sleep(min(1.0, end - time.time()))

    def _handle_cycle_error(self, exc: Exception) -> None:
        self._consecutive_errors += 1
        self.store.state.errors += 1
        logger.exception("erreur de cycle #%d", self._consecutive_errors)
        if self._consecutive_errors >= self.config.engine.max_consecutive_errors:
            reason = f"{self._consecutive_errors} cycles en echec : {str(exc)[:200]}"
            self.risk.halt(reason)
            self.store.state.halted = True
            self.store.state.halt_reason = reason
            self.notifier.critical("Robot en securite", reason)
        else:
            self.notifier.warning("Cycle en echec", str(exc)[:300],
                                  throttle_key="cycle_error", throttle_seconds=600)

    def _heartbeat(self) -> None:
        """Signe de vie periodique : prouve que le robot tourne vraiment."""
        interval = self.config.engine.heartbeat_minutes * 60
        if interval <= 0 or time.time() - self._last_heartbeat < interval:
            return
        self._last_heartbeat = time.time()
        acc = self.risk.account
        obj = self.objectives.status()
        uptime_h = (time.time() - self.store.state.started_at) / 3600.0
        self.notifier.info(
            "Robot actif",
            "\n".join([
                f"Actif depuis {uptime_h:.1f} h, {self.store.state.cycles} cycles",
                f"Capital {acc.equity:.2f} {acc.currency} "
                f"(jour {acc.daily_pnl_pct():+.2f} %, semaine {acc.weekly_pnl_pct():+.2f} %)",
                f"Positions ouvertes : {len(self.broker.positions())}",
                f"Objectif palier {obj['palier']} : {obj['realise']:+.2f}/{obj['objectif']:.2f}",
                f"Marches ouverts : {', '.join(i.symbol for i in self.universe.tradable()) or 'aucun'}",
            ]),
        )

    def _daily_report(self) -> None:
        """Bilan quotidien envoye une fois par jour."""
        now = datetime.now(timezone.utc)
        day = now.strftime("%Y-%m-%d")
        if now.hour < self.config.engine.daily_report_hour or self._last_report_day == day:
            return
        self._last_report_day = day

        since = time.time() - 86400
        stats = self.journal.stats(since)
        acc = self.risk.account
        obj = self.objectives.status()
        lines = [f"Capital : {acc.equity:.2f} {acc.currency} ({acc.daily_pnl_pct():+.2f} % sur la journee)"]
        if stats.get("trades"):
            lines += [
                f"Trades : {stats['trades']} ({stats['gagnants']} gagnants, "
                f"{stats['taux_reussite_pct']:.0f} % de reussite)",
                f"Resultat net : {stats['profit_net']:+.2f} {acc.currency}",
                f"Esperance : {stats['esperance_R']:+.3f}R par trade",
                f"Facteur de profit : {stats['facteur_profit']}",
                f"Objectifs repousses : {stats['trades_avec_extension']} trade(s), "
                f"{stats['extensions_tp_totales']} extension(s)",
            ]
        else:
            lines.append("Aucun trade aujourd'hui : aucune configuration n'a passe les filtres.")
        lines.append(f"Objectif hebdomadaire : {obj['realise']:+.2f} / {obj['objectif']:.2f} "
                     f"(palier {obj['palier']}, {obj['avancement']:.0%})")
        self.notifier.info(f"Bilan du {day}", "\n".join(lines))

    # ---------------------------------------------------------------
    def _install_signal_handlers(self) -> None:
        def handler(signum, _frame):
            logger.info("signal %s recu : arret propre demande", signum)
            self._stop_requested = True
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, handler)
            except (ValueError, OSError):   # pragma: no cover - hors thread principal
                pass

    def stop(self) -> None:
        self._stop_requested = True

    def shutdown(self) -> None:
        """Arret propre : on sauvegarde tout et on previent.

        Les positions ouvertes ne sont PAS fermees : leur stop-loss est
        deja place cote broker, elles restent protegees. Les fermer
        automatiquement transformerait un redemarrage en perte seche.
        """
        self.store.save()
        self.objectives.save()
        positions = self.broker.positions()
        stats = self.journal.stats(self.store.state.started_at)
        self.notifier.info(
            "Robot arrete",
            "\n".join([
                f"{self.store.state.cycles} cycles, {self.store.state.trades_closed} trades cloture(s)",
                f"Resultat de la session : {stats.get('profit_net', 0):+.2f}",
                f"{len(positions)} position(s) laissee(s) ouverte(s), protegees par leur stop",
            ]),
        )
        self._running = False

    # ---------------------------------------------------------------
    def status(self) -> dict:
        """Etat complet du robot (diagnostic, supervision)."""
        acc = self.broker.account()
        return {
            "broker": self.broker.name,
            "mode": getattr(self.broker, "mode", "simulation"),
            "actif": self._running,
            "cycles": self.store.state.cycles,
            "capital": round(acc.equity, 2),
            "devise": acc.currency,
            "positions": len(self.broker.positions()),
            "risque": self.risk.snapshot(),
            "objectif": self.objectives.status(),
            "marches_ouverts": [i.symbol for i in self.universe.tradable()],
            "sources": self.registry.status(),
            "alertes": self.notifier.active_channels(),
        }
