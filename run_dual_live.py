#!/usr/bin/env python3
"""Run live Bitvavo + IBKR engines with a hard IBKR readiness gate.

IBKR is never launched until IB Gateway's API socket is actually listening.
If Gateway disappears, the IBKR child is stopped and kept stopped until the
socket comes back. This prevents the previous 5-second crash/restart loop.
"""
from __future__ import annotations

import os
import signal
import socket
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
IBKR_HOST = os.environ.get("IBKR_HOST", "127.0.0.1")
IBKR_PORT = int(os.environ.get("IBKR_PORT", "4001"))


def log(msg: str) -> None:
    print(f"[DUAL] {msg}", flush=True)


def ibkr_api_ready() -> bool:
    """Return True only when IB Gateway's TCP API endpoint accepts a socket."""
    try:
        with socket.create_connection((IBKR_HOST, IBKR_PORT), timeout=2):
            return True
    except (OSError, TimeoutError):
        return False


def stop_child(name: str) -> None:
    proc = procs.get(name)
    if not proc or proc.poll() is not None:
        return
    log(f"arret {name}: dependance IBKR non prete")
    try:
        proc.terminate()
    except ProcessLookupError:
        pass
    deadline = time.time() + 15
    while proc.poll() is None and time.time() < deadline:
        time.sleep(0.2)
    if proc.poll() is None:
        proc.kill()


def stop_all(signum=None, frame=None) -> None:
    global stopping
    if stopping:
        return
    stopping = True
    log(f"arret demande ({signum}); arret propre des deux moteurs")
    for proc in procs.values():
        if proc.poll() is None:
            try:
                proc.terminate()
            except ProcessLookupError:
                pass
    deadline = time.time() + 55
    while time.time() < deadline:
        if not any(p.poll() is None for p in procs.values()):
            return
        time.sleep(0.25)
    for proc in procs.values():
        if proc.poll() is None:
            proc.kill()


def start(name: str) -> None:
    if name == "ibkr" and not ibkr_api_ready():
        return
    env = os.environ.copy()
    if name == "ibkr":
        env["IBKR_HOST"] = IBKR_HOST
        env["IBKR_PORT"] = str(IBKR_PORT)
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

    # Bitvavo can start independently. IBKR is deliberately gated on the
    # real Gateway socket and is NOT crash-looped while Gateway is offline.
    start("bitvavo")
    last_ibkr_state = None

    while not stopping:
        ready = ibkr_api_ready()
        ibkr_proc = procs.get("ibkr")
        ibkr_alive = ibkr_proc is not None and ibkr_proc.poll() is None

        if not ready:
            if last_ibkr_state is not False:
                log(f"IBKR EN ATTENTE: Gateway API {IBKR_HOST}:{IBKR_PORT} indisponible; aucun moteur IBKR lance")
            last_ibkr_state = False
            if ibkr_alive:
                stop_child("ibkr")
        else:
            if last_ibkr_state is not True:
                log(f"IBKR API PRETE sur {IBKR_HOST}:{IBKR_PORT}; lancement du moteur IBKR")
            last_ibkr_state = True
            if not ibkr_alive:
                start("ibkr")
                time.sleep(2)
                continue

        bitvavo = procs.get("bitvavo")
        if bitvavo is None or bitvavo.poll() is not None:
            log("bitvavo s'est arrete; redemarrage")
            start("bitvavo")

        time.sleep(3)

    stop_all()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
