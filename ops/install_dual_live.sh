#!/usr/bin/env bash
set -euo pipefail

ROOT=/home/ubuntu/Eve-AI-Influencer
VENV="$ROOT/.venv"
SERVICE=/etc/systemd/system/robot-dual-live.service

# La branche etait ecrite en dur. Deux branches vivent dans ce depot, et
# deployer la mauvaise reinstalle silencieusement une version anterieure du
# robot — sans erreur, sans message : le service redemarre simplement avec
# l'ancien code. Elle est donc nommee ici, et surchargeable :
#   BRANCHE=... ./ops/install_dual_live.sh
BRANCHE="${BRANCHE:-claude/bitvavo-ibkr-integration-waiac5}"

cd "$ROOT"
git fetch origin "$BRANCHE"
git reset --hard "origin/$BRANCHE"
echo "== code deploye : $BRANCHE @ $(git rev-parse --short HEAD) =="

# Ubuntu 26.04 enforces PEP 668: keep all Python packages in a venv.
if [ ! -x "$VENV/bin/python" ]; then
  sudo apt-get update -qq
  sudo apt-get install -y -qq python3-venv python3-full >/dev/null
  python3 -m venv "$VENV"
fi
"$VENV/bin/python" -m pip install -q --disable-pip-version-check --upgrade pip
# La version d'ib_async est epinglee dans requirements-ibkr.txt : l'installer
# sans borne ferait arriver une version majeure incompatible sans prevenir.
"$VENV/bin/python" -m pip install -q --disable-pip-version-check -r "$ROOT/requirements-ibkr.txt"

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
ss -ltnp | grep -E ':400[0-9]\b' || echo 'AUCUN PORT IB 400x EN ECOUTE'

echo
echo "===== ETAT REEL DE LA PASSERELLE IBKR ====="
# Un port ouvert ne veut pas dire une session authentifiee : c'est ce
# diagnostic-la qui distingue « Gateway eteinte » de « Gateway en attente
# du code SMS ». Il ne doit pas faire echouer l'installation.
set +e
(set -a; . "$ROOT/.env" 2>/dev/null; set +a; "$VENV/bin/python" "$ROOT/verifier_ibkr.py")
set -e
echo
echo "===== LIVE LOG ====="
sudo journalctl -u robot-dual-live.service -n 120 --no-pager
