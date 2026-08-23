#!/usr/bin/env bash
#
# Finalisation guidee du robot, de la cle API au service qui tourne.
#
#     bash finaliser.sh
#
# Le script VERIFIE a chaque etape et s'arrete au premier probleme en
# expliquant quoi faire. Il ne passe JAMAIS en argent reel tout seul :
# BITVAVO_DRY_RUN=0 reste une decision manuelle, expliquee a la fin.

set -u

DOSSIER="$(cd "$(dirname "$0")" && pwd)"
cd "$DOSSIER" || exit 1

VERT="\033[0;32m"; ROUGE="\033[0;31m"; JAUNE="\033[0;33m"
BLEU="\033[1;36m"; GRAS="\033[1m"; FIN="\033[0m"

etape()  { echo -e "\n${BLEU}${GRAS}== $1 ==${FIN}"; }
ok()     { echo -e "  ${VERT}OK${FIN}    $1"; }
souci()  { echo -e "  ${ROUGE}STOP${FIN}  $1"; }
info()   { echo -e "  ${JAUNE}i${FIN}     $1"; }
fatal()  { souci "$1"; echo -e "\n  ${GRAS}Corrige ce point puis relance : bash finaliser.sh${FIN}\n"; exit 1; }


# ---------------------------------------------------------------------------
etape "1/6  Code a jour"
BRANCHE="claude/gold-trading-system-auto-6boe8m"
if git rev-parse --git-dir >/dev/null 2>&1; then
    git fetch origin "$BRANCHE" --quiet 2>/dev/null
    if git merge-base --is-ancestor "origin/$BRANCHE" HEAD 2>/dev/null; then
        ok "deja a jour"
    else
        git pull origin "$BRANCHE" --quiet 2>/dev/null && ok "mis a jour" \
            || info "impossible de mettre a jour (reseau ?) — on continue"
    fi
else
    info "pas un depot git — on continue"
fi

# ---------------------------------------------------------------------------
etape "2/6  Tests"
if python3 -c "import pytest" 2>/dev/null; then
    SORTIE=$(python3 run_tests.py 2>&1 | tail -3)
    echo "$SORTIE" | sed 's/^/       /'
    # « 3 failed, 439 passed » contient « passed » : chercher ce mot seul
    # laissait passer une suite en echec.
    echo "$SORTIE" | grep -qE "(failed|error)" && fatal "des tests echouent — ne pas aller plus loin"
    echo "$SORTIE" | grep -q "passed" || fatal "aucun test execute"
    ok "suite complete au vert"
else
    info "pytest absent : sudo apt-get install -y python3-pytest"
    info "la suite ne sera que partiellement executee"
    python3 run_tests.py 2>&1 | tail -6 | sed 's/^/       /'
fi

# ---------------------------------------------------------------------------
etape "3/6  Cles API"
[ -f .env ] || fatal "fichier .env absent. Cree-le : cp .env.example .env"

# Les valeurs ne sont JAMAIS affichees, seulement leur longueur.
set -a; . ./.env 2>/dev/null; set +a

manquantes=""
for v in BITVAVO_API_KEY BITVAVO_API_SECRET; do
    eval "val=\${$v:-}"
    if [ -z "$val" ]; then
        manquantes="$manquantes $v"
    else
        ok "$v present (${#val} caracteres)"
    fi
done
[ -z "$manquantes" ] || fatal "manquant dans .env :$manquantes  (edite avec : nano .env)"

# La configuration se lit dans le FICHIER, pas dans l'environnement.
# Un `. ./.env` fait plus tot dans le meme terminal laisse une variable
# exportee qui survit a la modification du fichier : le script lisait
# alors l'ancienne plateforme en croyant lire la nouvelle.
CONFIG=$(grep -E "^GB_CONFIG=" .env 2>/dev/null | tail -1 | cut -d= -f2- | tr -d " \"'")
CONFIG="$(basename "${CONFIG:-robot.bitvavo.json}")"

DRY="${BITVAVO_DRY_RUN:-1}"
if [ "$DRY" = "0" ]; then
    echo -e "  ${ROUGE}${GRAS}!! BITVAVO_DRY_RUN=0 : LES ORDRES SERONT REELS !!${FIN}"
else
    ok "BITVAVO_DRY_RUN=$DRY — aucun ordre ne partira"
fi

# ---------------------------------------------------------------------------
etape "4/6  Connexion a Bitvavo"
if [ -f "$CONFIG" ]; then
    ok "configuration lue : $CONFIG"
else
    souci "configuration introuvable : $CONFIG"
    info "corrige GB_CONFIG dans .env, ou supprime la ligne"
    exit 1
fi
export GB_CONFIG="$CONFIG"
python3 - <<'PYEOF'
import logging, sys
logging.disable(logging.CRITICAL)
sys.path.insert(0, ".")
from gold_bot.brokers.bitvavo import BitvavoBroker, BitvavoConfig
cfg = BitvavoConfig.from_env()
cfg.dry_run = True                     # lecture seule, toujours
b = BitvavoBroker(cfg)
if not b.connect():
    print(f"       ECHEC : {b._last_error}")
    sys.exit(1)
c = b.account()
print(f"       solde        : {c.equity:.2f} {cfg.quote_asset} "
      f"(disponible {c.margin_free:.2f})")
print(f"       marches      : {len(b._regles)} cotables en {cfg.quote_asset}")
print(f"       tarif taker  : {cfg.fee_rate*100:.4f} % "
      f"({cfg.fee_rate*200:.4f} % aller-retour)")
ticket = b.notionnel_minimum()
print(f"       ticket mini  : {ticket:.2f} {cfg.quote_asset}")

from gold_bot.calibrage import calibrer
from gold_bot.settings import BotConfig
import os
conf = BotConfig.load(os.getenv("GB_CONFIG", "robot.bitvavo.json"))
cal = calibrer(c.equity, ticket, cfg.fee_rate,
               conf.risk.base_risk_pct, conf.risk.max_risk_pct,
               conf.risk.max_cost_ratio_pct, conf.risk.max_positions,
               conf.risk.max_capital_engaged_pct)
print()
for l in cal.resume():
    print(f"       {l}")
sys.exit(0 if cal.viable else 2)
PYEOF
code=$?
if [ $code -eq 1 ]; then
    souci "connexion refusee. Causes frequentes, dans l'ordre :"
    echo "         1. cle ou secret mal recopies (espace en trop)"
    echo "         2. cle restreinte a une IP qui n'est pas 92.222.90.65"
    echo "         3. horloge du serveur decalee  ->  timedatectl"
    echo "         4. droit « Trade » non coche sur la cle"
    exit 1
elif [ $code -eq 2 ]; then
    souci "capital insuffisant pour cette plateforme (voir ci-dessus)"
    info "le robot refusera de trader plutot que de forcer — c'est voulu"
    exit 1
fi
ok "connexion etablie, calibrage calcule"

# ---------------------------------------------------------------------------
etape "5/6  Un balayage reel des 85 cryptos"
info "analyse en cours, compte une a deux minutes..."
timeout 600 python3 run_bot.py scan --config "$CONFIG" 2>&1 \
    | grep -vE "nouvelle journee|INFO gold_bot.datasources" | tail -25 | sed 's/^/       /'
ok "balayage termine"

# ---------------------------------------------------------------------------
etape "6/6  Service"
echo
echo -e "  Le robot est pret. Pour le faire tourner en continu :"
echo
echo -e "      ${GRAS}echo 'GB_CONFIG=$CONFIG' >> .env${FIN}"
echo -e "      ${GRAS}sudo bash service.sh installer${FIN}"
echo -e "      ${GRAS}sudo bash service.sh demarrer${FIN}"
echo -e "      ${GRAS}bash service.sh journal${FIN}       (suivre en direct, Ctrl+C pour sortir)"
echo
echo -e "  ${JAUNE}Il tournera en SIMULATION.${FIN} Il analyse, decide et journalise,"
echo -e "  sans envoyer un seul ordre. C'est ce qui va nourrir l'apprentissage :"
echo -e "  la ponderation demarre neutre et n'apprend qu'avec des trades fermes."
echo
echo -e "  ${GRAS}Quand tu voudras passer en reel — et seulement quand tu l'auras decide :${FIN}"
echo
echo -e "      1. ${GRAS}nano .env${FIN}   puis mettre  BITVAVO_DRY_RUN=0"
echo -e "      2. ${GRAS}python3 verifier_bitvavo.py --confirmer${FIN}"
echo -e "         un aller-retour reel d'environ 10 EUR, cout ~0,05 EUR,"
echo -e "         visible dans ton historique Bitvavo. C'est la preuve."
echo -e "      3. ${GRAS}sudo bash service.sh demarrer${FIN}"
echo
