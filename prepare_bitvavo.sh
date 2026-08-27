#!/usr/bin/env bash
# One-shot migration from the old Pionex service to the hardened Bitvavo setup.
# Safe by design: it stops the old service, updates code/config, runs tests and
# a READ-ONLY Bitvavo preflight, installs the Bitvavo service, but DOES NOT START IT.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
BRANCH="claude/gold-trading-system-auto-6boe8m"
cd "$ROOT"

sudo systemctl stop gold-bot.service 2>/dev/null || true
sudo systemctl disable gold-bot.service 2>/dev/null || true
sudo systemctl stop robot-trading.service 2>/dev/null || true
sudo systemctl disable robot-trading.service 2>/dev/null || true

cp -a .env ".env.backup.$(date +%Y%m%d-%H%M%S)" 2>/dev/null || true
git pull --ff-only origin "$BRANCH"

if grep -q '^GB_CONFIG=' .env 2>/dev/null; then
  sed -i 's|^GB_CONFIG=.*|GB_CONFIG=robot.bitvavo.json|' .env
else
  printf '\nGB_CONFIG=robot.bitvavo.json\n' >> .env
fi
if grep -q '^BITVAVO_DRY_RUN=' .env 2>/dev/null; then
  sed -i 's|^BITVAVO_DRY_RUN=.*|BITVAVO_DRY_RUN=1|' .env
else
  printf 'BITVAVO_DRY_RUN=1\n' >> .env
fi
if grep -q '^BITVAVO_QUOTE_ASSET=' .env 2>/dev/null; then
  sed -i 's|^BITVAVO_QUOTE_ASSET=.*|BITVAVO_QUOTE_ASSET=EUR|' .env
else
  printf 'BITVAVO_QUOTE_ASSET=EUR\n' >> .env
fi

python3 -m json.tool robot.bitvavo.json >/dev/null
python3 -m py_compile run_bitvavo.py gold_bot/settings.py gold_bot/engine.py gold_bot/strategy.py gold_bot/brokers/bitvavo.py gold_bot/brokers/bitvavo_hardening.py
python3 run_tests.py

set -a
. ./.env
set +a
python3 - <<'PY'
from gold_bot.brokers import BitvavoBroker, BitvavoConfig
from gold_bot.settings import BotConfig

cfg = BitvavoConfig.from_env()
cfg.dry_run = True
if not cfg.api_key or not cfg.api_secret:
    raise SystemExit("BITVAVO_API_KEY / BITVAVO_API_SECRET manquants")

b = BitvavoBroker(cfg)
if not b.connect():
    raise SystemExit("PRECHECK BITVAVO ECHEC: " + (b._last_error or "connexion refusee"))

account = b.account()
print(f"BITVAVO OK | solde={account.equity:.2f} {account.currency} | disponible={account.margin_free:.2f}")
print(f"MARCHES EUR={len(b._regles)}")
print("MODE=DRY_RUN | AUCUN ORDRE")

bot = BotConfig.load("robot.bitvavo.json")
problems = bot.validate()
if problems:
    raise SystemExit("CONFIG INVALIDE: " + " | ".join(problems))
print("CONFIG=OK")
PY

sudo install -m 644 deploy/gold-bot.service /etc/systemd/system/gold-bot.service
sudo systemctl daemon-reload
sudo systemctl enable gold-bot.service >/dev/null
sudo systemctl reset-failed gold-bot.service 2>/dev/null || true

printf '\nREADY: Bitvavo est installe, teste en lecture seule et le service reste ARRETE.\n'
printf 'Pour le test 24h reel, mettre BITVAVO_DRY_RUN=0 apres le depot puis demarrer gold-bot.service.\n'
