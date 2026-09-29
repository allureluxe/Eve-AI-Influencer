#!/usr/bin/env python3
"""Promotion automatique du meilleur candidat VALIDATED vers DEMO 2.

Le labo reste autonome, mais aucune stratégie n'arrive directement sur le
réel. DEMO 2 est un bac d'essai isolé à 1 000 EUR virtuels.
"""
from __future__ import annotations
import json, os, subprocess, time, urllib.request, urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOOK = ROOT / "data/lab-validated.jsonl"
CONFIG = ROOT / "robot.demo2.json"
DEPLOY = ROOT / "data/demo2-strategy.json"
FILES = ["state-demo2.json", "trades-demo2.jsonl", "objectives-demo2.json", "journal-demo2.jsonl", "outbox-demo2.jsonl", "signaux_en_attente_demo2.jsonl"]


def score(x: dict) -> tuple:
    f = x.get("forward") or x.get("forward_test") or {}
    b = x.get("backtest") or {}
    # Le forward est prioritaire : rendement hors echantillon, puis PF,
    # puis drawdown faible, puis rendement historique.
    return (
        float(f.get("return_pct", -1e9)),
        float(f.get("profit_factor", -1e9)),
        -float(f.get("max_drawdown_pct", 1e9)),
        float(b.get("return_pct", -1e9)),
        float(b.get("profit_factor", -1e9)),
    )


def load_validated():
    if not BOOK.exists():
        return []
    out = {}
    with BOOK.open(encoding="utf-8") as fh:
        for line in fh:
            try:
                x = json.loads(line)
                if x.get("stage") == "VALIDATED":
                    out[x["id"]] = x
            except Exception:
                continue
    return list(out.values())


def restart_demo2():
    # Le service est Restart=always : après le SIGKILL de l'ancien processus,
    # systemd relance automatiquement avec la nouvelle configuration.
    # On ne lance pas un second `systemctl restart`, qui peut attendre le
    # vieux processus et expirer pendant son arrêt.
    for _ in range(20):
        state = subprocess.run(["systemctl", "is-active", "robot-demo2.service"], cwd=ROOT, capture_output=True, text=True, timeout=10).stdout.strip()
        if state == "active":
            return
        time.sleep(1)
    raise RuntimeError("robot-demo2 n'est pas redevenu actif après promotion")


def reset_remote_demo2_history():
    """Efface l historique distant de DEMO 2 avant chaque nouvelle strategie.

    Les anciennes donnees restent conservees dans data/demo2-archives/.
    L interface ne doit donc jamais melanger deux strategies dans le meme
    historique : chaque promotion ouvre une nouvelle generation a 1 000 EUR.
    """
    # Charge les memes variables que les autres outils ops.
    from gold_bot.env import charger_env
    charger_env()
    base = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not base or not key:
        raise RuntimeError("identifiants Supabase absents : historique DEMO 2 non remis a zero")
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    for table in ("signals", "alluxe_bot_capital"):
        url = f"{base}/rest/v1/{table}?compte=eq.{urllib.parse.quote('demo2')}"
        req = urllib.request.Request(url, headers=headers, method="DELETE")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                if resp.status not in (200, 204):
                    raise RuntimeError(f"DELETE {table}: HTTP {resp.status}")
        except Exception as exc:
            raise RuntimeError(f"impossible de remettre a zero l historique DEMO 2 ({table}): {exc}") from exc


def promote(best):
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())

    # D'abord sécuriser la transition distante. Si Supabase refuse la remise
    # à zéro, on ne touche ni au processus ni aux fichiers de DEMO2 : l'ancien
    # environnement reste intact et peut continuer à tourner.
    reset_remote_demo2_history()

    # Conserver une copie locale de chaque génération avant de repartir vierge.
    archive = ROOT / "data" / "demo2-archives" / stamp
    archive.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        src = ROOT / "data" / name
        if src.exists():
            src.replace(archive / name)

    # Après la remise à zéro distante, arrêter l'ancien processus. Avec
    # Restart=always, systemd relance ensuite automatiquement la nouvelle config.
    pid = subprocess.run(["systemctl", "show", "robot-demo2.service", "-p", "MainPID", "--value"], cwd=ROOT, capture_output=True, text=True, timeout=15).stdout.strip()
    if pid.isdigit() and int(pid) > 1:
        subprocess.run(["kill", "-9", pid], cwd=ROOT, timeout=10, check=False)
        time.sleep(1)

    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))
    cfg["engine"]["start_balance"] = 1000.0
    cfg["engine"]["dry_run"] = True
    cfg["engine"]["broker"] = "paper"
    params = dict(best.get("params") or {})
    strategy = cfg.setdefault("strategy", {})
    famille = params.get("strategie_famille") or params.get("famille") or strategy.get("famille", "tendance")
    strategy["famille"] = famille
    strategy["strategie_famille"] = famille
    for k, v in params.items():
        if k not in {"name", "famille", "strategie_famille"}:
            # Les paramètres validés sont déjà des paramètres du moteur.
            for section in (strategy, cfg.get("trade", {}), cfg.get("risk", {})):
                if k in section:
                    section[k] = v
                    break
    cfg["_demo2_promotion"] = {
        "strategy_id": best["id"],
        "fingerprint": best["fingerprint"],
        "name": params.get("name", best["id"]),
        "promoted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "capital_initial_eur": 1000.0,
        "history_generation": stamp,
        "history_reset": True,
        "source": "strategy_lab_validated",
    }
    CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    DEPLOY.write_text(json.dumps({
        "strategy_id": best["id"], "fingerprint": best["fingerprint"],
        "name": params.get("name", best["id"]), "params": params,
        "score": score(best), "promoted_at": cfg["_demo2_promotion"]["promoted_at"],
        "capital_initial_eur": 1000.0,
        "history_generation": stamp,
        "history_reset": True,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    restart_demo2()


def main():
    candidates = load_validated()
    if not candidates:
        return
    best = max(candidates, key=score)
    current = json.loads(DEPLOY.read_text(encoding="utf-8")) if DEPLOY.exists() else None
    if current and current.get("fingerprint") == best.get("fingerprint"):
        return
    if current:
        old_score = tuple(current.get("score") or ())
        if old_score and score(best) <= old_score:
            return
    promote(best)

if __name__ == "__main__":
    main()
