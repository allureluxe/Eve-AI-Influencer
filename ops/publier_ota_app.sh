#!/usr/bin/env bash
# Publie une mise a jour OTA d'Alluxe Bot (changements JS/TS seulement).
#
#     bash ops/publier_ota_app.sh "message de la mise a jour"
#
# Le telephone la telecharge a l'ouverture suivante de l'application et
# l'applique a l'ouverture d'apres. Un changement NATIF (dependance native,
# permission, plugin, `version` dans app.config.js) exige un nouvel APK :
# l'OTA ne s'appliquerait pas (runtimeVersion = version de l'app).
# Le jeton EXPO_TOKEN est lu dans .env, jamais affiche.
set -euo pipefail
cd "$(dirname "$0")/.."
message="${1:?usage : bash ops/publier_ota_app.sh \"message\"}"
EXPO_TOKEN="$(grep -m1 '^EXPO_TOKEN=' .env | cut -d= -f2-)"
export EXPO_TOKEN
cd app-alluxe-bot
npx tsc --noEmit -p tsconfig.json --pretty false
npx -y eas-cli@latest update --channel production --platform android \
  --message "$message" --non-interactive
