#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/ubuntu/Eve-AI-Influencer
SERVICE=/etc/systemd/system/robot-dual-live.service

cd "$ROOT"
git fetch origin
git reset --hard origin/claude/gold-trading-system-auto-6boe8m

python3 -m pip install -q --disable-pip-version-check ib_async

# The old service was Bitvavo-only and was manually stopped together with the
# Pionex service. Disable it so it cannot compete with the dual supervisor.
sudo systemctl disable --now robot-trading.service 2>/dev/null || true
sudo systemctl disable --now gold-bot.service 2>/dev/null || true

sudo install -m 0644 "$ROOT/ops/robot-dual-live.service" "$SERVICE"
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
