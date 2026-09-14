#!/usr/bin/env bash
# Poll ponctuel de l'etat du build EAS, jusqu'a un statut terminal.
set -euo pipefail
cd "$(dirname "$0")"

ID="${1:-556bf456-9d7f-4926-8f9a-e793a498a181}"
JETON=$(python3 -c "
import re
with open('../.env') as f:
    c = f.read()
print(re.search(r'^EXPO_TOKEN=(.+)\$', c, re.M).group(1).strip())
")

dernier=""
while true; do
  statut=$(EXPO_TOKEN="$JETON" node /home/ubuntu/.npm/_npx/e25a38a8cc65d08e/node_modules/eas-cli/bin/run \
    build:view "$ID" 2>/dev/null | grep -m1 "^Status" | awk -F'  +' '{print $2}')
  if [ "$statut" != "$dernier" ]; then
    echo "statut : $statut"
    dernier="$statut"
  fi
  case "$statut" in
    finished|errored|canceled) exit 0 ;;
  esac
  sleep 60
done
