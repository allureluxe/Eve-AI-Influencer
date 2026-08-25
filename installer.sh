#!/usr/bin/env bash
#
# Installation guidee du robot de trading.
#
#   bash installer.sh
#
# Le script verifie Python, prepare le fichier de configuration, demande les
# cles necessaires et cree un raccourci de demarrage. Rien n'est envoye nulle
# part : les cles restent dans le fichier .env, sur cette machine.

set -u

VERT="\033[0;32m"; ROUGE="\033[0;31m"; JAUNE="\033[0;33m"; GRAS="\033[1m"; FIN="\033[0m"

titre()   { echo -e "\n${GRAS}$1${FIN}"; echo "------------------------------------------------------------"; }
ok()      { echo -e "  ${VERT}OK${FIN}   $1"; }
souci()   { echo -e "  ${ROUGE}STOP${FIN} $1"; }
info()    { echo -e "  ${JAUNE}i${FIN}    $1"; }

cd "$(dirname "$0")" || exit 1

echo -e "${GRAS}"
echo "=============================================="
echo "   INSTALLATION DU ROBOT DE TRADING"
echo "=============================================="
echo -e "${FIN}"

# --------------------------------------------------------------------------
titre "1/5  Verification de Python"

PY=""
for candidat in python3 python; do
    if command -v "$candidat" >/dev/null 2>&1; then
        version=$("$candidat" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null)
        majeur=${version%%.*}; mineur=${version##*.}
        if [ "$majeur" = "3" ] && [ "$mineur" -ge 10 ] 2>/dev/null; then
            PY="$candidat"; ok "Python $version trouve ($candidat)"; break
        fi
    fi
done

if [ -z "$PY" ]; then
    souci "Python 3.10 ou plus recent est necessaire."
    echo "       Telechargement : https://www.python.org/downloads/"
    echo "       Sur Ubuntu/Debian : sudo apt install python3"
    echo "       Sur Mac : brew install python3"
    exit 1
fi

info "Le robot n'a besoin d'aucune autre installation."

# --------------------------------------------------------------------------
titre "2/5  Fichier de configuration"

if [ -f .env ]; then
    ok "Le fichier .env existe deja, il est conserve."
    info "Pour repartir de zero : supprimez-le puis relancez ce script."
else
    cp .env.example .env
    ok "Fichier .env cree a partir du modele."
fi

ecrire_valeur() {
    # ecrire_valeur NOM VALEUR  (sans question, pour les reglages non secrets)
    local nom="$1" valeur="$2" tmp
    if grep -qE "^${nom}=" .env; then
        tmp=$(mktemp)
        awk -v n="$nom" -v v="$valeur" -F= '$1==n {print n "=" v; next} {print}' .env > "$tmp"
        mv "$tmp" .env
    else
        echo "${nom}=${valeur}" >> .env
    fi
}

ecrire_cle() {
    # ecrire_cle NOM_VARIABLE "question" [masquer]
    local nom="$1" question="$2" masquer="${3:-non}" valeur=""
    local actuelle
    actuelle=$(grep -E "^${nom}=" .env 2>/dev/null | head -1 | cut -d= -f2-)

    if [ -n "$actuelle" ] && [[ "$actuelle" != votre_* ]] && [[ "$actuelle" != https://api.moon-x.io ]]; then
        ok "$nom deja renseigne, on garde."
        return
    fi

    if [ "$masquer" = "oui" ]; then
        read -r -s -p "  $question : " valeur; echo
    else
        read -r -p "  $question : " valeur
    fi

    [ -z "$valeur" ] && { info "$nom laisse vide."; return; }

    if grep -qE "^${nom}=" .env; then
        # Substitution compatible Linux et Mac
        tmp=$(mktemp)
        awk -v n="$nom" -v v="$valeur" -F= '$1==n {print n "=" v; next} {print}' .env > "$tmp"
        mv "$tmp" .env
    else
        echo "${nom}=${valeur}" >> .env
    fi
    ok "$nom enregistre."
}

# --------------------------------------------------------------------------
titre "3/5  Plateforme d'execution"

echo "  Ou le robot doit-il passer ses ordres ?"
echo
echo "    1) Binance Futures  (recommande : API publique, testnet gratuit)"
echo "    2) MoonX            (necessite un acces API fourni par leur support)"
echo "    3) Aucune pour l'instant (simulation seulement)"
echo
read -r -p "  Votre choix [1] : " choix_plateforme
choix_plateforme=${choix_plateforme:-1}

case "$choix_plateforme" in
1)
    echo
    echo "  Creez vos cles sur Binance : Profil > Gestion API > Creer une API."
    echo "  Cochez UNIQUEMENT 'Activer les Futures'. Ne cochez JAMAIS les retraits."
    echo "  Pour le testnet (argent fictif) : testnet.binancefuture.com"
    echo
    ecrire_cle "BINANCE_API_KEY"    "Cle API Binance" oui
    ecrire_cle "BINANCE_API_SECRET" "Secret API Binance" oui
    echo
    read -r -p "  Commencer sur le testnet, avec de l'argent fictif ? [O/n] : " testnet
    if [[ "$testnet" =~ ^[Nn] ]]; then
        ecrire_valeur "BINANCE_TESTNET" "0"
        echo -e "  ${ROUGE}ATTENTION${FIN} : mode reel. Les ordres engageront de l'argent veritable."
    else
        ecrire_valeur "BINANCE_TESTNET" "1"
        ok "Testnet actif : aucun risque tant que vous ne changerez pas ce reglage."
    fi
    ecrire_valeur "GB_CONFIG" "robot.binance.json"
    ;;
2)
    echo
    echo "  Ces informations viennent de votre compte MoonX."
    ecrire_cle "MOONX_API_URL" "Adresse de l'API MoonX (ex: https://api.moon-x.io)"
    ecrire_cle "MOONX_API_KEY" "Cle API MoonX (elle ne s'affichera pas)" oui
    ecrire_valeur "GB_CONFIG" "robot.live.json"
    ;;
*)
    info "Aucune plateforme configuree : le robot tournera en simulation."
    ecrire_valeur "GB_CONFIG" "robot.micro.json"
    ;;
esac

# --------------------------------------------------------------------------
titre "4/5  Alertes sur telephone (fortement conseille)"

echo "  Un robot qui gere de l'argent seul doit rester surveillable."
echo "  Telegram est le plus simple : parlez a @BotFather, tapez /newbot,"
echo "  il vous donne un token. Puis parlez a @userinfobot pour votre ID."
echo "  Vous pouvez laisser vide et le configurer plus tard."
echo
ecrire_cle "TELEGRAM_BOT_TOKEN" "Token du bot Telegram (ou Entree pour passer)" oui
ecrire_cle "TELEGRAM_CHAT_ID"   "Votre identifiant Telegram (ou Entree pour passer)"

chmod 600 .env 2>/dev/null
ok "Le fichier .env est protege en lecture."

# --------------------------------------------------------------------------
titre "5/5  Raccourcis de demarrage"

mkdir -p data

cat > verifier.sh <<'EOF'
#!/usr/bin/env bash
# Verifie que tout repond, sans rien executer.
cd "$(dirname "$0")" || exit 1
set -a; [ -f .env ] && . ./.env; set +a
python3 run_bot.py check --config "${GB_CONFIG:-robot.micro.json}"
EOF

cat > essai.sh <<'EOF'
#!/usr/bin/env bash
# Mode essai : le robot analyse en direct et prepare de vrais ordres,
# mais n'envoie RIEN. Aucun risque. Les ordres sont ecrits dans
# data/journal.jsonl pour verification.
cd "$(dirname "$0")" || exit 1
set -a; [ -f .env ] && . ./.env; set +a
echo "MODE ESSAI : aucun ordre ne sera envoye. Ctrl+C pour arreter."
python3 run_bot.py run --config "${GB_CONFIG:-robot.micro.json}" --dry-run
EOF

cat > demarrer.sh <<'EOF'
#!/usr/bin/env bash
# Demarrage en REEL : le robot passe des ordres sur le compte.
cd "$(dirname "$0")" || exit 1
set -a; [ -f .env ] && . ./.env; set +a

echo
echo "############################################################"
echo "#  EXECUTION REELLE : le robot va passer des ordres seul.  #"
echo "#  Ctrl+C pour arreter (les positions gardent leur stop).   #"
echo "############################################################"
echo
read -r -p "Taper OUI pour confirmer : " reponse
[ "$reponse" != "OUI" ] && { echo "Annule."; exit 0; }

python3 run_bot.py run --config "${GB_CONFIG:-robot.micro.json}"
EOF

cat > resultats.sh <<'EOF'
#!/usr/bin/env bash
# Affiche les resultats et l'avancement de l'objectif.
cd "$(dirname "$0")" || exit 1
set -a; [ -f .env ] && . ./.env; set +a
python3 run_bot.py stats
echo
python3 run_bot.py objectifs --config "${GB_CONFIG:-robot.micro.json}"
EOF

chmod +x verifier.sh essai.sh demarrer.sh resultats.sh
ok "verifier.sh   -> teste que tout fonctionne"
ok "essai.sh      -> tourne sans envoyer d'ordre (aucun risque)"
ok "demarrer.sh   -> lance en reel"
ok "resultats.sh  -> affiche les gains et l'objectif"

# --------------------------------------------------------------------------
echo
echo -e "${GRAS}=============================================="
echo "   INSTALLATION TERMINEE"
echo -e "==============================================${FIN}"
echo
echo "  Etape suivante, dans cet ordre :"
echo
echo -e "     ${GRAS}bash verifier.sh${FIN}     verifier que tout repond"
echo -e "     ${GRAS}bash essai.sh${FIN}        laisser tourner sans risque"
echo -e "     ${GRAS}bash demarrer.sh${FIN}     passer en reel"
echo
