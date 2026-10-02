"""Strategy Lab -- laboratoire autonome inspire des principes publics d'AITradingArena.

Aucun ordre n'est envoye. Le labo utilise uniquement Backtester/PaperBroker,
garde les echecs, deduplique les configurations et separe backtest et
forward-test. Les strategies validees restent en incubation/paper: elles ne
sont jamais branchees automatiquement sur le compte reel.
"""
from __future__ import annotations
import copy, dataclasses, hashlib, json, logging, os, time, urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path
from .backtest import Backtester
from .backtest_portefeuille import BacktestPortefeuille
from .core import Candle
from .datasources.base import tf_seconds
from .universe import Universe, ajouter_cryptos, instrument_crypto

logger = logging.getLogger(__name__)
BAR_BACKTEST = 1200
BAR_FORWARD = 240
LAB_HISTORY_DAYS = int(os.getenv("GB_LAB_HISTORY_DAYS", "365"))
# 2 oct. 2026 : un candidat en M5 chargeait 180 jours de M5 pour ~245
# cryptos A LA FOIS (12 millions de bougies) -- le Lab etait tue par son
# plafond memoire avant d'avoir teste quoi que ce soit, 16 h sans resultat.
# Le nombre de bougies par serie est borne : les unites lentes gardent
# toute la periode, les rapides n'en gardent que ce qui tient dans la borne.
LAB_MAX_BARS = int(os.getenv("GB_LAB_MAX_BARS", "12000"))


def _lab_jours(timeframe):
    """Jours d'historique pour une unite : la periode, bornee en bougies."""
    return max(7, min(LAB_HISTORY_DAYS, int(LAB_MAX_BARS * tf_seconds(timeframe) / 86400)))
MIN_TRADES = 100
MIN_FORWARD_TRADES = 20
MIN_PF = 1.20
MIN_WIN = 51.0
MIN_PAYOFF = 1.0
LAB_BITVAVO_CACHE = Path(os.getenv("GB_LAB_BITVAVO_CACHE", "data/lab-bitvavo"))
LAB_BITVAVO_LIMIT = 1440
LAB_BITVAVO_INTERVALS = {"M1": "1m", "M3": "3m", "M5": "5m", "M15": "15m", "M30": "30m", "H1": "1h", "H4": "4h", "D1": "1d"}
LAB_DATA_MEMORY = {}

def _lab_align(ts, seconds):
    return int(ts // seconds) * seconds

def _lab_http_json(url, params=None):
    if params:
        from urllib.parse import urlencode
        url = f"{url}?{urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "gold-bot-lab/1.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))

def _lab_cache_file(market, timeframe):
    return LAB_BITVAVO_CACHE / market.replace("-", "_") / f"{timeframe}.json"

def _lab_read_cache(path):
    if not path.exists():
        return []
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
        return [Candle(float(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5])) for r in rows]
    except Exception:
        return []

def _lab_write_cache(path, candles):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps([[c.ts, c.open, c.high, c.low, c.close, c.volume] for c in candles], separators=(",", ":")), encoding="utf-8")
    tmp.replace(path)

def _lab_fetch_range(market, timeframe, start, end):
    interval = LAB_BITVAVO_INTERVALS[timeframe]
    step = tf_seconds(timeframe) * 1000
    cursor_end = _lab_align(end / 1000, tf_seconds(timeframe)) * 1000
    out = []
    while cursor_end >= start:
        rows = _lab_http_json("https://api.bitvavo.com/v2/" + market + "/candles",
                              {"interval": interval, "end": cursor_end, "limit": LAB_BITVAVO_LIMIT})
        if not rows:
            break
        got = [Candle(float(r[0]) / 1000, float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5]))
               for r in rows if len(r) >= 6]
        got.sort(key=lambda c: c.ts)
        out.extend(got)
        oldest = int(got[0].ts * 1000)
        if oldest <= start:
            break
        cursor_end = oldest - 1
    uniq = {c.ts: c for c in out}
    return [uniq[k] for k in sorted(uniq) if start <= int(k * 1000) <= end]

def _lab_candles_1y(market, timeframe, extra_days=0):
    now = time.time(); seconds = tf_seconds(timeframe)
    jours = _lab_jours(timeframe)
    end = _lab_align(now, seconds) + seconds - 1; start = end - (jours + extra_days) * 86400
    path = _lab_cache_file(market, timeframe); cached = _lab_read_cache(path)
    if cached and cached[0].ts <= start and cached[-1].ts >= end - seconds:
        return [c for c in cached if start <= c.ts <= end]
    logger.info("Lab Bitvavo: téléchargement %s %s sur %d jours", market, timeframe, jours)
    fresh = _lab_fetch_range(market, timeframe, int(start * 1000), int(end * 1000))
    if not fresh:
        raise RuntimeError(f"historique vide {market} {timeframe}")
    _lab_write_cache(path, fresh)
    return [c for c in fresh if start <= c.ts <= end]

def _lab_prepare_universe_and_data(timeframes):
    markets = _lab_http_json("https://api.bitvavo.com/v2/markets")
    quote = os.getenv("BITVAVO_QUOTE_ASSET", "EUR").upper()
    markets = [m for m in markets if isinstance(m, dict) and m.get("quote") == quote and m.get("status") == "trading" and m.get("base") not in (None, "", quote)]
    bases = {str(m["base"]).upper(): m for m in markets}
    ajouter_cryptos({b: "crypto_alt" for b in bases})
    instruments = [instrument_crypto(b, "crypto_alt", quote_currency=quote) for b in sorted(bases)]
    data = {}; skipped = {}
    for inst in instruments:
        base = inst.symbol[:-3]; market = bases[base]["market"]
        try:
            series = {tf: _lab_candles_1y(market, tf, max(1, int((BAR_FORWARD * tf_seconds(tf) + 86399) / 86400))) for tf in timeframes}
            if any(len(v) < 200 or (v[-1].ts - v[0].ts) < _lab_jours(tf) * 86400 * 0.95 for tf, v in series.items()):
                skipped[base] = "historique inférieur à 95% de 1 an"; continue
            data[inst.symbol] = series
        except Exception as exc:
            skipped[base] = str(exc)[:160]
    logger.info("Lab Bitvavo: %d marchés EUR trading, %d chargés, %d écartés", len(markets), len(data), len(skipped))
    return instruments, data, {"markets_trading_eur": len(markets), "symbols_loaded": len(data), "symbols_skipped": len(skipped), "skipped": skipped, "history_days": LAB_HISTORY_DAYS, "source": "Bitvavo REST candles"}

LAB_STATE = Path(os.getenv("GB_LAB_STATE_FILE", "data/lab-state.json"))
LAB_BOOK = Path(os.getenv("GB_LAB_BOOK_FILE", "data/lab-book.jsonl"))
LAB_SYMBOLS = tuple(x.strip().upper() for x in os.getenv(
    "LAB_SYMBOLS",
    "BTCUSD,ETHUSD,SOLUSD,ADAUSD,AVAXUSD,LINKUSD,DOGEUSD,XRPUSD"
).split(",") if x.strip())

# Les agents proposent une idee + au maximum deux reglages. Ils ne modifient
# jamais le moteur de risque/execution du compte reel.
AGENTS = {
    "prospector-momentum": [
        {"name": "momentum_28", "famille": "momentum", "momentum_formation": 28, "momentum_detention": 5},
        {"name": "momentum_14", "famille": "momentum", "momentum_formation": 14, "momentum_detention": 3},
    ],
    # LA FAMILLE DOIT CORRESPONDRE AUX REGLAGES PROPOSES.
    #
    # Ces trois agents portaient « famille: momentum » (ou aucune famille,
    # donc celle de la configuration de base, momentum elle aussi). Or
    # `_finish_momentum` ne lit QUE momentum_formation, momentum_seuil_pct
    # et momentum_detention : ni le canal Donchian, ni l'ADX, ni le ratio
    # rendement/risque. Leurs variantes mesuraient donc le temoin, a
    # l'identique, indefiniment — 166 essais sur 354 rendaient exactement
    # -291,04 EUR. Mesure du 27 septembre, quatre symboles :
    #
    #     min_adx 5 / min_adx 40 / donchian 5 / donchian 60 / min_score 0
    #     -> 218 trades, -427,26 EUR, a la decimale, pour TOUTES.
    "prospector-breakout": [
        {"name": "donchian_10", "famille": "donchian", "donchian_entrees": [10], "donchian_sortie": 10},
        {"name": "donchian_20", "famille": "donchian", "donchian_entrees": [20], "donchian_sortie": 10},
    ],
    "prospector-filter": [
        {"name": "adx_16", "famille": "tendance", "min_adx": 16.0},
        {"name": "adx_20", "famille": "tendance", "min_adx": 20.0},
    ],
    "prospector-reversion": [
        {"name": "reversion_50_2_05", "famille": "reversion", "reversion_ma_periode": 50, "reversion_entree_atr": 2.0, "reversion_sortie_atr": 0.5},
        {"name": "reversion_80_25_07", "famille": "reversion", "reversion_ma_periode": 80, "reversion_entree_atr": 2.5, "reversion_sortie_atr": 0.7},
    ],
    "risk-refiner": [
        {"name": "rr_18", "famille": "risque", "min_rr": 1.8},
        {"name": "rr_22", "famille": "risque", "min_rr": 2.2},
    ],
    "prospector-volatility": [
        {"name": "volatility_mid", "famille": "volatilite", "min_atr_percentile": 0.20, "max_atr_percentile": 0.90},
        {"name": "volatility_wide", "famille": "volatilite", "min_atr_percentile": 0.10, "max_atr_percentile": 0.95},
    ],
    "volatility-refiner": [
        {"name": "atr_stop_18", "famille": "risque", "atr_stop_mult": 1.8},
        {"name": "atr_stop_22", "famille": "risque", "atr_stop_mult": 2.2},
    ],
    "timeframe-refiner": [
        {"name": "m15", "trigger_tf": "M15", "entry_tf": "M15", "context_tf": "H1", "bias_tf": "H1"},
        {"name": "h1", "trigger_tf": "H1", "entry_tf": "H1", "context_tf": "H4", "bias_tf": "H4"},
    ],
}

@dataclass
class Candidate:
    id: str
    agent: str
    parent_id: str | None
    stage: str
    fingerprint: str
    params: dict
    created_at: float
    backtest: dict
    forward: dict | None = None
    reason: str = ""

def fingerprint(params: dict) -> str:
    raw = json.dumps(params, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()[:16]

#: CE QUE CHAQUE FAMILLE LIT REELLEMENT DANS `cfg.strategy`.
#
# `Strategy._finish` aiguille vers une branche par famille, et chaque
# branche n'ouvre que ses propres reglages. Un reglage propose hors de sa
# famille est pose sur la configuration — `_apply` le fait bien — puis
# n'est JAMAIS LU. Rien ne le signale : le backtest tourne, rend un
# resultat parfaitement plausible, et c'est celui du temoin.
#
# Les sections `trade` et `risk` (atr_stop_mult, trail_atr_mult,
# base_risk_pct...) sont lues par toutes les familles : elles ne figurent
# pas ici, elles mordent toujours.
REGLAGES_PAR_FAMILLE = {
    "tendance": {"min_adx", "min_headroom_atr", "min_rr", "require_trigger", "require_mtf_alignment", "allow_counter_trend", "macro_veto_threshold", "w_trend", "w_momentum", "w_candles", "w_chart", "w_divergence", "w_zones", "w_volume", "w_macro", "w_news"},
    "momentum": {"momentum_formation", "momentum_seuil_pct",
                 "momentum_detention"},
    "donchian": {"donchian_entrees", "donchian_sortie",
                 "donchian_filtre_precedent", "donchian_momentum_max_pct"},
    "reversion": {"reversion_ma_periode", "reversion_entree_atr", "reversion_sortie_atr"},
    "risque": {"min_rr"},
    "volatilite": {"min_atr_percentile", "max_atr_percentile", "min_atr_price_ratio", "max_spread_atr_ratio"},
    "filtre": {"min_adx", "min_headroom_atr", "min_score", "require_mtf_alignment", "allow_counter_trend"},
    "sortie": {"tp_r_multiple", "trail_atr_mult", "trail_start_r", "time_stop_minutes", "detention_max_jours", "reversal_exit_r"},
}

#: Reglages de `cfg.strategy` lus par toutes les familles.
#: Les quatre unites de temps alimentent directement le scanner/backtest :
#: elles ne doivent donc jamais etre declarees « inertes » simplement parce
#: que la strategie utilise une branche specialisee.
REGLAGES_GLOBAUX = {
    "entry_tf", "trigger_tf", "context_tf", "bias_tf",
    "adaptive_timeframe", "timeframe_ladder", "max_cost_ratio_pct",
    "mode", "min_confirmations", "require_candle_confirmation",
    "confirmation_margin", "rsi_achat_min", "rsi_achat_max",
    "rsi_vente_min", "rsi_vente_max",
    # Le filtre de volatilite est execute par le moteur avant la branche
    # de famille : ces reglages ont donc un effet quelle que soit la famille.
    "min_atr_percentile", "max_atr_percentile",
    "min_atr_price_ratio", "max_spread_atr_ratio",
}

#: Reglages de `cfg.trade` / `cfg.risk` lus par le moteur quel que soit
#: le chemin de strategie. Ils doivent rester testables comme hypotheses
#: transversales et ne peuvent donc pas etre declares « inertes ».
REGLAGES_EXECUTION_GLOBAUX = {
    "atr_stop_mult", "min_stop_atr", "max_stop_atr",
    "tp_r_multiple", "trail_atr_mult", "trail_start_r",
    "time_stop_minutes", "detention_max_jours", "reversal_exit_r",
    "base_risk_pct", "max_risk_pct", "risk_per_trade_pct",
}

#: Les reglages de `cfg.strategy` qu'AUCUNE branche specialisee ne lit :
#: ils n'ont d'effet que sur le chemin generique (famille « tendance »).
_SPECIALISES = set().union(*REGLAGES_PAR_FAMILLE.values())


STRATEGIE_FAMILLES = {"tendance", "momentum", "donchian", "reversion"}

def famille_execution(params: dict, fallback: str = "tendance") -> str:
    f = str(params.get("strategie_famille") or params.get("famille") or fallback).strip().lower()
    return f if f in STRATEGIE_FAMILLES else fallback


def reglages_sans_effet(params: dict, famille: str) -> list[str]:
    """Les reglages proposes que cette famille-la ne lira jamais.

    Sert de garde-fou au labo : une hypothese dont AUCUN reglage ne mord
    est refusee avant le backtest, au lieu d'etre archivee comme
    « barre non franchie » — ce qu'elle n'a jamais eu l'occasion de
    franchir.
    """
    inertes: list[str] = []
    lus = REGLAGES_PAR_FAMILLE.get(famille, set())
    for cle in params:
        if cle in ("name", "famille", "strategie_famille"):
            continue
        if cle in REGLAGES_EXECUTION_GLOBAUX:
            continue
        if cle in _SPECIALISES and cle not in lus:
            inertes.append(cle)
        elif famille in REGLAGES_PAR_FAMILLE and cle not in lus:
            # Une branche specialisee ignore les reglages du chemin generique
            # (min_adx, min_score, min_rr...) mais PAS les reglages globaux
            # du moteur de lecture, notamment les unites de temps.
            if cle not in REGLAGES_GLOBAUX:
                from .settings import StrategyConfig
                if cle in {f.name for f in dataclasses.fields(StrategyConfig)}:
                    inertes.append(cle)
    return sorted(set(inertes))


def _apply(cfg, params):
    for key, value in params.items():
        if key in ("name", "strategie_famille"):
            continue
        for section in (cfg.strategy, cfg.trade, cfg.risk):
            if hasattr(section, key):
                setattr(section, key, value)
                break
    return cfg

def _stats(trades):
    real = [t for t in trades if not getattr(t, "partial", False)]
    wins = [t for t in real if t.profit > 0]
    losses = [t for t in real if t.profit <= 0]
    gw = sum(t.profit for t in wins)
    gl = abs(sum(t.profit for t in losses))
    payoff = (gw / len(wins)) / (gl / len(losses)) if wins and losses and gl else 0.0
    return {
        "trades": len(real),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / len(real) * 100, 2) if real else 0.0,
        "profit_factor": round(gw / gl, 3) if gl else (999.0 if gw else 0.0),
        "payoff": round(payoff, 3),
        "profit": round(sum(t.profit for t in real), 2),
    }

def _aggregate(results):
    """Agregation historique par symbole (conserve pour diagnostic)."""
    trades = sum(x["trades"] for x in results)
    wins = sum(x["wins"] for x in results)
    losses = sum(x["losses"] for x in results)
    gw = sum(x.get("gross_w", 0.0) for x in results)
    gl = sum(x.get("gross_l", 0.0) for x in results)
    return {
        "symbols_tested": len(results),
        "trades": trades,
        "win_rate": round(wins / trades * 100, 2) if trades else 0.0,
        "profit_factor": round(gw / gl, 3) if gl else (999.0 if gw else 0.0),
        "payoff": round((gw / wins) / (gl / losses), 3) if wins and losses and gl else 0.0,
        "profit": round(sum(x["profit"] for x in results), 2),
    }


def _stats_portefeuille(resultat, start_balance: float) -> dict:
    """Mesure une strategie sur un compte UNIQUE partage entre les actifs."""
    trades = [t for t in resultat.trades if not getattr(t, "partial", False)]
    wins = [t for t in trades if t.profit > 0]
    losses = [t for t in trades if t.profit <= 0]
    gross_w = sum(t.profit for t in wins)
    gross_l = abs(sum(t.profit for t in losses))
    end = float(resultat.end_balance or start_balance)
    return {
        "symbols_tested": len(resultat.par_instrument),
        "trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / len(trades) * 100, 2) if trades else 0.0,
        "profit_factor": round(gross_w / gross_l, 3) if gross_l else (999.0 if gross_w else 0.0),
        "payoff": round((gross_w / len(wins)) / (gross_l / len(losses)), 3) if wins and losses and gross_l else 0.0,
        "profit": round(end - start_balance, 2),
        "start_balance": round(start_balance, 2),
        "end_balance": round(end, 2),
        "return_pct": round((end / start_balance - 1) * 100, 2) if start_balance else 0.0,
        "max_drawdown_pct": resultat.stats().get("drawdown_max_pct", 0.0),
        "portfolio_mode": True,
    }

def _run_one(cfg, symbol, bars, decalage=0):
    result = Backtester(cfg).run(
        symbol, bars=bars, start_balance=float(cfg.engine.start_balance),
        decalage=decalage,
    )
    stats = _stats(result.trades)
    stats["symbol"] = symbol
    stats["gross_w"] = sum(t.profit for t in result.trades if not getattr(t, "partial", False) and t.profit > 0)
    stats["gross_l"] = abs(sum(t.profit for t in result.trades if not getattr(t, "partial", False) and t.profit <= 0))
    return stats

class StrategyLab:
    def __init__(self, base_config):
        self.base = base_config
        LAB_STATE.parent.mkdir(parents=True, exist_ok=True)
        LAB_BOOK.parent.mkdir(parents=True, exist_ok=True)
        self.state = self._load()
        self._reprendre_les_tests_interrompus()
        self._publish("IDLE", "Laboratoire pret")

    def _reprendre_les_tests_interrompus(self):
        """Une hypothese TESTING au demarrage est un test mort en route.

        2 oct. 2026 : tue par son plafond memoire, le Lab laissait ses
        hypotheses en TESTING pour toujours -- jamais retestees, jamais
        conclues. Un seul Lab tourne : au demarrage, tout TESTING est orphelin.
        """
        url = os.getenv("SUPABASE_URL", "").rstrip("/")
        key = os.getenv("SUPABASE_SERVICE_KEY", "")
        if not url or not key:
            return
        try:
            req = urllib.request.Request(
                f"{url}/rest/v1/lab_research?statut=eq.TESTING",
                data=json.dumps({"statut": "IDEATED"}).encode(),
                headers={"apikey": key, "authorization": f"Bearer {key}",
                         "content-type": "application/json",
                         "prefer": "return=minimal"},
                method="PATCH")
            urllib.request.urlopen(req, timeout=15).close()
        except Exception as exc:  # noqa: BLE001 - jamais bloquant au demarrage
            logger.warning("reprise des tests interrompus : %s", str(exc)[:120])

    def _load(self):
        try:
            return json.loads(LAB_STATE.read_text())
        except Exception:
            return {"stage": "IDLE", "current": None, "completed": 0,
                    "candidates": 0, "validated": 0, "forward_passed": 0,
                    "last_error": "", "updated_at": time.time()}

    def _save(self):
        self.state["updated_at"] = time.time()
        LAB_STATE.write_text(json.dumps(self.state, indent=2, ensure_ascii=False))

    def _publish(self, stage, detail):
        self.state["stage"] = stage
        self.state["detail"] = detail
        self._save()
        self._supabase("lab_status", {
            "id": "robot", "stage": stage, "detail": detail,
            "completed": self.state.get("completed", 0),
            "candidates": self.state.get("candidates", 0),
            "validated": self.state.get("validated", 0),
            "updated_at": "now()",
        })

    def _supabase(self, table, row):
        url = os.getenv("SUPABASE_URL", "").rstrip("/")
        key = os.getenv("SUPABASE_SERVICE_KEY", "")
        if not url or not key:
            return
        try:
            payload = dict(row)
            if payload.get("updated_at") == "now()":
                payload["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            req = urllib.request.Request(
                f"{url}/rest/v1/{table}", data=json.dumps(payload).encode(),
                headers={"apikey": key, "authorization": f"Bearer {key}",
                         "content-type": "application/json",
                         "prefer": "resolution=merge-duplicates"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=15).read()
        except Exception as exc:
            logger.warning("publication labo: %s", str(exc)[:120])

    def _set_research_status(self, research_id, status):
        """Synchronise le cycle d'une hypothese avec son journal lab_research."""
        if not research_id:
            return
        url = os.getenv("SUPABASE_URL", "").rstrip("/")
        key = os.getenv("SUPABASE_SERVICE_KEY", "")
        if not url or not key:
            return
        try:
            req = urllib.request.Request(
                f"{url}/rest/v1/lab_research?id=eq.{int(research_id)}&statut=eq.TESTING",
                data=json.dumps({"statut": "TESTED"}).encode(),
                headers={"apikey": key, "authorization": f"Bearer {key}",
                         "content-type": "application/json", "prefer": "return=minimal"},
                method="PATCH",
            )
            urllib.request.urlopen(req, timeout=15).read()
        except Exception as exc:
            logger.warning("sync lab_research %s: %s", research_id, str(exc)[:120])

    def _record(self, c):
        record = asdict(c)
        with LAB_BOOK.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        # Index compact des seules stratégies validées : le promoteur DEMO 2
        # n'a jamais besoin de rescanner un carnet qui peut devenir très gros.
        if c.stage == "VALIDATED":
            with (LAB_BOOK.parent / "lab-validated.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._supabase("lab_strategies", {
            "strategy_id": c.id, "agent": c.agent, "parent_id": c.parent_id,
            "stage": c.stage, "fingerprint": c.fingerprint, "params": c.params,
            "backtest": c.backtest, "forward_test": c.forward, "reason": c.reason,
        })

    def _seen(self, fp):
        if not LAB_BOOK.exists():
            return False
        return any(f'"fingerprint": "{fp}"' in line for line in LAB_BOOK.read_text(encoding="utf-8").splitlines())

    def run_candidate(self, agent, params, parent_id=None, research_id=None):
        fp = fingerprint(params)
        if self._seen(fp):
            # Une variante deja mesuree ne doit jamais bloquer la boucle sur
            # le meme candidat : on avance le curseur et on laisse le cycle
            # suivant chercher la prochaine hypothese.
            self.state["completed"] = int(self.state.get("completed", 0)) + 1
            self._set_research_status(research_id, "TESTED")
            self._save()
            logger.info("candidat deja mesure %s : passage au suivant", fp)
            return None
        cid = f"{agent}-{fp}"
        self.state["current"] = cid
        self._publish("IDEATED", f"{agent}: {params.get('name', 'strategy')}")

        # UN CANDIDAT DONT AUCUN REGLAGE NE MORD N'EST PAS UN CANDIDAT.
        #
        # Sans ce refus, le labo lancait le backtest, obtenait le resultat
        # du temoin, et l'archivait en « barre non franchie » — verdict
        # sur une idee qui n'a jamais ete mesuree. 166 essais sur 354 ont
        # ete depenses ainsi. Mieux vaut le dire que de le remesurer.
        famille = famille_execution(params, getattr(self.base.strategy, "famille", "tendance"))
        inertes = reglages_sans_effet(params, famille)
        proposes = [k for k in params if k not in ("name", "famille")]
        if proposes and len(inertes) == len(proposes):
            motif = (f"aucun reglage lu par la famille « {famille} » : "
                     f"{', '.join(inertes)}")
            logger.warning("candidat %s refuse — %s", cid, motif)
            self._publish("INEFFECTIF", f"{cid}: {motif}")
            self._record(Candidate(
                id=cid, agent=agent, parent_id=parent_id, stage="INEFFECTIF",
                fingerprint=fp, params=params, created_at=time.time(),
                backtest={}, forward=None, reason=motif))
            return None

        params_exec = dict(params)
        params_exec["famille"] = famille
        cfg = _apply(copy.deepcopy(self.base), params_exec)

        # Full history minus the latest forward window. This prevents the
        # forward period from influencing the candidate gate.
        # IMPORTANT : un seul compte virtuel pour tout l'univers. Le Lab ne
        # doit plus donner le capital entier a chaque crypto puis additionner
        # les profits : le portefeuille partage cash, risque et positions.
        self._publish("BACKTEST", f"{cid}: Bitvavo, 1 an, univers EUR")
        start_balance = float(cfg.engine.start_balance)
        try:
            timeframes = list(getattr(cfg.strategy, "timeframes", (cfg.strategy.entry_tf,)))
            lab_instruments, lab_data, lab_scope = _lab_prepare_universe_and_data(timeframes)
            symbols = sorted(lab_data)
            train_data = {sym: {tf: vals[:-BAR_FORWARD] if len(vals) > BAR_FORWARD else []
                                for tf, vals in series.items()}
                          for sym, series in lab_data.items()}
            portefeuille = BacktestPortefeuille(cfg)
            portefeuille.rejeu.universe = Universe(lab_instruments)
            porte = portefeuille.run(symbols, bars=BAR_BACKTEST,
                                     start_balance=start_balance, decalage=BAR_FORWARD,
                                     series_by_symbol=train_data)
            bt = _stats_portefeuille(porte, start_balance)
            bt["data_scope"] = lab_scope
        except Exception as exc:
            logger.warning("backtest Bitvavo %s: %s", cid, str(exc)[:200])
            bt = {"symbols_tested": 0, "trades": 0, "wins": 0, "losses": 0,
                  "win_rate": 0.0, "profit_factor": 0.0, "payoff": 0.0,
                  "profit": 0.0, "start_balance": start_balance,
                  "end_balance": start_balance, "portfolio_mode": True,
                  "error": str(exc)[:300]}
        passed = (
            bt["trades"] >= MIN_TRADES and bt["profit_factor"] >= MIN_PF
            and bt["win_rate"] >= MIN_WIN and bt["payoff"] > MIN_PAYOFF
        )
        c = Candidate(cid, agent, parent_id,
                      "CANDIDATE" if passed else "ARCHIVED-WEAK",
                      fp, params, time.time(), bt,
                      reason="bar backtest" if passed else "bar backtest non franchie")
        self._record(c)
        self.state["completed"] += 1

        if passed:
            self.state["candidates"] += 1
            self._publish("FORWARD_TEST", f"{cid}: portefeuille recent")
            try:
                portefeuille_fw = BacktestPortefeuille(cfg)
                portefeuille_fw.rejeu.universe = Universe(lab_instruments)
                recent = {sym: {tf: vals[-BAR_FORWARD:] for tf, vals in series.items()}
                          for sym, series in lab_data.items()}
                porte_fw = portefeuille_fw.run(symbols, bars=BAR_FORWARD,
                                               start_balance=start_balance, decalage=0,
                                               series_by_symbol=recent)
                c.forward = _stats_portefeuille(porte_fw, start_balance)
                c.forward["data_scope"] = lab_scope
            except Exception as exc:
                logger.warning("forward portefeuille %s: %s", cid, str(exc)[:200])
                c.forward = {"symbols_tested": 0, "trades": 0, "wins": 0, "losses": 0,
                             "win_rate": 0.0, "profit_factor": 0.0, "payoff": 0.0,
                             "profit": 0.0, "start_balance": start_balance,
                             "end_balance": start_balance, "portfolio_mode": True,
                             "error": str(exc)[:300]}
            forward_pass = (
                c.forward["trades"] >= MIN_FORWARD_TRADES
                and c.forward["profit_factor"] >= MIN_PF
                and c.forward["win_rate"] >= MIN_WIN
                and c.forward["payoff"] > MIN_PAYOFF
            )
            if forward_pass:
                c.stage, c.reason = "VALIDATED", "backtest + forward test franchis"
                self.state["validated"] += 1
                self.state["forward_passed"] += 1
            elif c.forward["trades"] < MIN_FORWARD_TRADES:
                c.stage, c.reason = "INCUBATION", "forward insuffisant"
            else:
                c.stage, c.reason = "RETIRED-WEAK", "forward bar non franchie"
            self._record(c)

        self.state["current"] = None
        self._set_research_status(research_id, "TESTED")
        self._publish(c.stage, c.reason)
        return c

    def _next_research_candidate(self):
        """Prend une hypothese IDEATED issue de la veille/cerveaux et la soumet
        au meme pipeline strict que les candidats internes."""
        url = os.getenv("SUPABASE_URL", "").rstrip("/")
        key = os.getenv("SUPABASE_SERVICE_KEY", "")
        if not url or not key:
            return None
        try:
            req = urllib.request.Request(
                f"{url}/rest/v1/lab_research?statut=eq.IDEATED&hypothese=not.eq.&select=id,titre,famille,hypothese&order=created_at.asc&limit=1",
                headers={"apikey": key, "authorization": f"Bearer {key}"},
            )
            with urllib.request.urlopen(req, timeout=15) as r:
                rows = json.loads(r.read().decode())
            if not rows:
                return None
            row = rows[0]
            raw = row.get("hypothese") or "{}"
            try:
                meta = json.loads(raw)
            except Exception:
                meta = {}
            # Une hypothese externe qui depend d'une serie/feature non
            # presente dans le moteur ne doit jamais etre backtestee avec un
            # proxy implicite : ce serait un faux test.
            feature = str(meta.get("feature_requise") or "").strip() if isinstance(meta, dict) else ""
            if feature:
                patch = urllib.request.Request(
                    f"{url}/rest/v1/lab_research?id=eq.{int(row['id'])}&statut=eq.IDEATED",
                    data=json.dumps({"statut":"FEATURE_REQUIRED"}).encode(),
                    headers={"apikey":key,"authorization":f"Bearer {key}",
                             "content-type":"application/json","prefer":"return=minimal"},
                    method="PATCH")
                urllib.request.urlopen(patch, timeout=15).read()
                logger.info("recherche %s exige une feature externe: %s", row.get("id"), feature[:120])
                return None
            params = meta.get("params") if isinstance(meta, dict) else None
            if not isinstance(params, dict) or not params:
                # Source sans hypothese executable : archive explicitement la
                # reference pour qu'elle ne reboucle jamais indéfiniment.
                patch = urllib.request.Request(
                    f"{url}/rest/v1/lab_research?id=eq.{int(row['id'])}&statut=eq.IDEATED",
                    data=json.dumps({"statut":"REFERENCE"}).encode(),
                    headers={"apikey":key,"authorization":f"Bearer {key}",
                             "content-type":"application/json","prefer":"return=minimal"},
                    method="PATCH")
                urllib.request.urlopen(patch, timeout=15).read()
                logger.info("recherche %s archivee comme reference non executable", row.get("id"))
                return None
            params = dict(params)
            famille_recherche = str(row.get("famille") or params.get("famille") or "tendance").strip().lower()
            params["strategie_famille"] = (famille_recherche if famille_recherche in STRATEGIE_FAMILLES else "tendance")
            params["famille"] = famille_recherche
            params["name"] = str(row.get("titre") or "research_candidate")[:120]
            patch = urllib.request.Request(
                f"{url}/rest/v1/lab_research?id=eq.{int(row['id'])}&statut=eq.IDEATED",
                data=json.dumps({"statut":"TESTING"}).encode(),
                headers={"apikey":key,"authorization":f"Bearer {key}",
                         "content-type":"application/json","prefer":"return=minimal"},
                method="PATCH")
            urllib.request.urlopen(patch, timeout=15).read()
            return "research", params, None, int(row["id"])
        except Exception as exc:
            logger.warning("lecture lab_research: %s", str(exc)[:160])
            return None

    def cycle(self):
        # Les hypotheses issues de la veille et des deux cerveaux passent
        # AVANT la grille interne. Elles subissent exactement les memes
        # garde-fous, backtest portefeuille et forward-test.
        external = self._next_research_candidate()
        if external:
            return self.run_candidate(*external)

        # Premiere passe: quelques familles de signaux, une configuration
        # par job. Ensuite, l'agent affine UNE variable a la fois et repart
        # sur le meme univers. Cela garde la discipline "one/two knobs" et
        # evite de refaire exactement le meme backtest.
        completed = int(self.state.get("completed", 0))
        flat = [(agent, p) for agent, ps in AGENTS.items() for p in ps]
        if completed < len(flat):
            return self.run_candidate(*flat[completed])

        idx = completed - len(flat)
        agent, base = flat[idx % len(flat)]
        round_no = idx // len(flat) + 1
        p = dict(base)
        name = str(p.get("name", "strategy"))
        if agent == "prospector-momentum":
            p["momentum_formation"] = 10 + ((round_no * 7) % 41)
        elif agent == "prospector-breakout":
            n = 5 + ((round_no * 5) % 26)
            p["donchian_entrees"] = [n]
            p["donchian_sortie"] = max(5, n // 2)
        elif agent == "prospector-filter":
            p["min_adx"] = 10.0 + ((round_no * 2) % 21)
        elif agent == "risk-refiner":
            p["famille"] = "risque"
            p["strategie_famille"] = "tendance"
            p["min_rr"] = round(1.2 + ((round_no * 0.1) % 1.9), 2)
        elif agent == "volatility-refiner":
            p["famille"] = "volatilite"
            p["strategie_famille"] = "tendance"
            p["atr_stop_mult"] = round(1.2 + ((round_no * 0.2) % 1.8), 2)
        elif agent == "timeframe-refiner":
            tfs = [("M5","M15"), ("M15","H1"), ("H1","H4"), ("H4","D1")]
            entry, context = tfs[(round_no - 1) % len(tfs)]
            p["entry_tf"], p["trigger_tf"] = entry, entry
            p["context_tf"], p["bias_tf"] = context, context
        p["name"] = f"{name}_v{round_no}"
        return self.run_candidate(agent, p)

    def loop(self, pause_seconds=60):
        # Veille autonome : les deux cerveaux + recherche web sont relances
        # periodiquement par le meme service que le Lab. Ainsi la boucle
        # survit aux deconnexions et ne depend pas d'une session utilisateur.
        last_research = float(self.state.get("last_research", 0))
        research_every = int(os.getenv("LAB_RESEARCH_INTERVAL", "21600"))
        while True:
            try:
                now = time.time()
                if now - last_research >= research_every:
                    self._publish("RESEARCH", "veille GPT + Claude + finance web")
                    import subprocess
                    subprocess.run(
                        [str(Path(".venv/bin/python")), "ops/labo_recherche.py",
                         "--combien", "6",
                         "--local-only",
                         "--sujet", "strategies OHLC crypto: entrees sorties regimes momentum donchian reversion volatilite risque"],
                        cwd=Path.cwd(), timeout=900, check=False)
                    last_research = time.time()
                    self.state["last_research"] = last_research
                    self._save()
                self.cycle()
            except Exception as exc:
                self.state["last_error"] = str(exc)[:300]
                self._publish("ERROR", self.state["last_error"])
                logger.exception("laboratoire")
            time.sleep(pause_seconds)
