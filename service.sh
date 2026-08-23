#!/usr/bin/env bash
#
# Installe le robot comme service systeme sur un serveur Linux.
#
#   sudo bash service.sh installer     met en service (demarrage automatique)
#   sudo bash service.sh demarrer      lance le robot
#   sudo bash service.sh arreter       arrete le robot
#   sudo bash service.sh etat          etat courant
#   bash service.sh journal            suit les messages en direct
#   sudo bash service.sh desinstaller  retire le service
#
# Une fois installe, le robot redemarre tout seul apres un reboot du serveur
# ou une coupure reseau. Les positions ouvertes restent protegees par leur
# stop-loss cote broker pendant la coupure.

set -u

NOM="robot-trading"
UNITE="/etc/systemd/system/${NOM}.service"
DOSSIER="$(cd "$(dirname "$0")" && pwd)"
VERT="\033[0;32m"; ROUGE="\033[0;31m"; JAUNE="\033[0;33m"; GRAS="\033[1m"; FIN="\033[0m"

ok()    { echo -e "  ${VERT}OK${FIN}   $1"; }
souci() { echo -e "  ${ROUGE}STOP${FIN} $1"; }
info()  { echo -e "  ${JAUNE}i${FIN}    $1"; }

exiger_root() {
    [ "$(id -u)" -eq 0 ] || { souci "Cette commande demande sudo : sudo bash service.sh $1"; exit 1; }
}

case "${1:-aide}" in

installer)
    exiger_root installer

    [ -f "$DOSSIER/.env" ] || { souci "Fichier .env absent. Lancez d'abord : bash installer.sh"; exit 1; }
    # La configuration retenue est celle choisie a l'installation.
    CONFIG=$(grep -E "^GB_CONFIG=" "$DOSSIER/.env" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d " \"'")
    CONFIG="$(basename "${CONFIG:-robot.micro.json}")"
    [ -f "$DOSSIER/$CONFIG" ] || { souci "$CONFIG absent."; exit 1; }
    ok "configuration installee : $CONFIG"

    # Le service tourne sous le compte proprietaire du dossier, jamais root :
    # un robot qui gere de l'argent n'a aucun besoin des droits administrateur.
    UTILISATEUR=$(stat -c '%U' "$DOSSIER")
    [ "$UTILISATEUR" = "root" ] && info "Le dossier appartient a root : le service tournera en root."

    PYTHON=$(command -v python3) || { souci "python3 introuvable."; exit 1; }

    cat > "$UNITE" <<EOF
[Unit]
Description=Robot de trading autonome
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${UTILISATEUR}
WorkingDirectory=${DOSSIER}
EnvironmentFile=${DOSSIER}/.env
ExecStart=${PYTHON} ${DOSSIER}/run_bot.py run --config ${DOSSIER}/${CONFIG}

Restart=always
RestartSec=30
StartLimitIntervalSec=600
StartLimitBurst=10

KillSignal=SIGTERM
TimeoutStopSec=60

StandardOutput=journal
StandardError=journal
SyslogIdentifier=${NOM}

NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=${DOSSIER}/data

[Install]
WantedBy=multi-user.target
EOF

    mkdir -p "$DOSSIER/data"
    chown -R "$UTILISATEUR" "$DOSSIER/data" 2>/dev/null || true
    systemctl daemon-reload
    systemctl enable "$NOM" >/dev/null 2>&1

    ok "Service installe : $UNITE"
    ok "Configuration : $CONFIG"
    ok "Compte utilise : $UTILISATEUR"
    ok "Demarrage automatique au boot : active"
    echo
    info "Le robot n'est pas encore lance. Pour demarrer :"
    echo -e "     ${GRAS}sudo bash service.sh demarrer${FIN}"
    ;;

demarrer)
    exiger_root demarrer
    # L'unite systemd fige la configuration au moment de l'installation.
    # Changer GB_CONFIG dans .env ne la met PAS a jour : sans ce controle,
    # le robot repart sur l'ancienne plateforme en silence — c'est ainsi
    # qu'un service Bitvavo s'est retrouve a envoyer des ordres a Binance.
    VOULUE=$(grep -E "^GB_CONFIG=" "$DOSSIER/.env" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d " \"'")
    VOULUE="$(basename "${VOULUE:-}")"
    INSTALLEE=$(grep -oE "run_bot\.py run --config [^ ]+" "$UNITE" 2>/dev/null | awk '{print $NF}')
    INSTALLEE="$(basename "${INSTALLEE:-}")"
    if [ -n "$VOULUE" ] && [ -n "$INSTALLEE" ] && [ "$VOULUE" != "$INSTALLEE" ]; then
        souci "Le service installe utilise ${INSTALLEE}, mais .env demande ${VOULUE}."
        info "Reinstalle-le pour prendre le changement en compte :"
        echo "      sudo bash service.sh installer"
        exit 1
    fi
    [ -n "$INSTALLEE" ] && ok "configuration du service : $INSTALLEE"

    systemctl start "$NOM"
    sleep 3
    if systemctl is-active --quiet "$NOM"; then
        ok "Robot demarre."
        info "Voir ce qu'il fait : bash service.sh journal"
    else
        souci "Le robot n'a pas demarre. Details :"
        journalctl -u "$NOM" -n 25 --no-pager
        exit 1
    fi
    ;;

arreter)
    exiger_root arreter
    systemctl stop "$NOM"
    ok "Robot arrete."
    info "Les positions ouvertes gardent leur stop-loss cote broker."
    ;;

redemarrer)
    exiger_root redemarrer
    systemctl restart "$NOM"
    ok "Robot redemarre."
    ;;

etat)
    systemctl status "$NOM" --no-pager 2>/dev/null || souci "Service non installe."
    ;;

journal)
    echo "Messages en direct (Ctrl+C pour quitter l'affichage, le robot continue) :"
    journalctl -u "$NOM" -f --no-pager
    ;;

desinstaller)
    exiger_root desinstaller
    systemctl stop "$NOM" 2>/dev/null
    systemctl disable "$NOM" 2>/dev/null
    rm -f "$UNITE"
    systemctl daemon-reload
    ok "Service retire. Le dossier et les donnees sont conserves."
    ;;

*)
    echo -e "${GRAS}Gestion du robot en service${FIN}"
    echo
    echo "  sudo bash service.sh installer     mettre en service (une seule fois)"
    echo "  sudo bash service.sh demarrer      lancer"
    echo "  sudo bash service.sh arreter       arreter"
    echo "  sudo bash service.sh redemarrer    relancer"
    echo "       bash service.sh etat          voir s'il tourne"
    echo "       bash service.sh journal       suivre en direct"
    echo "  sudo bash service.sh desinstaller  retirer le service"
    ;;
esac
