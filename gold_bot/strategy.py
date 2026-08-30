"""Moteur de decision.

Deux etages, volontairement separes :

  1. LES FILTRES ELIMINATOIRES (`gates`). Une liste de conditions
     obligatoires. Il suffit qu'une seule echoue pour que l'instrument soit
     ecarte — le robot passe alors au suivant. Pas de compensation possible :
     un signal magnifique sur un spread anormal reste un mauvais trade.

  2. LE SCORE DE CONFLUENCE. Une fois les filtres passes, on additionne des
     lectures independantes (tendance multi-unites, momentum, bougies,
     figures, divergences, zones, volume, macro, news). Le score doit
     depasser un seuil pour declencher.

Trois familles de configurations sont reconnues :

  - SUIVI DE TENDANCE SUR REPLI : le scenario le plus robuste en court terme.
  - CASSURE (breakout) : sortie de compression ou de canal, avec volume.
  - RETOURNEMENT SUR NIVEAU : uniquement en regime de retour a la moyenne,
    avec divergence et bougie de rejet.

Aucune position n'est proposee sans stop-loss et take-profit calcules.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from . import candles as K
from .chart import ChartRead, read_chart
from .core import Candle, Side, Tick
from .apprentissage import PoidsAdaptatifs
from .microstructure import balayage_de_liquidite, desequilibre_carnet
from .indicators import IndicatorSet
from .macro import MacroBias, MacroEngine
from .news import NewsWindow
from .trade_manager import TradeManager, TradeManagerConfig
from .universe import Instrument

logger = logging.getLogger(__name__)


# ==========================================================================
# Structures de sortie
# ==========================================================================
@dataclass(slots=True)
class Gate:
    """Resultat d'un filtre eliminatoire."""

    name: str
    passed: bool
    detail: str = ""

    def __str__(self) -> str:  # pragma: no cover
        return f"{'OK ' if self.passed else 'NON'} {self.name}: {self.detail}"


@dataclass(slots=True)
class Confirmation:
    """Une confirmation independante, en mode quorum."""

    name: str
    passed: bool
    detail: str = ""
    # Une confirmation qu'on ne PEUT PAS evaluer n'est pas une confirmation
    # ratee. Le carnet d'ordres n'existe pas dans un rejeu historique : l'y
    # compter comme echouee retire une confirmation atteignable a chaque
    # bougie, et rend le backtest structurellement plus severe que le reel.
    # Elle sort donc du numerateur ET du denominateur.
    applicable: bool = True

    def __str__(self) -> str:  # pragma: no cover
        if not self.applicable:
            return f"n/a {self.name}" + (f" ({self.detail})" if self.detail else "")
        return f"{'oui' if self.passed else 'non'} {self.name}" + (f" ({self.detail})" if self.detail else "")


@dataclass(slots=True)
class ScoreComponent:
    """Une brique du score de confluence."""

    name: str
    value: float          # contribution signee, deja ponderee
    detail: str = ""


@dataclass(slots=True)
class Evaluation:
    """Verdict complet pour un instrument."""

    symbol: str
    asset_class: str
    side: Optional[Side] = None
    setup: str = ""
    score: float = 0.0
    threshold: float = 0.0
    mode: str = "confluence"
    timeframe: str = ""
    confirmations: list[Confirmation] = field(default_factory=list)
    confirmed: int = 0
    required: int = 0
    gates: list[Gate] = field(default_factory=list)
    components: list[ScoreComponent] = field(default_factory=list)
    entry: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    atr: float = 0.0
    rr: float = 0.0
    spread: float = 0.0
    priority_score: float = 0.0
    rejected_by: str = ""
    ts: float = field(default_factory=time.time)

    @property
    def valid(self) -> bool:
        """Le trade est-il autorise ?

        En confluence : tous les filtres passes ET le score au-dessus du seuil.
        En quorum     : tous les filtres passes ET assez de confirmations.
        """
        if self.side is None or not all(g.passed for g in self.gates):
            return False
        if self.mode == "quorum":
            return self.confirmed >= self.required
        return self.score >= self.threshold

    def failed_gates(self) -> list[Gate]:
        return [g for g in self.gates if not g.passed]

    def explain(self) -> str:
        """Explication lisible de la decision (journal et alertes)."""
        head = f"{self.symbol} "
        if self.valid:
            if self.mode == "quorum":
                noms = ", ".join(c.name for c in self.confirmations if c.passed)
                head += (f"{self.side.value} [{self.setup} {self.timeframe}] "
                         f"{self.confirmed}/{self.required} "
                         f"confirmations ({noms}) | entree {self.entry} SL {self.stop_loss} "
                         f"TP {self.take_profit} (RR {self.rr:.2f})")
            else:
                head += (f"{self.side.value} [{self.setup}] score {self.score:.2f}/"
                         f"{self.threshold:.2f} | entree {self.entry} SL {self.stop_loss} "
                         f"TP {self.take_profit} (RR {self.rr:.2f})")
        else:
            failed = self.failed_gates()
            if failed:
                head += f"ecarte -> {failed[0].name} : {failed[0].detail}"
            elif self.side is None:
                head += f"ecarte -> aucun scenario ({self.rejected_by or 'pas de configuration'})"
            elif self.mode == "quorum":
                manquantes = ", ".join(c.name for c in self.confirmations if not c.passed)
                head += (f"ecarte -> {self.confirmed}/{self.required} confirmations "
                         f"(manque : {manquantes[:70]})")
            else:
                head += f"ecarte -> score {self.score:.2f} < seuil {self.threshold:.2f}"
        return head

    def detail_lines(self) -> list[str]:
        lines = [f"  {g}" for g in self.gates]
        lines += [f"  {c}" for c in self.confirmations]
        lines += [f"  + {c.name} {c.value:+.3f} ({c.detail})" for c in self.components if abs(c.value) > 1e-6]
        return lines


# ==========================================================================
# Configuration
# ==========================================================================
@dataclass(slots=True)
class StrategyConfig:
    """Parametres du moteur de decision."""

    # --- Unites de temps ---
    entry_tf: str = "M5"          # unite de declenchement
    trigger_tf: str = "M1"        # affinage de l'entree
    context_tf: str = "M15"       # contexte immediat
    bias_tf: str = "H1"           # biais de fond

    # --- Choix automatique de l'unite de temps ---
    #
    # Chaque instrument a son propre rapport spread / mouvement. Sur EURUSD
    # le spread vaut 17 % d'un stop en M1 ; sur AUDUSD il en vaut 28 %, et
    # aucun elargissement raisonnable du stop n'y change rien. Plutot que
    # d'ecarter ces instruments, le robot descend d'un cran : en M5 le meme
    # AUDUSD retombe a 14 %.
    #
    # Le robot retient donc, pour chaque instrument, l'unite de temps LA PLUS
    # FINE ou le cout reste acceptable — c'est-a-dire la cadence la plus
    # rapide qu'il peut se permettre sur cet instrument.
    adaptive_timeframe: bool = False
    timeframe_ladder: list[str] = field(default_factory=lambda: ["M1", "M5", "M15"])
    max_cost_ratio_pct: float = 15.0

    # --- Mode de decision ---
    #
    # "confluence" : toutes les lectures sont ponderees et doivent produire
    #                un score eleve. Peu de trades, forte conviction.
    # "quorum"     : il suffit qu'un nombre minimal de confirmations
    #                INDEPENDANTES soient d'accord (les bougies plus deux ou
    #                trois indicateurs). Beaucoup plus de trades, chacun
    #                moins argumente. C'est le mode du trading rapide.
    mode: str = "confluence"
    min_confirmations: int = 3          # quorum : nombre de confirmations exigees
    require_candle_confirmation: bool = True   # la lecture des bougies est obligatoire
    confirmation_margin: int = 1        # avance minimale sur le sens oppose

    # --- Seuil de validation ---
    min_score: float = 0.55       # score de confluence minimal
    min_score_counter_trend: float = 0.75   # exigence relevee a contre-tendance

    # --- Filtres eliminatoires ---
    max_spread_atr_ratio: float = 0.22    # spread max en fraction d'ATR
    min_atr_percentile: float = 0.20      # volatilite trop faible = marche mort
    max_atr_percentile: float = 0.95      # volatilite extreme = chaos
    min_atr_price_ratio: float = 0.00025  # ATR minimal rapporte au prix
    min_adx: float = 18.0                 # tendance exploitable
    min_headroom_atr: float = 1.2         # marge avant le prochain obstacle
    min_rr: float = 1.5                   # ratio rendement/risque minimal
    require_trigger: bool = True          # un declencheur price action est obligatoire
    require_mtf_alignment: bool = True    # accord entre unites de temps
    allow_counter_trend: bool = True      # autoriser les retournements en range
    macro_veto_threshold: float = 0.55

    # --- Poids du score ---
    w_trend: float = 0.22
    w_momentum: float = 0.16
    w_candles: float = 0.16
    w_chart: float = 0.10
    w_divergence: float = 0.08
    w_zones: float = 0.08
    w_volume: float = 0.06
    w_macro: float = 0.08
    w_news: float = 0.06

    history: int = 300


# ==========================================================================
# Moteur
# ==========================================================================
class Strategy:
    """Analyse un instrument et decide s'il y a un trade a prendre."""

    def __init__(
        self,
        config: Optional[StrategyConfig] = None,
        trade_manager: Optional[TradeManager] = None,
        macro: Optional[MacroEngine] = None,
        poids: Optional[PoidsAdaptatifs] = None,
    ) -> None:
        self.config = config or StrategyConfig()
        self.trade_manager = trade_manager or TradeManager(TradeManagerConfig())
        self.macro = macro
        # Ponderation apprise sur les trades reellement fermes. Neutre par
        # defaut : sans historique, elle ne change rien.
        self.poids = poids or PoidsAdaptatifs()

    # ---------------------------------------------------------------
    ORDRE_TF = {"M1": 1, "M3": 3, "M5": 5, "M15": 15,
                "M30": 30, "H1": 60, "H4": 240, "D1": 1440}

    @property
    def timeframes(self) -> list[str]:
        cfg = self.config
        besoin = {cfg.trigger_tf, cfg.entry_tf, cfg.context_tf, cfg.bias_tf}
        if cfg.adaptive_timeframe:
            besoin |= set(cfg.timeframe_ladder)
        return sorted(besoin, key=lambda tf: self.ORDRE_TF[tf])

    def pick_timeframe(
        self,
        instrument: Instrument,
        indicators: dict[str, IndicatorSet],
        spread: float,
    ) -> tuple[str, str]:
        """Unite de temps la plus fine ou le cout d'execution reste tenable.

        Retourne (unite retenue, explication). Si aucune ne convient, on
        rend la plus lente de l'echelle : l'evaluation la refusera ensuite
        proprement, avec un motif lisible.
        """
        cfg = self.config
        if not cfg.adaptive_timeframe or spread <= 0:
            return cfg.entry_tf, "unite de temps fixe"

        essais: list[str] = []
        for tf in sorted(cfg.timeframe_ladder, key=lambda t: self.ORDRE_TF[t]):
            ind = indicators.get(tf)
            if ind is None or not ind.ready or not ind.atr.value:
                continue
            ratio = self.trade_manager.cost_ratio(ind.atr.value, spread)
            essais.append(f"{tf} {ratio:.0f}%")
            if ratio <= cfg.max_cost_ratio_pct + 1e-9:
                return tf, f"cout {ratio:.0f} % du risque ({' -> '.join(essais)})"

        lente = max(cfg.timeframe_ladder, key=lambda t: self.ORDRE_TF[t])
        return lente, f"aucune unite sous le seuil ({' -> '.join(essais) or 'donnees absentes'})"

    def build_indicators(self, candles_by_tf: dict[str, list[Candle]]) -> dict[str, IndicatorSet]:
        """Alimente un jeu d'indicateurs par unite de temps."""
        out: dict[str, IndicatorSet] = {}
        for tf, candles in candles_by_tf.items():
            ind = IndicatorSet(history=self.config.history)
            for c in candles:
                ind.update(c)
            out[tf] = ind
        return out

    # ---------------------------------------------------------------
    def evaluate(
        self,
        instrument: Instrument,
        indicators: dict[str, IndicatorSet],
        tick: Tick,
        news: Optional[NewsWindow] = None,
        charts: Optional[dict[str, ChartRead]] = None,
        score_bonus: float = 0.0,
        now: Optional[float] = None,
        entry_tf: Optional[str] = None,
    ) -> Evaluation:
        """Evalue un instrument et retourne le verdict complet."""
        cfg = self.config
        now = now or time.time()
        ev = Evaluation(symbol=instrument.symbol, asset_class=instrument.asset_class,
                        ts=now, mode=cfg.mode)

        entry_tf = entry_tf or cfg.entry_tf
        ev.timeframe = entry_tf
        entry_ind = indicators.get(entry_tf)
        ctx_ind = indicators.get(cfg.context_tf)
        bias_ind = indicators.get(cfg.bias_tf)

        # ---------- Filtre 1 : donnees suffisantes ----------
        missing = [tf for tf in (entry_tf, cfg.context_tf, cfg.bias_tf)
                   if tf not in indicators or not indicators[tf].ready]
        ev.gates.append(Gate("donnees", not missing,
                             "indicateurs prets" if not missing
                             else f"historique insuffisant sur {', '.join(missing)}"))
        if missing:
            return ev

        price = round(tick.mid, instrument.digits)
        atr = entry_ind.atr.value or 0.0
        ev.atr, ev.entry, ev.spread = atr, price, tick.spread

        chart = (charts or {}).get(entry_tf) or read_chart(entry_ind, instrument.round_step)

        # ---------- Filtre 2 : marche ouvert ----------
        market_open = instrument.is_open(now)
        ev.gates.append(Gate("marche_ouvert", market_open,
                             "seance active" if market_open else "hors seance de cotation"))
        if not market_open:
            return ev

        # ---------- Filtre 3 : spread ----------
        spread_ok = tick.spread <= instrument.max_spread and (atr <= 0 or tick.spread <= cfg.max_spread_atr_ratio * atr)
        ev.gates.append(Gate(
            "spread", spread_ok,
            f"{tick.spread:.5f} (max {instrument.max_spread:.5f}, "
            f"{tick.spread / atr * 100 if atr else 0:.0f}% de l'ATR)"))
        if not spread_ok:
            return ev

        # ---------- Filtre 4 : volatilite exploitable ----------
        pct = entry_ind.atr_percentile()
        atr_ratio = atr / price if price else 0.0
        vol_ok = (cfg.min_atr_percentile <= pct <= cfg.max_atr_percentile
                  and atr_ratio >= cfg.min_atr_price_ratio)
        # Le motif doit NOMMER le critere qui refuse. Les deux se lisent sur
        # des echelles differentes — un percentile est relatif a l'histoire
        # de l'instrument, un ratio ATR/prix est absolu — et afficher les
        # deux valeurs sans dire laquelle mord laisse chercher du mauvais
        # cote. Le 30 aout, sept cryptos etaient refusees sur le plancher
        # ABSOLU (0,40 % d'ATR pour 0,75 % exiges) pendant que le journal
        # mettait le percentile en avant.
        if not vol_ok:
            if atr_ratio < cfg.min_atr_price_ratio:
                pourquoi = (f"marche trop calme : ATR {atr_ratio * 100:.3f}% du prix "
                            f"pour {cfg.min_atr_price_ratio * 100:.3f}% exiges "
                            f"(sous ce seuil les frais depassent le plafond de cout)")
            elif pct < cfg.min_atr_percentile:
                pourquoi = (f"volatilite au plus bas de son historique : "
                            f"percentile {pct:.2f} pour {cfg.min_atr_percentile:.2f} exiges")
            else:
                pourquoi = (f"volatilite extreme : percentile {pct:.2f} "
                            f"au-dessus de {cfg.max_atr_percentile:.2f}")
        else:
            pourquoi = (f"ATR {atr:.5f} ({atr_ratio * 100:.3f}% du prix), "
                        f"percentile {pct:.2f}")
        ev.gates.append(Gate("volatilite", vol_ok, pourquoi))
        if not vol_ok:
            return ev

        # ---------- Filtre 5 : calendrier economique ----------
        news_ok = not (news and news.blocked)
        ev.gates.append(Gate("calendrier", news_ok,
                             news.reason if (news and news.reason) else "aucune annonce bloquante"))
        if not news_ok:
            return ev

        # ---------- Branche rapide : mode quorum ----------
        if cfg.mode == "quorum":
            return self._finish_quorum(ev, instrument, entry_ind, ctx_ind, bias_ind,
                                       chart, tick, price, atr, score_bonus)

        # ---------- Determination du scenario ----------
        setup = self._detect_setup(entry_ind, ctx_ind, bias_ind, chart, news)
        if setup is None:
            ev.rejected_by = "aucune configuration reconnue"
            ev.gates.append(Gate("configuration", False, ev.rejected_by))
            return ev
        side, setup_name, setup_detail = setup
        ev.side, ev.setup = side, setup_name
        ev.gates.append(Gate("configuration", True, f"{setup_name} : {setup_detail}"))

        counter_trend = setup_name.startswith("retournement")

        # ---------- Filtre 6 : regime de marche ----------
        adx = entry_ind.adx.value or 0.0
        regime = entry_ind.hurst.regime
        if counter_trend:
            regime_ok = regime in ("mean_revert", "random") or adx < 25
            detail = f"regime {regime}, ADX {adx:.0f} : compatible avec un retournement"
        elif adx >= 25:
            # ADX mesure directement la force de tendance ; l'exposant de
            # Hurst est une statistique secondaire, bruitee sur une fenetre
            # courte. Quand la tendance est franche, elle ne peut pas etre
            # invalidee par une lecture de regime approximative.
            regime_ok = True
            detail = f"ADX {adx:.0f} : tendance confirmee (regime {regime} non bloquant)"
        else:
            regime_ok = adx >= cfg.min_adx and regime != "mean_revert"
            detail = f"regime {regime}, ADX {adx:.0f} (min {cfg.min_adx:.0f})"
        ev.gates.append(Gate("regime", regime_ok, detail))
        if not regime_ok:
            return ev

        # ---------- Filtre 7 : alignement multi-unites ----------
        if cfg.require_mtf_alignment and not counter_trend:
            wanted = "bullish" if side is Side.BUY else "bearish"
            ctx_bias, bias_bias = ctx_ind.trend_bias(), bias_ind.trend_bias()
            aligned = ctx_bias != _opposite(wanted) and bias_bias != _opposite(wanted)
            ev.gates.append(Gate(
                "alignement_mtf", aligned,
                f"{cfg.context_tf}={ctx_bias}, {cfg.bias_tf}={bias_bias} pour un {wanted}"))
            if not aligned:
                return ev
        else:
            ev.gates.append(Gate("alignement_mtf", True, "non requis pour ce scenario"))

        # ---------- Filtre 8 : marge avant le prochain obstacle ----------
        room = chart.headroom(price, side)
        room_ok = room is None or atr <= 0 or room >= cfg.min_headroom_atr * atr
        ev.gates.append(Gate(
            "marge_structurelle", room_ok,
            "champ libre" if room is None else
            f"{room:.5f} avant le prochain niveau ({room / atr if atr else 0:.2f} ATR, "
            f"min {cfg.min_headroom_atr:.2f})"))
        if not room_ok:
            return ev

        # ---------- Niveaux de sortie ----------
        structure_stop = self._structure_stop(side, entry_ind, atr)
        sl, tp = self.trade_manager.initial_levels(
            side, price, atr, spread=tick.spread,
            structure_stop=structure_stop, digits=instrument.digits)
        ev.stop_loss, ev.take_profit = sl, tp
        risk = abs(price - sl)
        ev.rr = abs(tp - price) / risk if risk > 0 else 0.0

        # ---------- Filtre 9 : ratio rendement/risque ----------
        rr_ok = ev.rr >= cfg.min_rr
        ev.gates.append(Gate("ratio_rr", rr_ok, f"{ev.rr:.2f} (min {cfg.min_rr:.2f})"))
        if not rr_ok:
            return ev

        # Si un obstacle se trouve avant le TP, on verifie que le RR tient
        # jusqu'a cet obstacle : viser au travers d'une resistance majeure
        # est la premiere cause de TP jamais atteints.
        if room is not None and risk > 0:
            reachable_rr = room / risk
            reachable_ok = reachable_rr >= cfg.min_rr
            ev.gates.append(Gate(
                "objectif_atteignable", reachable_ok,
                f"{reachable_rr:.2f}R disponible jusqu'au prochain niveau (min {cfg.min_rr:.2f})"))
            if not reachable_ok:
                return ev

        # ---------- Filtre 10 : veto macro ----------
        macro_bias: Optional[MacroBias] = None
        if self.macro is not None:
            veto = self.macro.veto(instrument.symbol, instrument.asset_class,
                                   side is Side.BUY, cfg.macro_veto_threshold)
            ev.gates.append(Gate("macro", veto is None, veto or "pas d'opposition fondamentale"))
            if veto:
                return ev
            macro_bias = self.macro.bias(instrument.symbol, instrument.asset_class)
        else:
            ev.gates.append(Gate("macro", True, "moteur macro desactive"))

        # ---------- Score de confluence ----------
        ev.components = self._score_components(
            side, entry_ind, ctx_ind, bias_ind, chart, macro_bias, news, setup_name)
        ev.score = round(sum(c.value for c in ev.components), 4)

        base_threshold = cfg.min_score_counter_trend if counter_trend else cfg.min_score
        ev.threshold = round(base_threshold + score_bonus, 4)

        ev.gates.append(Gate("score", ev.score >= ev.threshold,
                             f"{ev.score:.3f} (seuil {ev.threshold:.3f})"))

        # Priorite pour le classement entre instruments : on tient compte de
        # la qualite du signal, de la marge disponible et du poids de l'actif.
        ev.priority_score = round(
            ev.score * instrument.priority * (1.0 + min(ev.rr, 4.0) * 0.05), 4)
        return ev

    # ---------------------------------------------------------------
    # Mode quorum : un nombre minimal de confirmations independantes
    # ---------------------------------------------------------------
    def confirmations(
        self,
        side: Side,
        entry: IndicatorSet,
        ctx: IndicatorSet,
        bias: IndicatorSet,
        chart: ChartRead,
        tick: Optional[Tick] = None,
    ) -> list[Confirmation]:
        """Liste des confirmations pour un sens donne.

        Chaque confirmation est INDEPENDANTE des autres : elle interroge une
        famille d'information differente (price action, tendance, momentum,
        volume, structure). C'est ce qui donne du sens au comptage — additionner
        trois lectures du meme phenomene ne prouverait rien.
        """
        sign = side.sign
        haussier = side is Side.BUY
        price = entry.last.close if entry.last else 0.0
        atr = entry.atr.value or 0.0
        out: list[Confirmation] = []

        # 1. Bougies japonaises : la lecture du prix lui-meme.
        hits = K.scan(list(entry.candles)[-3:], atr)
        pattern = K.pattern_score(hits)
        noms = ", ".join(h.name for h in hits) or "aucun motif"
        out.append(Confirmation("bougies", sign * pattern >= 0.25 and not K.has_blocker(hits), noms))

        # 2. Tendance courte : position et ordre des moyennes mobiles.
        tendance = False
        detail_t = "moyennes non pretes"
        if entry.ema_fast.ready and entry.ema_mid.ready:
            au_dessus = sign * (price - entry.ema_mid.value) > 0
            ordonnees = sign * (entry.ema_fast.value - entry.ema_mid.value) > 0
            tendance = au_dessus and ordonnees
            detail_t = (f"prix {'au-dessus' if au_dessus else 'en dessous'} de l'EMA, "
                        f"moyennes {'ordonnees' if ordonnees else 'melangees'}")
        out.append(Confirmation("tendance", tendance, detail_t))

        # 3. Momentum : expansion de l'histogramme MACD.
        macd_ok = (entry.macd.rising and haussier) or (entry.macd.falling and not haussier)
        out.append(Confirmation("momentum", bool(macd_ok),
                                f"histogramme {'en expansion' if macd_ok else 'sans appui'}"))

        # 4. Supertrend : filtre directionnel autonome.
        st_ok = entry.supertrend.ready and (entry.supertrend.direction > 0) == haussier
        out.append(Confirmation("supertrend", bool(st_ok),
                                "haussier" if entry.supertrend.direction > 0 else "baissier"))

        # 5. Oscillateur : ni epuise, ni contre le sens.
        osc_ok, detail_o = False, "RSI non pret"
        if entry.rsi.ready and entry.rsi.value is not None:
            r = entry.rsi.value
            if haussier:
                osc_ok = 45.0 <= r <= 78.0
            else:
                osc_ok = 22.0 <= r <= 55.0
            detail_o = f"RSI {r:.0f}"
            if entry.stoch.ready and (
                    (entry.stoch.cross_up() and haussier) or (entry.stoch.cross_down() and not haussier)):
                osc_ok = True
                detail_o += ", croisement stochastique"
        out.append(Confirmation("oscillateur", osc_ok, detail_o))

        # 6. Volume : le mouvement est-il porte ?
        vol_ok = False
        bits = []
        if abs(entry.obv.slope) > 0.03 and sign * entry.obv.slope > 0:
            vol_ok = True
            bits.append(f"OBV {entry.obv.slope:+.2f}")
        if entry.mfi.ready and entry.mfi.value is not None:
            if (haussier and entry.mfi.value > 52) or (not haussier and entry.mfi.value < 48):
                vol_ok = True
                bits.append(f"MFI {entry.mfi.value:.0f}")
        out.append(Confirmation("volume", vol_ok, ", ".join(bits) or "sans appui volume"))

        # 7. VWAP : reference des intervenants de la journee.
        vwap_ok = entry.vwap.ready and sign * (price - entry.vwap.value) > 0
        out.append(Confirmation("vwap", bool(vwap_ok),
                                "du bon cote" if vwap_ok else "mauvais cote"))

        # 8. Structure : appui sur une zone ou un niveau dans le bon sens.
        zone = chart.zone_support(price, side, atr)
        niveau = False
        if atr > 0:
            cible = "support" if haussier else "resistance"
            niveau = any(l.kind == cible and abs(l.price - price) <= 0.8 * atr
                         and l.strength >= 0.4 for l in chart.levels)
        out.append(Confirmation("structure", zone > 0.2 or niveau,
                                "appui sur zone" if zone > 0.2 else
                                ("appui sur niveau" if niveau else "rien de proche")))

        # 9. Contexte : l'unite superieure ne s'y oppose pas.
        voulu = "bullish" if haussier else "bearish"
        contraire = "bearish" if haussier else "bullish"
        ctx_ok = ctx.trend_bias() != contraire and bias.trend_bias() != contraire
        out.append(Confirmation("contexte", ctx_ok,
                                f"{ctx.trend_bias()} / {bias.trend_bias()} pour un {voulu}"))

        # 10. Balayage de liquidite : le prix est alle chercher les stops
        # juste derriere l'extreme, puis a ete rejete. Ce n'est pas une
        # cassure — c'est souvent le contraire d'une cassure.
        sens_balayage, force, detail_b = balayage_de_liquidite(
            list(entry.candles), atr)
        out.append(Confirmation("balayage", sens_balayage == sign and force > 0,
                                detail_b))

        # 11. Carnet d'ordres : qui est pose au meilleur prix.
        # Sans tailles, la confirmation echoue plutot que de passer : une
        # information absente n'est pas une information favorable.
        if tick is not None and tick.bid_size is not None and tick.ask_size is not None:
            desequilibre = desequilibre_carnet(tick.bid_size, tick.ask_size)
            favorable = sign * desequilibre >= 0.12
            detail_c = (f"desequilibre {desequilibre:+.0%} "
                        f"({'favorable' if favorable else 'neutre ou contraire'})")
            out.append(Confirmation("carnet", favorable, detail_c))
        else:
            # La source est muette : on ne sait rien, ni pour ni contre.
            out.append(Confirmation("carnet", False,
                                    "tailles du carnet indisponibles", applicable=False))

        return out

    def _finish_quorum(
        self,
        ev: Evaluation,
        instrument: Instrument,
        entry: IndicatorSet,
        ctx: IndicatorSet,
        bias: IndicatorSet,
        chart: ChartRead,
        tick: Tick,
        price: float,
        atr: float,
        score_bonus: float,
    ) -> Evaluation:
        """Decide en comptant les confirmations, sans exiger l'unanimite."""
        cfg = self.config

        pour_achat = self.confirmations(Side.BUY, entry, ctx, bias, chart, tick)
        pour_vente = self.confirmations(Side.SELL, entry, ctx, bias, chart, tick)
        n_achat = sum(1 for c in pour_achat if c.applicable and c.passed)
        n_vente = sum(1 for c in pour_vente if c.applicable and c.passed)

        # Le sens retenu est celui qui rassemble le plus de confirmations, et
        # il doit devancer l'autre : a egalite, le marche est indecis.
        if n_achat >= n_vente + cfg.confirmation_margin:
            side, confirmations, compte = Side.BUY, pour_achat, n_achat
        elif n_vente >= n_achat + cfg.confirmation_margin:
            side, confirmations, compte = Side.SELL, pour_vente, n_vente
        else:
            ev.confirmations = pour_achat if n_achat >= n_vente else pour_vente
            ev.confirmed, ev.required = max(n_achat, n_vente), cfg.min_confirmations
            ev.rejected_by = f"aucun sens ne se degage ({n_achat} achat contre {n_vente} vente)"
            ev.gates.append(Gate("direction", False, ev.rejected_by))
            return ev

        ev.side, ev.confirmations, ev.confirmed = side, confirmations, compte
        ev.gates.append(Gate("direction", True,
                             f"{side.value} : {n_achat} confirmations achat contre {n_vente} vente"))

        # Le quorum exige peut etre releve par l'avancement de l'objectif :
        # en retard, on ne prend pas plus de risque, on demande plus de preuves.
        ev.required = cfg.min_confirmations + (1 if score_bonus >= 0.06 else 0)

        # La lecture des bougies peut etre rendue obligatoire : c'est la seule
        # information qui vienne du prix lui-meme et non d'un calcul derive.
        if cfg.require_candle_confirmation:
            bougies = next((c for c in confirmations if c.name == "bougies"), None)
            ok = bool(bougies and bougies.passed)
            ev.gates.append(Gate("bougies_obligatoires", ok,
                                 bougies.detail if bougies else "non evaluees"))
            if not ok:
                return ev

        # Niveaux de sortie, identiques aux deux modes.
        structure_stop = self._structure_stop(side, entry, atr)
        sl, tp = self.trade_manager.initial_levels(
            side, price, atr, spread=tick.spread,
            structure_stop=structure_stop, digits=instrument.digits)
        ev.stop_loss, ev.take_profit = sl, tp
        risque = abs(price - sl)
        ev.rr = abs(tp - price) / risque if risque > 0 else 0.0

        rr_ok = ev.rr >= cfg.min_rr - 1e-9
        ev.gates.append(Gate("ratio_rr", rr_ok, f"{ev.rr:.2f} (min {cfg.min_rr:.2f})"))
        if not rr_ok:
            return ev

        ev.setup = "quorum"
        ev.components = self._score_components(side, entry, ctx, bias, chart, None, None, "quorum")
        ev.score = round(sum(c.value for c in ev.components), 4)

        # LE SCORE REDEVIENT UNE BARRIERE, MEME EN QUORUM.
        #
        # Il avait ete rendu purement indicatif ici, le seuil force a zero.
        # Un compte de confirmations ne dit pas la meme chose qu'une force
        # de signal : cinq confirmations faibles restent cinq confirmations.
        # Observe en production le 28 aout, un achat XRP reel ouvert sur un
        # score de 0,24 — tendance +0,01, momentum +0,18, bougies +0,14 —
        # autant dire un tirage a pile ou face, alors que la configuration
        # portait min_score a 0,55. Le reglage existait, s'affichait, et ne
        # servait a rien.
        #
        # Le bonus d'objectif n'est PAS ajoute ici : en quorum il releve
        # deja le nombre de confirmations exigees, et le compter deux fois
        # penaliserait deux fois la meme situation.
        ev.threshold = round(cfg.min_score, 4)
        ev.gates.append(Gate("score", ev.score >= ev.threshold,
                             f"{ev.score:.3f} (seuil {ev.threshold:.3f})"))

        evaluables = sum(1 for c in confirmations if c.applicable)
        ev.gates.append(Gate("quorum", compte >= ev.required,
                             f"{compte} confirmations sur {evaluables} evaluables "
                             f"(minimum {ev.required})"))
        # La ponderation apprise agit ICI et nulle part ailleurs : elle
        # departage des candidats deja valides quand les places sont
        # limitees. Elle ne peut pas rendre valide un trade refuse, ni
        # elargir un stop, ni augmenter le risque. Un robot qui ajuste seul
        # son risque a partir de ses bons resultats augmente la mise juste
        # avant de rendre les gains.
        ev.priority_score = round(
            (compte / max(1, evaluables)) * instrument.priority
            * (1.0 + min(ev.rr, 4.0) * 0.05)
            * self.poids.poids(instrument.correlation_group), 4)
        return ev

    # ---------------------------------------------------------------
    # Detection de configuration
    # ---------------------------------------------------------------
    def _detect_setup(
        self,
        entry: IndicatorSet,
        ctx: IndicatorSet,
        bias: IndicatorSet,
        chart: ChartRead,
        news: Optional[NewsWindow],
    ) -> Optional[tuple[Side, str, str]]:
        """Identifie le scenario de trading, ou None s'il n'y en a aucun."""
        cfg = self.config
        atr = entry.atr.value or 0.0
        if atr <= 0 or not entry.last:
            return None

        price = entry.last.close
        recent = list(entry.candles)[-3:]
        hits = K.scan(recent, atr)
        pattern = K.pattern_score(hits)
        blocked = K.has_blocker(hits)
        trend = ctx.trend_bias()

        # --- 1. Cassure post-annonce (fenetre breakout) ---
        if news is not None and news.breakout_mode:
            upper, lower = entry.donchian.exclude_last()
            if upper and price > upper and pattern >= 0:
                return Side.BUY, "cassure_post_annonce", f"cassure du plus haut {upper:.5f} apres publication"
            if lower and price < lower and pattern <= 0:
                return Side.SELL, "cassure_post_annonce", f"cassure du plus bas {lower:.5f} apres publication"

        # --- 2. Suivi de tendance sur repli ---
        # Le scenario de reference : tendance etablie, repli sur une zone,
        # bougie de reprise dans le sens de la tendance.
        if trend == "bullish" and not blocked:
            near_ema = entry.ema_mid.ready and abs(price - entry.ema_mid.value) <= 0.9 * atr
            near_zone = chart.zone_support(price, Side.BUY, atr) > 0.2
            near_fibo = _near_fibo(price, chart, atr)
            pulled_back = entry.rsi.value is not None and entry.rsi.value < 62
            if (near_ema or near_zone or near_fibo) and pulled_back and pattern > 0.25:
                where = "EMA" if near_ema else ("zone institutionnelle" if near_zone else "retracement Fibonacci")
                return Side.BUY, "tendance_repli", f"repli sur {where} + bougie de reprise ({pattern:+.2f})"

        if trend == "bearish" and not blocked:
            near_ema = entry.ema_mid.ready and abs(price - entry.ema_mid.value) <= 0.9 * atr
            near_zone = chart.zone_support(price, Side.SELL, atr) > 0.2
            near_fibo = _near_fibo(price, chart, atr)
            pulled_back = entry.rsi.value is not None and entry.rsi.value > 38
            if (near_ema or near_zone or near_fibo) and pulled_back and pattern < -0.25:
                where = "EMA" if near_ema else ("zone institutionnelle" if near_zone else "retracement Fibonacci")
                return Side.SELL, "tendance_repli", f"repli sur {where} + bougie de reprise ({pattern:+.2f})"

        # --- 3. Cassure de canal / sortie de compression ---
        upper, lower = entry.donchian.exclude_last()
        released = not entry.squeeze()
        volume_ok = entry.obv.slope > 0.05 or (entry.mfi.value or 50) > 52
        if upper and price > upper and released and trend != "bearish":
            if volume_ok and pattern >= 0 and not blocked:
                return Side.BUY, "cassure", f"cassure du plus haut {upper:.5f} avec confirmation volume"
        if lower and price < lower and released and trend != "bullish":
            if (entry.obv.slope < -0.05 or (entry.mfi.value or 50) < 48) and pattern <= 0 and not blocked:
                return Side.SELL, "cassure", f"cassure du plus bas {lower:.5f} avec confirmation volume"

        # --- 4. Retournement sur niveau (uniquement hors tendance) ---
        if cfg.allow_counter_trend and entry.hurst.regime in ("mean_revert", "random"):
            div = chart.divergence_score()
            support = _nearest_kind(chart, price, "support", atr)
            resistance = _nearest_kind(chart, price, "resistance", atr)
            rsi = entry.rsi.value or 50.0
            if support and div > 0.25 and pattern > 0.4 and rsi < 35:
                return Side.BUY, "retournement_niveau", f"rejet du support {support:.5f} + divergence haussiere"
            if resistance and div < -0.25 and pattern < -0.4 and rsi > 65:
                return Side.SELL, "retournement_niveau", f"rejet de la resistance {resistance:.5f} + divergence baissiere"

        return None

    # ---------------------------------------------------------------
    def _structure_stop(self, side: Side, ind: IndicatorSet, atr: float) -> Optional[float]:
        """Stop naturel : au-dela du dernier swing, avec une marge de bruit."""
        margin = 0.25 * atr
        if side is Side.BUY:
            low = ind.swings.last_low
            return low - margin if low is not None else None
        high = ind.swings.last_high
        return high + margin if high is not None else None

    # ---------------------------------------------------------------
    def _score_components(
        self,
        side: Side,
        entry: IndicatorSet,
        ctx: IndicatorSet,
        bias: IndicatorSet,
        chart: ChartRead,
        macro_bias: Optional[MacroBias],
        news: Optional[NewsWindow],
        setup: str,
    ) -> list[ScoreComponent]:
        """Calcule les briques du score, chacune ramenee a [-1, 1] puis ponderee."""
        cfg = self.config
        sign = side.sign
        out: list[ScoreComponent] = []
        price = entry.last.close if entry.last else 0.0
        atr = entry.atr.value or 0.0

        # --- Tendance multi-unites de temps ---
        trend_raw, trend_bits = 0.0, []
        for name, ind, weight in (("M5", entry, 0.3), ("contexte", ctx, 0.4), ("fond", bias, 0.3)):
            b = ind.trend_bias()
            if b == "bullish":
                trend_raw += weight * sign
                trend_bits.append(f"{name} haussier")
            elif b == "bearish":
                trend_raw -= weight * sign
                trend_bits.append(f"{name} baissier")
        if entry.supertrend.ready:
            trend_raw += 0.25 * sign * (1 if entry.supertrend.direction > 0 else -1)
            trend_bits.append(f"supertrend {'haussier' if entry.supertrend.direction > 0 else 'baissier'}")
        if entry.ichimoku.ready:
            pos = entry.ichimoku.position(price)
            if pos != "inside":
                trend_raw += 0.20 * sign * (1 if pos == "above" else -1)
                trend_bits.append(f"nuage ichimoku : prix {pos}")
        out.append(ScoreComponent("tendance", cfg.w_trend * _clip(trend_raw),
                                  ", ".join(trend_bits[:3]) or "neutre"))

        # --- Momentum ---
        mom_raw, mom_bits = 0.0, []
        if entry.macd.ready:
            if (entry.macd.rising and side is Side.BUY) or (entry.macd.falling and side is Side.SELL):
                mom_raw += 0.4
                mom_bits.append("MACD en expansion")
            elif (entry.macd.falling and side is Side.BUY) or (entry.macd.rising and side is Side.SELL):
                mom_raw -= 0.4
                mom_bits.append("MACD en contraction")
        if entry.rsi.ready:
            r = entry.rsi.value
            centered = (r - 50.0) / 50.0
            mom_raw += 0.35 * sign * centered
            if (side is Side.BUY and r > 76) or (side is Side.SELL and r < 24):
                mom_raw -= 0.35
                mom_bits.append(f"RSI {r:.0f} en zone d'epuisement")
            else:
                mom_bits.append(f"RSI {r:.0f}")
        if entry.stoch.ready:
            if (entry.stoch.cross_up() and side is Side.BUY) or (entry.stoch.cross_down() and side is Side.SELL):
                mom_raw += 0.3
                mom_bits.append("croisement stochastique favorable")
        if entry.adx.ready and entry.adx.value is not None:
            if entry.adx.value >= 25:
                mom_raw += 0.25
                mom_bits.append(f"ADX {entry.adx.value:.0f}")
        out.append(ScoreComponent("momentum", cfg.w_momentum * _clip(mom_raw),
                                  ", ".join(mom_bits[:3]) or "neutre"))

        # --- Bougies japonaises ---
        hits = K.scan(list(entry.candles)[-3:], atr)
        candle_raw = sign * K.pattern_score(hits)
        out.append(ScoreComponent("bougies", cfg.w_candles * _clip(candle_raw),
                                  ", ".join(h.name for h in hits) or "aucun pattern"))

        # --- Figures chartistes ---
        chart_raw = sign * chart.pattern_score()
        out.append(ScoreComponent("figures", cfg.w_chart * _clip(chart_raw),
                                  ", ".join(p.name for p in chart.patterns) or "aucune figure"))

        # --- Divergences ---
        div_raw = sign * chart.divergence_score()
        out.append(ScoreComponent("divergences", cfg.w_divergence * _clip(div_raw),
                                  ", ".join(d.kind for d in chart.divergences) or "aucune divergence"))

        # --- Zones institutionnelles ---
        zone_raw = chart.zone_support(price, side, atr)
        detail = "appui sur zone" if zone_raw > 0.2 else "pas de zone proche"
        if chart.profile is not None:
            pos = chart.profile.position(price)
            if (pos == "above_value" and side is Side.BUY) or (pos == "below_value" and side is Side.SELL):
                zone_raw += 0.25
                detail += f", prix {pos} (profil de volume)"
        out.append(ScoreComponent("zones", cfg.w_zones * _clip(zone_raw), detail))

        # --- Volume ---
        vol_raw, vol_bits = 0.0, []
        if abs(entry.obv.slope) > 0.02:
            vol_raw += sign * _clip(entry.obv.slope * 3.0) * 0.6
            vol_bits.append(f"OBV {entry.obv.slope:+.2f}")
        if entry.mfi.ready and entry.mfi.value is not None:
            vol_raw += 0.4 * sign * ((entry.mfi.value - 50.0) / 50.0)
            vol_bits.append(f"MFI {entry.mfi.value:.0f}")
        if entry.vwap.ready:
            if sign * (price - entry.vwap.value) > 0:
                vol_raw += 0.3
                vol_bits.append("du bon cote du VWAP")
            else:
                vol_raw -= 0.2
                vol_bits.append("mauvais cote du VWAP")
        out.append(ScoreComponent("volume", cfg.w_volume * _clip(vol_raw),
                                  ", ".join(vol_bits[:3]) or "neutre"))

        # --- Macro ---
        if macro_bias is not None and macro_bias.confidence > 0:
            macro_raw = sign * macro_bias.score * macro_bias.confidence
            out.append(ScoreComponent("macro", cfg.w_macro * _clip(macro_raw),
                                      "; ".join(macro_bias.drivers[:2]) or macro_bias.direction))
        else:
            out.append(ScoreComponent("macro", 0.0, "indisponible"))

        # --- News recentes ---
        news_raw = 0.0
        news_detail = "aucune publication recente"
        if news is not None and news.event is not None and news.minutes_to_event is not None:
            if -120 <= news.minutes_to_event <= 0 and news.event.actual is not None:
                news_raw = sign * news.event.gold_direction()
                news_detail = f"{news.event.title} publie ({news.event.surprise():+.2%} vs consensus)"
        out.append(ScoreComponent("news", cfg.w_news * _clip(news_raw), news_detail))

        return out


# ==========================================================================
# Utilitaires
# ==========================================================================
def _clip(x: float) -> float:
    return max(-1.0, min(1.0, x))


def _opposite(bias: str) -> str:
    return "bearish" if bias == "bullish" else "bullish"


def _near_fibo(price: float, chart: ChartRead, atr: float) -> bool:
    """Le prix est-il sur une zone de retracement de Fibonacci utile (38-62 %) ?"""
    if not chart.fibo or atr <= 0:
        return False
    for key in ("retr_0.382", "retr_0.5", "retr_0.618"):
        level = chart.fibo.get(key)
        if level is not None and abs(price - level) <= 0.5 * atr:
            return True
    return False


def _nearest_kind(chart: ChartRead, price: float, kind: str, atr: float) -> Optional[float]:
    """Niveau du type demande situe a moins d'un ATR du prix."""
    if atr <= 0:
        return None
    candidates = [l for l in chart.levels if l.kind == kind and abs(l.price - price) <= 1.0 * atr]
    if not candidates:
        return None
    return min(candidates, key=lambda l: abs(l.price - price)).price
