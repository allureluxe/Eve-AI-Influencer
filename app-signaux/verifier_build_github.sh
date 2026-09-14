#!/usr/bin/env bash
# Poll ponctuel de l'etat d'une construction GitHub Actions (depot public,
# aucun jeton necessaire), jusqu'a un statut terminal.
set -euo pipefail

ID="${1:?usage: verifier_build_github.sh <run_id>}"

dernier=""
while true; do
  statut=$(curl -s "https://api.github.com/repos/allureluxe/Eve-AI-Influencer/actions/runs/$ID" \
    | python3 -c "import json,sys; d=json.load(sys.stdin); print(f\"{d.get('status')}:{d.get('conclusion')}\")")
  if [ "$statut" != "$dernier" ]; then
    echo "statut : $statut"
    dernier="$statut"
  fi
  case "$statut" in
    completed:*) exit 0 ;;
  esac
  sleep 30
done
