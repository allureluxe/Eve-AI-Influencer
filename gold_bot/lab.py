"""Strategy Lab -- laboratoire autonome inspire des principes publics d'AITradingArena.

Aucun ordre n'est envoye. Le labo utilise uniquement Backtester/PaperBroker,
garde les echecs, deduplique les configurations et separe backtest et
forward-test. Les strategies validees restent en incubation/paper: elles ne
sont jamais branchees automatiquement sur le compte reel.
"""
from __future__ import annotations
import copy, hashlib, json, logging, os, time, urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path
from .backtest import Backtester
from .backtest_portefeuille import BacktestPortefeuille

logger = logging.getLogger(__name__)
BAR_BACKTEST = 1200
BAR_FORWARD = 240
MIN_TRADES = 100
MIN_PF = 1.20
MIN_WIN = 40.0
MIN_PAYOFF = 1.0
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
    "prospector-breakout": [
        {"name": "donchian_10", "famille": "momentum", "donchian_entrees": [10], "donchian_sortie": 10},
        {"name": "donchian_20", "famille": "momentum", "donchian_entrees": [20], "donchian_sortie": 10},
    ],
    "prospector-filter": [
        {"name": "adx_16", "min_adx": 16.0},
        {"name": "adx_20", "min_adx": 20.0},
    ],
    "risk-refiner": [
        {"name": "rr_18", "min_rr": 1.8},
        {"name": "rr_22", "min_rr": 2.2},
    ],
    "volatility-refiner": [
        {"name": "atr_stop_18", "atr_stop_mult": 1.8},
        {"name": "atr_stop_22", "atr_stop_mult": 2.2},
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

def _apply(cfg, params):
    for key, value in params.items():
        if key == "name":
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
        self._publish("IDLE", "Laboratoire pret")

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

    def _record(self, c):
        with LAB_BOOK.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(c), ensure_ascii=False) + "\n")
        self._supabase("lab_strategies", {
            "strategy_id": c.id, "agent": c.agent, "parent_id": c.parent_id,
            "stage": c.stage, "fingerprint": c.fingerprint, "params": c.params,
            "backtest": c.backtest, "forward_test": c.forward, "reason": c.reason,
        })

    def _seen(self, fp):
        if not LAB_BOOK.exists():
            return False
        return any(f'"fingerprint": "{fp}"' in line for line in LAB_BOOK.read_text(encoding="utf-8").splitlines())

    def run_candidate(self, agent, params, parent_id=None):
        fp = fingerprint(params)
        if self._seen(fp):
            return None
        cid = f"{agent}-{fp}"
        self.state["current"] = cid
        self._publish("IDEATED", f"{agent}: {params.get('name', 'strategy')}")
        cfg = _apply(copy.deepcopy(self.base), params)

        # Full history minus the latest forward window. This prevents the
        # forward period from influencing the candidate gate.
        # IMPORTANT : un seul compte virtuel pour tout l'univers. Le Lab ne
        # doit plus donner le capital entier a chaque crypto puis additionner
        # les profits : le portefeuille partage cash, risque et positions.
        self._publish("BACKTEST", f"{cid}: portefeuille historique")
        start_balance = float(cfg.engine.start_balance)
        try:
            porte = BacktestPortefeuille(cfg).run(
                list(LAB_SYMBOLS), bars=BAR_BACKTEST,
                start_balance=start_balance, decalage=BAR_FORWARD)
            bt = _stats_portefeuille(porte, start_balance)
        except Exception as exc:
            logger.warning("backtest portefeuille %s: %s", cid, str(exc)[:200])
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
                porte_fw = BacktestPortefeuille(cfg).run(
                    list(LAB_SYMBOLS), bars=BAR_FORWARD,
                    start_balance=start_balance, decalage=0)
                c.forward = _stats_portefeuille(porte_fw, start_balance)
            except Exception as exc:
                logger.warning("forward portefeuille %s: %s", cid, str(exc)[:200])
                c.forward = {"symbols_tested": 0, "trades": 0, "wins": 0, "losses": 0,
                             "win_rate": 0.0, "profit_factor": 0.0, "payoff": 0.0,
                             "profit": 0.0, "start_balance": start_balance,
                             "end_balance": start_balance, "portfolio_mode": True,
                             "error": str(exc)[:300]}
            forward_pass = (
                c.forward["trades"] >= MIN_TRADES
                and c.forward["profit_factor"] >= MIN_PF
                and c.forward["win_rate"] >= MIN_WIN
                and c.forward["payoff"] > MIN_PAYOFF
            )
            if forward_pass:
                c.stage, c.reason = "VALIDATED", "backtest + forward test franchis"
                self.state["validated"] += 1
                self.state["forward_passed"] += 1
            elif c.forward["trades"] < MIN_TRADES:
                c.stage, c.reason = "INCUBATION", "forward insuffisant"
            else:
                c.stage, c.reason = "RETIRED-WEAK", "forward bar non franchie"
            self._record(c)

        self.state["current"] = None
        self._publish(c.stage, c.reason)
        return c

    def cycle(self):
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
            p["min_rr"] = round(1.2 + ((round_no * 0.1) % 1.9), 2)
        elif agent == "volatility-refiner":
            p["atr_stop_mult"] = round(1.2 + ((round_no * 0.2) % 1.8), 2)
        elif agent == "timeframe-refiner":
            tfs = [("M5","M15"), ("M15","H1"), ("H1","H4"), ("H4","D1")]
            entry, context = tfs[(round_no - 1) % len(tfs)]
            p["entry_tf"], p["trigger_tf"] = entry, entry
            p["context_tf"], p["bias_tf"] = context, context
        p["name"] = f"{name}_v{round_no}"
        return self.run_candidate(agent, p)

    def loop(self, pause_seconds=60):
        while True:
            try:
                self.cycle()
            except Exception as exc:
                self.state["last_error"] = str(exc)[:300]
                self._publish("ERROR", self.state["last_error"])
                logger.exception("laboratoire")
            time.sleep(pause_seconds)
