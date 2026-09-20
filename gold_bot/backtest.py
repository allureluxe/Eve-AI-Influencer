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


@dataclass
class Prepare:
    """Un instrument pret a defiler, et de quoi le piloter.

    `parcours` annonce l'horodatage de la prochaine bougie ; un `next()`
    la traite. `broker` et `risk` peuvent etre partages avec d'autres
    instruments — c'est toute la difference entre mesurer un robot et
    mesurer autant de comptes qu'il y a de cryptos.
    """
    resultat: BacktestResult
    parcours: object
    broker: PaperBroker
    risk: RiskManager
    instrument: Instrument
    bougies: list[Candle]


class Backtester:
    """Rejoue une strategie sur l'historique d'un instrument."""

    def __init__(self, config: Optional[BotConfig] = None,
                 registry: Optional[DataRegistry] = None,
                 autorise_vente: Optional[bool] = None,
                 entree_limite: bool = False) -> None:
        self.config = config or BotConfig.load()
        # La vente a decouvert suit le lieu d'execution vise. Au comptant
        # (« bitvavo ») elle est impossible ; sur compte de marge
        # (« bitvavo_margin ») elle l'est. Mesurer avec des ventes une
        # strategie qui tournera sans elles surestime le nombre de trades
        # ET fausse le taux de reussite.
        if autorise_vente is None:
            autorise_vente = self.config.engine.broker != "bitvavo"
        self.autorise_vente = bool(autorise_vente)

        # ENTREES EN ORDRE LIMITE : moins de frais, mais des trades rates.
        #
        # Un ordre post-only pose au meilleur acheteur paie 0,15 % au lieu
        # de 0,25 %. En echange il n'est servi QUE si le prix revient le
        # toucher. Modeliser la baisse de frais sans modeliser les non-
        # executions donnerait un resultat flatteur et faux — c'est
        # exactement le genre d'hypothese qui fait armer une strategie que
        # personne n'a testee.
        self.entree_limite = bool(entree_limite)
        self._rates = 0
        # Meme verrou de devise que le moteur : un rejeu sur des prix en
        # dollars pour une configuration en euros donnerait des resultats
        # coherents entre eux mais sans rapport avec le marche ou les ordres
        # partiront. Le backtest doit mesurer ce que le robot vivra.
        self.registry = registry or registre_pour(self.config)
        self.universe = Universe()

    def run(self, symbol: str, bars: int = 1500, start_balance: float = 1000.0,
            series: Optional[dict[str, list[Candle]]] = None) -> BacktestResult:
        """Rejoue la strategie sur un instrument, sur un compte a lui seul.

        `series` : si fourni, `{unite: bougies}` remplace le telechargement
        par le registre. Sert aux rejeux sur une fenetre longue (6 mois)
        recuperee a part, que les fournisseurs du registre ne servent pas.
        La serie d'entree doit couvrir la periode ; les unites superieures
        doivent inclure de l'historique ANTERIEUR pour le prechauffage.

        ATTENTION A CE QUE CETTE MESURE DIT, ET A CE QU'ELLE NE DIT PAS.
        Chaque appel ouvre un compte NEUF, dote de `start_balance` entier
        et de tout le budget de risque. Mesurer vingt instruments ainsi,
        puis additionner les profits, revient a supposer vingt comptes
        separes — pas un robot qui les arbitre sur un seul. Pour cela,
        voir `backtest_portefeuille.BacktestPortefeuille`.
        """
        prep = self.preparer(symbol, bars, start_balance, series)
        for _ in prep.parcours:
            pass
        for pos in list(prep.broker.positions()):
            t = prep.broker.close_position(pos.id, None, "fin de periode de test")
            if t:
                prep.resultat.trades.append(t)
        prep.resultat.end_balance = prep.broker.account().balance
        return prep.resultat

    def preparer(self, symbol: str, bars: int, start_balance: float,
                 series: Optional[dict[str, list[Candle]]] = None,
                 broker: Optional[PaperBroker] = None,
                 risk: Optional[RiskManager] = None,
                 decalage: int = 0) -> "Prepare":
        """Prepare le rejeu d'un instrument et rend `(resultat, parcours)`.

        `parcours` est un generateur qui rend la main AVANT de traiter
        chaque bougie, en annoncant son horodatage. Un `next()` traite la
        bougie annoncee et annonce la suivante.

        C'est ce qui permet a deux pilotes tres differents — un rejeu par
        instrument et un rejeu de portefeuille — d'executer exactement le
        MEME corps de bougie. Dupliquer ce corps serait la faute que ce
        depot a deja payee plusieurs fois : deux endroits qui decident de
        la meme chose finissent toujours par diverger, sans test rouge.

        `broker` et `risk` fournis : le compte est PARTAGE avec d'autres
        instruments, et c'est a l'appelant de le cloturer.
        """
        instrument = self.universe.get(symbol.upper())
        if instrument is None:
            raise ValueError(f"instrument inconnu : {symbol}")

        cfg = self.config
        entry_tf = cfg.strategy.entry_tf
        result = BacktestResult(symbol=instrument.symbol, start_balance=start_balance)

        if series and entry_tf in series:
            base = list(series[entry_tf])
        else:
            # DECALAGE : reculer dans le temps pour mesurer HORS
            # ECHANTILLON.
            #
            # Un reglage choisi sur une periode y parait toujours bon --
            # c'est la definition du sur-ajustement, et ce depot l'a paye
            # en septembre : cinq configurations de pyramidage
            # amelioraient TOUTES la periode d'apprentissage et
            # degradaient TOUTES la suivante.
            #
            # `decalage` coupe les N dernieres bougies : on mesure alors
            # sur une periode que le reglage n'a jamais vue. Sans cet
            # outil, le rejeu de portefeuille ne pouvait produire qu'une
            # seule periode -- donc aucune verification possible.
            base = self.registry.candles(
                instrument.symbol, instrument.asset_class, entry_tf,
                bars + max(0, decalage))
            if decalage > 0:
                base = base[:-decalage] if decalage < len(base) else []
        if len(base) < 200:
            raise ValueError(f"historique insuffisant ({len(base)} bougies)")

        # La commission du rejeu suit celle de la configuration (Bitvavo
        # taker = 0,25 % par cote). Sans ce passage, PaperConfig retombait
        # sur son defaut 0,02 %, soit douze fois moins que le tarif reel.
        if broker is None:
            broker = PaperBroker(PaperConfig(
                start_balance=start_balance, currency=cfg.engine.currency,
                commission_pct=cfg.risk.commission_pct))
            broker.connect()
        broker.register_instrument(instrument)

        strategy = Strategy(cfg.strategy, TradeManager(cfg.trade), macro=None)
        manager = TradeManager(cfg.trade)
        if risk is None:
            risk = RiskManager(cfg.risk)

        # « MES positions » n'est PAS « toutes les positions ».
        #
        # Ici les deux se confondent : un rejeu par instrument n'a qu'un
        # symbole dans le courtier, donc filtrer ne change aucun chiffre
        # (verrouille par un test). Mais la distinction est reelle, et
        # elle devient vitale des que plusieurs symboles partagent un
        # compte — c'est le cas du robot, et celui de
        # `backtest_portefeuille`.
        #
        # Sans elle, la gestion dynamique appliquerait la cotation et les
        # indicateurs de CE symbole aux positions des AUTRES : des stops
        # deplaces sur un prix qui n'est pas le leur, en silence.
        #
        # Deux appels restent volontairement GLOBAUX, parce qu'ils portent
        # sur le compte et non sur l'instrument : `risk.can_trade` et
        # `risk.size_position`, qui lisent le budget de risque partage.
        def miennes():
            return [p for p in broker.positions()
                    if p.symbol == instrument.symbol]

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
                if series and tf in series:
                    source = list(series[tf])
                else:
                    source = self.registry.candles(
                        instrument.symbol, instrument.asset_class, tf, cfg.strategy.history)
                anterieures = [c for c in source if c.ts < debut]
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

        def parcours():
            for i, candle in enumerate(base):
                # ON REND LA MAIN AVANT DE TRAITER, PAS APRES.
                #
                # Le pilote a besoin de connaitre l'horodatage de la
                # prochaine bougie pour decider quel instrument avance.
                # S'il ne l'apprenait qu'une fois la bougie traitee, un
                # portefeuille traiterait les symboles dans le desordre
                # chronologique — et un robot qui voit l'avenir d'un
                # marche pendant qu'il decide sur un autre mesure
                # n'importe quoi.
                yield candle.ts
                _bougie(i, candle)

        def _bougie(i, candle):
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
                return

            spread = spread_estime(instrument, candle.close)
            tick = Tick(candle.ts, candle.close - spread / 2, candle.close + spread / 2)
            atr = indicators[entry_tf].atr.value or 0.0
            broker.set_price(instrument.symbol, tick, atr)

            # --- Vie des positions : stop/objectif sur la bougie ---
            for trade in broker.process_candle(instrument.symbol, candle):
                result.trades.append(trade)
                risk.record_close(trade)
                strategy.noter_sortie_donchian(trade.symbol, trade.profit > 0)

            acc = broker.account()
            risk.sync_account(acc.equity, acc.balance, cfg.engine.currency, ts=candle.ts)
            result.equity_curve.append((candle.ts, round(acc.equity, 2)))

            # --- Gestion dynamique des positions restantes ---
            chart = read_chart(indicators[entry_tf], instrument.round_step)
            ouvertes = miennes()
            for pos in ouvertes:
                for action in manager.manage(pos, tick, indicators[entry_tf],
                                             chart=chart, digits=instrument.digits,
                                             now=candle.ts, etages=ouvertes):
                    if action.type is ActionType.MODIFY_STOP:
                        broker.modify_position(pos.id, stop_loss=action.price)
                    elif action.type is ActionType.MODIFY_TARGET:
                        broker.modify_position(pos.id, take_profit=action.price)
                    elif action.type is ActionType.PARTIAL_CLOSE:
                        t = broker.close_position(pos.id, action.volume, action.reason)
                        if t:
                            result.trades.append(t)
                            risk.record_close(t)
                            strategy.noter_sortie_donchian(t.symbol, t.profit > 0)
                    elif action.type is ActionType.CLOSE:
                        t = broker.close_position(pos.id, None, action.reason)
                        if t:
                            result.trades.append(t)
                            risk.record_close(t)
                            strategy.noter_sortie_donchian(t.symbol, t.profit > 0)

            # --- Sortie reversion : retour dans la bande sous la SMA courante ---
            #
            # En famille « reversion » il n'y a pas d'objectif fixe : on
            # sort des que le prix repasse a moins de `reversion_sortie_atr`
            # ATR sous la SMA COURANTE (reevaluee ici chaque bougie). Le
            # stop ATR reste gere par `process_candle` : une reversion qui
            # ne revient jamais sort au stop.
            if cfg.strategy.famille == "reversion" and miennes():
                n_ma = int(cfg.strategy.reversion_ma_periode)
                closes = [c.close for c in indicators[entry_tf].candles]
                if len(closes) >= n_ma and atr > 0:
                    sma_now = sum(closes[-n_ma:]) / n_ma
                    if (sma_now - candle.close) <= cfg.strategy.reversion_sortie_atr * atr:
                        for pos in miennes():
                            t = broker.close_position(pos.id, None, "reversion : retour a la MA")
                            if t:
                                result.trades.append(t)
                                risk.record_close(t)
                            strategy.noter_sortie_donchian(t.symbol, t.profit > 0)

            # --- Recherche d'entree ---
            #
            # LE REJEU DOIT POUVOIR EMPILER, SINON IL NE MESURE PAS LA
            # PYRAMIDE. Cette ligne tenait UNE position a la fois : armer
            # `pyramide_max` sans la lever aurait donne un resultat
            # identique a la configuration de base, et on en aurait conclu
            # que le renforcement « ne change rien » alors qu'il n'avait
            # simplement jamais eu lieu.
            #
            # Hors pyramide le comportement est inchange : une seule
            # position, comme toutes les mesures precedentes — celles du
            # 30 aout restent donc comparables.
            ouvertes = miennes()
            if ouvertes and cfg.risk.pyramide_max <= 0:
                return
            # Prix et ATR transmis : sans eux la regle d'espacement Turtle
            # (« +1 unite tous les 0,5 N ») ne peut pas s'appliquer, et deux
            # etages s'ouvriraient sur la meme bougie.
            _atr_now = indicators[entry_tf].atr.value or 0.0
            if ouvertes and not risk.peut_renforcer(
                    ouvertes, ouvertes[0].side, prix=candle.close, atr=_atr_now)[0]:
                return
            # LE MEME PIEGE QUE POUR LA PYRAMIDE, ET IL A DEJA MENTI UNE FOIS.
            #
            # Le delai de carence vit dans `check_exposure`, que le rejeu
            # n'appelle pas : il a sa propre porte d'entree. Sans cette
            # ligne, la premiere mesure a rendu des chiffres IDENTIQUES au
            # temoin — au centieme et par paire — et on aurait conclu que la
            # carence ne sert a rien alors qu'elle ne s'etait jamais
            # declenchee. Elle est ici sur l'horloge des BOUGIES, pas celle
            # du systeme, sinon elle ne se declencherait toujours pas.
            if not ouvertes and risk.carence_restante(instrument.symbol,
                                                      now=candle.ts) > 0:
                result.rejections["carence apres sortie"] = \
                    result.rejections.get("carence apres sortie", 0) + 1
                return
            ok, why = risk.can_trade(broker.positions(), ts=candle.ts)
            if not ok:
                result.rejections[why.split("(")[0].strip()] = \
                    result.rejections.get(why.split("(")[0].strip(), 0) + 1
                return

            # LA LIMITE PAR FAMILLE DE CRYPTOS, et pourquoi elle est ici.
            #
            # TROISIEME FOIS QUE CE PIEGE SE REFERME. L'avertissement est
            # ecrit dix lignes plus haut pour la carence : `check_exposure`
            # n'est appele QUE par le moteur reel, jamais par le rejeu.
            # Quelqu'un a rapatrie la carence et laisse la correlation
            # derriere.
            #
            # Resultat, mesure le 20 septembre : faire varier
            # `max_per_correlation_group` de 99 a 1 rendait QUATRE FOIS
            # le meme chiffre, au centime. On aurait conclu « ce reglage
            # ne change rien » alors qu'il ne s'executait pas.
            #
            # Le rejeu n'a qu'UN symbole dans son courtier, donc cette
            # porte ne mord que dans le rejeu de PORTEFEUILLE -- ou elle
            # est justement la seule a pouvoir repondre.
            ok, why = risk.check_exposure(
                instrument, Side.BUY, broker.positions(), self.universe.get,
                now=candle.ts)
            if not ok:
                cle = why.split("'")[0].strip() or "exposition"
                result.rejections[cle] = result.rejections.get(cle, 0) + 1
                return

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
                return
            if not ev.valid:
                failed = ev.failed_gates()
                key = failed[0].name if failed else (ev.rejected_by or "score")
                result.rejections[key] = result.rejections.get(key, 0) + 1
                return

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
                return
            prix_entree = None
            if self.entree_limite:
                # L'ordre est pose au meilleur acheteur, soit le prix moins
                # un demi-spread. Il n'est servi que si la bougie SUIVANTE
                # redescend le toucher. Sinon le prix est parti sans nous :
                # le trade n'a pas lieu, et c'est le vrai cout de la
                # methode.
                limite = candle.close - spread / 2.0
                suivante = base[i + 1] if i + 1 < len(base) else None
                if suivante is None or suivante.low > limite:
                    result.rejections["limite non servie"] = \
                        result.rejections.get("limite non servie", 0) + 1
                    self._rates += 1
                    return
                prix_entree = limite

            try:
                broker.open_position(instrument, ev.side, sizing.lots,
                                     ev.stop_loss, ev.take_profit,
                                     comment=f"{ev.setup} {ev.score:.2f}")
                if prix_entree is not None:
                    # Servi au prix pose, et au tarif MAKER.
                    for pos in broker.positions():
                        if pos.symbol == instrument.symbol:
                            pos.entry_price = prix_entree
            except Exception as exc:  # noqa: BLE001
                result.rejections["ouverture_refusee"] = result.rejections.get("ouverture_refusee", 0) + 1
                logger.debug("ouverture refusee : %s", exc)

        # La cloture de fin de periode appartient au PILOTE, pas ici : sur
        # un compte partage, elle ne doit avoir lieu qu'une fois, quand
        # tous les instruments ont fini de defiler.
        return Prepare(resultat=result, parcours=parcours(), broker=broker,
                       risk=risk, instrument=instrument, bougies=base)

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
