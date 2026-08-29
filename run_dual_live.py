#!/usr/bin/env python3
from __future__ import annotations

import logging
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = str(ROOT / ".venv/bin/python") if (ROOT / ".venv/bin/python").exists() else sys.executable
LOG = logging.getLogger("dual-live")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

children: list[subprocess.Popen] = []


def ibkr_ready(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except OSError:
        return False


def stop_all(*_args) -> None:
    for p in children:
        if p.poll() is None:
            p.send_signal(signal.SIGTERM)
    deadline = time.time() + 10
    while time.time() < deadline and any(p.poll() is None for p in children):
        time.sleep(0.2)
    for p in children:
        if p.poll() is None:
            p.kill()


def start(config: str) -> subprocess.Popen:
    cmd = [PY, str(ROOT / "run_dual_scalping.py"), "--config", str(ROOT / config)]
    LOG.info("demarrage %s", " ".join(cmd))
    return subprocess.Popen(cmd, cwd=ROOT, env=os.environ.copy())


def main() -> int:
    signal.signal(signal.SIGTERM, stop_all)
    signal.signal(signal.SIGINT, stop_all)

    children.append(start("robot.bitvavo.json"))

    host = os.getenv("IBKR_HOST", "127.0.0.1")
    port = int(os.getenv("IBKR_PORT", "4001"))
    for _ in range(120):
        if ibkr_ready(host, port):
            LOG.info("IBKR API PRETE sur %s:%d", host, port)
            children.append(start("robot.ibkr.json"))
            break
        time.sleep(1)
    else:
        LOG.warning("IBKR API indisponible sur %s:%d: moteur IBKR non lance", host, port)

    try:
        while children:
            alive = [p for p in children if p.poll() is None]
            if not alive:
                return 1
            children[:] = alive
            time.sleep(2)
    finally:
        stop_all()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
