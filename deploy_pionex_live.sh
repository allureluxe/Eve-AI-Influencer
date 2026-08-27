#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$(readlink -f "$0")")"

BRANCH="claude/gold-trading-system-auto-6boe8m"

echo "===== SYNCHRONISATION GITHUB ====="
git fetch origin "$BRANCH"
git checkout "$BRANCH"
git reset --hard "origin/$BRANCH"

echo "===== COMPILATION ====="
python3 -m py_compile gold_bot/*.py gold_bot/brokers/*.py run_pionex.py verifier_pionex.py
echo "PYCOMPILE OK"

echo "===== PREFLIGHT PIONEX FUTURES (AUCUN ORDRE) ====="
python3 verifier_pionex.py

echo "===== SERVICE ====="
sudo systemctl daemon-reload
sudo systemctl restart gold-bot
sleep 8

if ! sudo systemctl is-active --quiet gold-bot; then
  echo "SERVICE FAILED"
  sudo journalctl -u gold-bot -n 80 --no-pager -o cat
  exit 1
fi

echo "===== BOT ACTIF ====="
sudo systemctl status gold-bot --no-pager -l

echo "===== LOGS RECENTS ====="
sudo journalctl -u gold-bot --since "30 seconds ago" --no-pager -o cat
