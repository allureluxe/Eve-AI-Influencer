#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/ubuntu/Eve-AI-Influencer
VENV="$ROOT/.venv"
SERVICE=/etc/systemd/system/robot-dual-live.service

cd "$ROOT"
git fetch origin
git reset --hard origin/claude/gold-trading-system-auto-6boe8m

# Ubuntu 26.04 enforces PEP 668. Never install into the system Python.
if [ ! -x "$VENV/bin/python" ]; then
  sudo apt-get update -qq
  sudo apt-get install -y -qq python3-venv python3-full >/dev/null
  python3 -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install -q --disable-pip-version-check --upgrade pip
"$VENV/bin/python" -m pip install -q --disable-pip-version-check ib_async

# Make the service use the same isolated interpreter.
sudo sed -i "s#^ExecStart=.*#ExecStart=$VENV/bin/python $ROOT/run_dual_live.py#" "$SERVICE"

# The old services were not a dual broker supervisor and could be stopped
# together, leaving the real Bitvavo bot dead. Disable them to avoid conflicts.
sudo systemctl disable --now robot-trading.service 2>/dev/null || true
sudo systemctl disable --now gold-bot.service 2>/dev/null || true

sudo install -m 0644 "$ROOT/ops/robot-dual-live.service" "$SERVICE"
# install above restores the committed service file; patch ExecStart again.
sudo sed -i "s#^ExecStart=.*#ExecStart=$VENV/bin/python $ROOT/run_dual_live.py#" "$SERVICE"
sudo systemctl daemon-reload
sudo systemctl enable robot-dual-live.service
sudo systemctl restart robot-dual-live.service

sleep 8

echo "===== DUAL SERVICE ====="
sudo systemctl status robot-dual-live.service --no-pager -l

echo
echo "===== PROCESSES ====="
ps -ef | grep -E 'run_dual_live|run_dual_scalping|ibgateway|GWClient' | grep -v grep || true

echo
echo "===== IB API PORT ====="
ss -ltnp | grep -E ':4001\\b' || echo 'IB Gateway n''ecoute pas encore sur 4001'
echo
echo "===== LIVE LOG ====="
sudo journalctl -u robot-dual-live.service -n 120 --no-pager
