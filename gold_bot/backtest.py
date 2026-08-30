"""Backtest : rejoue l'historique bougie par bougie.

Regles de fidelite (sans elles, un backtest ment) :
  - aucune donnee future n'est accessible : les indicateurs ne recoivent
    que des bougies deja cloturees au moment de la decision ;
  - le stop est teste AVANT l'objectif quand une bougie touche les deux ;
  - le spread et la commission sont preleves a l'entree et a la sortie ;
  - la gestion dynamique (break-even, trailing, extension du TP) est
    appliquee a chaque bougie, exactement comme en direct.

Un backtest reste une approximation : il ne reproduit ni les elargissements
de spread sur annonce, ni les slippages reels, ni les rejets d'ordre.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from .brokers.paper import PaperBroker, PaperConfig
from .chart import read_chart
from .core import Candle, ClosedTrade, Side, Tick
from .datasources import DataRegistry, build_registry
from .engine import registre_pour
from .datasources.base import resample, tf_seconds
from .indicators import IndicatorSet
from .risk import RiskManager
from .settings import BotConfig
from .strategy import Strategy
from .trade_manager import ActionType, TradeManager
from .universe import Instrument, Universe, spread_estime

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    symbol: str
    bars: int = 0
    trades: list[ClosedTrade] = field(default_factory=list)
    equity_curve: list[tuple[float, float]] = field(default_factory=list)
    start_balance: float = 0.0
    end_balance: float = 0.0
    evaluations: int = 0
    rejections: dict[str, int] = field(default_factory=dict)

    def stats(self) -> dict:
        if not self.trades:
            return {"trades": 0, "resultat": 0.0,
                    "motifs_de_rejet": dict(sorted(self.rejections.items(), key=lambda kv: -kv[1])[:6])}
        # Les prises partielles ne comptent pas comme des trades distincts.
        partials = [t for t in self.trades if t.partial]
        trades = [t for t in self.trades if not t.partial]
        if not trades:
            return {"trades": 0, "prises_partielles": len(partials),
                    "resultat": round(self.end_balance - self.start_balance, 2),
                    "motifs_de_rejet": dict(sorted(self.rejections.items(), key=lambda kv: -kv[1])[:6])}
        wins = [t for t in trades if t.profit > 0]
        losses = [t for t in trades if t.profit <= 0]
        gross_w = sum(t.profit for t in wins)
        gross_l = abs(sum(t.profit for t in losses))
        peak, dd, eq = self.start_balance, 0.0, self.start_balance
        for t in self.trades:
            eq += t.profit
            peak = max(peak, eq)
            dd = max(dd, peak - eq)
        return {
            "trades": len(trades),
            "prises_partielles": len(partials),
            "taux_reussite_pct": round(len(wins) / len(trades) * 100, 1),
            "resultat": round(self.end_balance - self.start_balance, 2),
            "rendement_pct": round((self.end_balance / self.start_balance - 1) * 100, 2) if self.start_balance else 0,
            "facteur_profit": round(gross_w / gross_l, 2) if gross_l else None,
            "esperance_R": round(sum(t.r_multiple for t in trades) / len(trades), 3),
            "drawdown_max": round(dd, 2),
            "drawdown_max_pct": round(dd / self.start_balance * 100, 2) if self.start_balance else 0,
            "extensions_tp": sum(t.tp_extensions for t in trades),
            "trades_etendus": sum(1 for t in trades if t.tp_extensions > 0),
            "R_moyen_gagnant": round(sum(t.r_multiple for t in wins) / len(wins), 2) if wins else 0,
            "R_moyen_perdant": round(sum(t.r_multiple for t in losses) / len(losses), 2) if losses else 0,
            "motifs_de_rejet": dict(sorted(self.rejections.items(), key=lambda kv: -kv[1])[:6]),
        }


class Backtester:
    """Rejoue une strategie sur l'historique d'un instrument."""

    def __init__(self, config: Optional[BotConfig] = None,
                 registry: Optional[DataRegistry] = None,
                 autorise_vente: Optional[bool] = None) -> None:
        self.config = config or BotConfig.load()
        # La vente a decouvert suit le lieu d'execution vise. Au comptant
        # (« bitvavo ») elle est impossible ; sur compte de marge
        # (« bitvavo_margin ») elle l'est. Mesurer avec des ventes une
        # strategie qui tournera sans elles surestime le nombre de trades
        # ET fausse le taux de reussite.
        if autorise_vente is None:
            autorise_vente = self.config.engine.broker != "bitvavo"
        self.autorise_vente = bool(autorise_vente)
        # Meme verrou de devise que le moteur : un rejeu sur des prix en
        # dollars pour une configuration en euros donnerait des resultats
        # coherents entre eux mais sans rapport avec le marche ou les ordres
        # partiront. Le backtest doit mesurer ce que le robot vivra.
        self.registry = registry or registre_pour(self.config)
        self.universe = Universe()

    def run(self, symbol: str, bars: int = 1500, start_balance: float = 1000.0) -> BacktestResult:
        instrument = self.universe.get(symbol.upper())
        if instrument is None:
            raise ValueError(f"instrument inconnu : {symbol}")

        cfg = self.config
        entry_tf = cfg.strategy.entry_tf
        result = BacktestResult(symbol=instrument.symbol, start_balance=start_balance)

        base = self.registry.candles(instrument.symbol, instrument.asset_class, entry_tf, bars)
        if len(base) < 200:
            raise ValueError(f"historique insuffisant ({len(base)} bougies)")

        broker = PaperBroker(PaperConfig(start_balance=start_balance, currency=cfg.engine.currency))
        broker.connect()
        broker.register_instrument(instrument)

        strategy = Strategy(cfg.strategy, TradeManager(cfg.trade), macro=None)
        manager = TradeManager(cfg.trade)
        risk = RiskManager(cfg.risk)

        # Un jeu d'indicateurs par unite de temps, alimente au fil de l'eau.
        indicators = {tf: IndicatorSet(history=cfg.strategy.history) for tf in strategy.timeframes}
        higher = [tf for tf in strategy.timeframes if tf_seconds(tf) > tf_seconds(entry_tf)]
        lower = [tf for tf in strategy.timeframes if tf_seconds(tf) < tf_seconds(entry_tf)]
        buffers: dict[str, list[Candle]] = {tf: [] for tf in higher}
        last_bucket: dict[str, float] = {tf: -1.0 for tf in higher}

        # PRECHAUFFAGE DES UNITES SUPERIEURES
        #
        # Les regrouper depuis la serie d'entree les affame : 1439 bougies
        # H1 ne donnent que 60 bougies journalieres, et les indicateurs D1
        # ne sont prets qu'aux trois quarts du parcours. Resultat, le robot
        # reste aveugle sur la majeure partie de l'echantillon et le
        # backtest mesure surtout son propre temps de chauffe.
        #
        # Le robot en reel ne connait pas ce probleme : il telecharge
        # chaque unite separement. On fait donc pareil ici, en ne gardant
        # que l'historique ANTERIEUR au debut du parcours — sinon on
        # donnerait au robot des bougies qu'il ne pouvait pas connaitre.
        debut = base[0].ts
        for tf in higher:
            try:
                anterieures = [c for c in self.registry.candles(
                    instrument.symbol, instrument.asset_class, tf, cfg.strategy.history)
                    if c.ts < debut]
            except Exception as exc:  # noqa: BLE001
                logger.warning("prechauffage %s impossible sur %s : %s",
                               tf, instrument.symbol, str(exc)[:120])
                continue
            for c in anterieures:
                indicators[tf].update(c)
            if anterieures:
                last_bucket[tf] = int(anterieures[-1].ts // tf_seconds(tf)) * tf_seconds(tf)
                logger.info("%s %s : %d bougies de prechauffage",
                            instrument.symbol, tf, len(anterieures))

        warmup = 150
        for i, candle in enumerate(base):
            result.bars += 1

            # --- Alimentation des indicateurs (uniquement du cloture) ---
            indicators[entry_tf].update(candle)
            for tf in lower:
                indicators[tf].update(candle)      # approximation : meme bougie
            for tf in higher:
                secs = tf_seconds(tf)
                bucket = int(candle.ts // secs) * secs
                if last_bucket[tf] < 0:
                    last_bucket[tf] = bucket
                if bucket != last_bucket[tf] and buffers[tf]:
                    agg = resample(buffers[tf], entry_tf, tf)
                    for c in agg:
                        indicators[tf].update(c)
                    buffers[tf] = []
                    last_bucket[tf] = bucket
                buffers[tf].append(candle)

            if i < warmup:
                continue

            spread = spread_estime(instrument, candle.close)
            tick = Tick(candle.ts, candle.close - spread / 2, candle.close + spread / 2)
            atr = indicators[entry_tf].atr.value or 0.0
            broker.set_price(instrument.symbol, tick, atr)

            # --- Vie des positions : stop/objectif sur la bougie ---
            for trade in broker.process_candle(instrument.symbol, candle):
                result.trades.append(trade)
                risk.record_close(trade)

            acc = broker.account()
            risk.sync_account(acc.equity, acc.balance, cfg.engine.currency, ts=candle.ts)
            result.equity_curve.append((candle.ts, round(acc.equity, 2)))

            # --- Gestion dynamique des positions restantes ---
            chart = read_chart(indicators[entry_tf], instrument.round_step)
            for pos in list(broker.positions()):
                for action in manager.manage(pos, tick, indicators[entry_tf],
                                             chart=chart, digits=instrument.digits,
                                             now=candle.ts):
                    if action.type is ActionType.MODIFY_STOP:
                        broker.modify_position(pos.id, stop_loss=action.price)
                    elif action.type is ActionType.MODIFY_TARGET:
                        broker.modify_position(pos.id, take_profit=action.price)
                    elif action.type is ActionType.PARTIAL_CLOSE:
                        t = broker.close_position(pos.id, action.volume, action.reason)
                        if t:
                            result.trades.append(t)
                            risk.record_close(t)
                    elif action.type is ActionType.CLOSE:
                        t = broker.close_position(pos.id, None, action.reason)
                        if t:
                            result.trades.append(t)
                            risk.record_close(t)

            # --- Recherche d'entree ---
            if broker.positions():
                continue
            ok, why = risk.can_trade(broker.positions(), ts=candle.ts)
            if not ok:
                result.rejections[why.split("(")[0].strip()] = \
                    result.rejections.get(why.split("(")[0].strip(), 0) + 1
                continue

            ev = strategy.evaluate(instrument, indicators, tick, news=None,
                                   charts={entry_tf: chart}, now=candle.ts)
            result.evaluations += 1

            # LE REJEU DOIT REFUSER CE QUE LA PLATEFORME REFUSE.
            #
            # `PaperBroker` herite de `supports_short = True` et le rejeu ne
            # filtrait aucun sens : toutes les mesures comptaient donc des
            # ventes a decouvert. Sur un compte au comptant, qui ne sait
            # qu'acheter, la moitie de ces trades n'existerait pas — et le
            # taux de reussite mesure ne dit alors rien de ce que le robot
            # fera vraiment.
            if not self.autorise_vente and ev.side is Side.SELL:
                result.rejections["vente impossible au comptant"] = \
                    result.rejections.get("vente impossible au comptant", 0) + 1
                continue
            if not ev.valid:
                failed = ev.failed_gates()
                key = failed[0].name if failed else (ev.rejected_by or "score")
                result.rejections[key] = result.rejections.get(key, 0) + 1
                continue

            # LE SPREAD DOIT ETRE LE MEME PARTOUT DANS LE REJEU.
            #
            # Le filtre de la strategie utilise `spread_estime()` — relatif,
            # 5 points de base — tandis que le dimensionnement, faute de
            # recevoir le parametre, retombait sur `instrument.typical_spread`,
            # une valeur ABSOLUE heritee d'une autre echelle de prix. Deux
            # modeles de cout dans le meme rejeu : les quatre cryptos reglees
            # a la main etaient penalisees (BTCUSD portait 8,0 de spread) et
            # les quatre-vingt-une generees flattees (spread de zero).
            #
            # Le moteur reel passe `spread=ev.spread` (voir engine._execute) :
            # sans cette ligne, le rejeu ne mesurait pas la meme strategie que
            # celle qui tourne.
            sizing = risk.size_position(instrument, ev.side, ev.entry, ev.stop_loss,
                                        ev.take_profit, broker.positions(),
                                        self.universe.get, spread=tick.spread)
            if not sizing.allowed:
                key = "dimensionnement"
                result.rejections[key] = result.rejections.get(key, 0) + 1
                continue
            try:
                broker.open_position(instrument, ev.side, sizing.lots,
                                     ev.stop_loss, ev.take_profit,
                                     comment=f"{ev.setup} {ev.score:.2f}")
            except Exception as exc:  # noqa: BLE001
                result.rejections["ouverture_refusee"] = result.rejections.get("ouverture_refusee", 0) + 1
                logger.debug("ouverture refusee : %s", exc)

        # Cloture de ce qui reste ouvert a la fin de la periode
        for pos in list(broker.positions()):
            t = broker.close_position(pos.id, None, "fin de periode de test")
            if t:
                result.trades.append(t)

        result.end_balance = broker.account().balance
        return result

    def run_multi(self, symbols: list[str], bars: int = 1500,
                  start_balance: float = 1000.0) -> dict[str, BacktestResult]:
        """Backtest independant sur plusieurs instruments."""
        out: dict[str, BacktestResult] = {}
        for sym in symbols:
            try:
                out[sym] = self.run(sym, bars, start_balance)
            except Exception as exc:  # noqa: BLE001
                logger.warning("backtest %s impossible : %s", sym, str(exc)[:150])
        return out
