#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/ubuntu/Eve-AI-Influencer
VENV="$ROOT/.venv"
SERVICE=/etc/systemd/system/robot-dual-live.service

cd "$ROOT"
git fetch origin
git reset --hard origin/claude/gold-trading-system-auto-6boe8m

# Ubuntu 26.04 enforces PEP 668: keep all Python packages in a venv.
if [ ! -x "$VENV/bin/python" ]; then
  sudo apt-get update -qq
  sudo apt-get install -y -qq python3-venv python3-full >/dev/null
  python3 -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install -q --disable-pip-version-check --upgrade pip
"$VENV/bin/python" -m pip install -q --disable-pip-version-check ib_async

# Install the service file FIRST; it may not exist on a fresh VPS.
sudo install -m 0644 "$ROOT/ops/robot-dual-live.service" "$SERVICE"

# Always use the isolated interpreter and force LIVE broker modes.
sudo sed -i "s#^ExecStart=.*#ExecStart=$VENV/bin/python $ROOT/run_dual_live.py#" "$SERVICE"
sudo sed -i '/^Environment=IBKR_PORT=/d;/^Environment=IBKR_TRADING_LIVE=/d;/^Environment=IBKR_ALLOW_SHORT=/d;/^Environment=BITVAVO_DRY_RUN=/d' "$SERVICE"
sudo sed -i '/^EnvironmentFile=/a Environment=IBKR_PORT=4001\nEnvironment=IBKR_TRADING_LIVE=1\nEnvironment=IBKR_ALLOW_SHORT=1\nEnvironment=BITVAVO_DRY_RUN=0' "$SERVICE"

# Avoid the old single-broker services fighting the dual supervisor.
sudo systemctl disable --now robot-trading.service 2>/dev/null || true
sudo systemctl disable --now gold-bot.service 2>/dev/null || true

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
echo "===== IB API PORTS ====="
ss -ltnp | grep -E ':400[0-9]\\b' || echo 'AUCUN PORT IB 400x EN ECOUTE'
echo
echo "===== LIVE LOG ====="
sudo journalctl -u robot-dual-live.service -n 120 --no-pager
