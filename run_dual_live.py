#!/usr/bin/env python3
"""Run the live Bitvavo and IBKR engines as one supervised process.

Both brokers keep independent state/journals because TradingEngine keys
persistence by cfg.engine.broker. A failure/restart of one child does not
silently disable the other; the supervisor restarts failed children.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PYTHON = sys.executable or "/usr/bin/python3"
CHILDREN = {
    "bitvavo": [PYTHON, str(ROOT / "run_dual_scalping.py"), "--config", str(ROOT / "robot.bitvavo.json")],
    "ibkr": [PYTHON, str(ROOT / "run_dual_scalping.py"), "--config", str(ROOT / "robot.ibkr.json")],
}

procs: dict[str, subprocess.Popen] = {}
stopping = False


def log(msg: str) -> None:
    print(f"[DUAL] {msg}", flush=True)


def stop_all(signum=None, frame=None) -> None:
    global stopping
    if stopping:
        return
    stopping = True
    log(f"arret demande ({signum}); arret propre des deux moteurs")
    for name, proc in list(procs.items()):
        if proc.poll() is None:
            try:
                proc.terminate()
            except ProcessLookupError:
                pass
    deadline = time.time() + 55
    while time.time() < deadline:
        alive = [p for p in procs.values() if p.poll() is None]
        if not alive:
            return
        time.sleep(0.25)
    for proc in procs.values():
        if proc.poll() is None:
            proc.kill()


def start(name: str) -> None:
    env = os.environ.copy()
    if name == "ibkr":
        # IB Gateway live socket is 4001. Explicitly override the old 4000
        # value that previously prevented the bot from reaching Gateway.
        env["IBKR_HOST"] = env.get("IBKR_HOST", "127.0.0.1")
        env["IBKR_PORT"] = "4001"
        env["IBKR_TRADING_LIVE"] = "1"
        env["IBKR_ALLOW_SHORT"] = "1"
    elif name == "bitvavo":
        env["BITVAVO_DRY_RUN"] = "0"
    log(f"demarrage {name}: {' '.join(CHILDREN[name])}")
    procs[name] = subprocess.Popen(CHILDREN[name], cwd=ROOT, env=env)


def main() -> int:
    signal.signal(signal.SIGTERM, stop_all)
    signal.signal(signal.SIGINT, stop_all)
    signal.signal(signal.SIGHUP, stop_all)

    for name in CHILDREN:
        start(name)

    while not stopping:
        for name, proc in list(procs.items()):
            code = proc.poll()
            if code is not None:
                log(f"{name} s'est arrete (code={code}); redemarrage dans 5s")
                if not stopping:
                    time.sleep(5)
                    start(name)
        time.sleep(1)

    stop_all()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
