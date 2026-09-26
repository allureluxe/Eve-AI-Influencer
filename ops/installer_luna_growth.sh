#!/usr/bin/env bash
set -euo pipefail

RACINE="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE_DIR="/etc/systemd/system"

sudo cp "$RACINE/systemd/luna-planner.service" "$SERVICE_DIR/luna-planner.service"
sudo cp "$RACINE/systemd/luna-planner.timer" "$SERVICE_DIR/luna-planner.timer"
sudo systemctl daemon-reload
sudo systemctl enable --now luna-planner.timer

echo "Luna growth planner actif."
sudo systemctl status luna-planner.timer --no-pager
