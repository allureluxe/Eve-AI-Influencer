#!/bin/bash
# Verifie et installe l'agent Alluxe, en UNE commande courte.
#
# POURQUOI CE SCRIPT EXISTE. Le terminal de l'operateur coupe les
# commandes longues -- un `cd ... && ./.venv/bin/python -m pytest ...`
# arrive tronque et ne s'execute pas, sans le moindre message. Constate
# le 19 sept. : trois commandes lancees, zero sortie, alors que tout
# etait correct. D'ou une commande de 20 caracteres :
#
#     bash ops/verifier.sh
#
# Elle enchaine les deux etapes qui comptent, et S'ARRETE a la premiere
# qui echoue -- il ne faut pas isoler un agent dont les garde-fous ne
# passent pas les tests.

set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

echo
echo "############  1/2  LES GARDE-FOUS TIENNENT-ILS ?  ############"
echo
if ./.venv/bin/python -m pytest tests/test_agent_outils.py -q; then
    echo
    echo ">>> Les garde-fous passent."
else
    echo
    echo ">>> ECHEC. NE PAS brancher l'agent."
    echo ">>> Recopiez ce qui est ecrit au-dessus a Claude Code."
    exit 1
fi

echo
echo "############  2/2  ISOLER L'AGENT DE VOS CLES  ############"
echo
if bash ops/installer_agent_isole.sh; then
    echo
    echo ">>> Agent isole : il ne peut plus lire vos cles."
else
    echo
    echo ">>> L'isolation a echoue. Recopiez ce qui est ecrit au-dessus."
    exit 1
fi

echo
echo "=============================================================="
echo " Termine. Alluxe peut agir, sans jamais atteindre vos cles."
echo
echo " Pour ajouter Tor plus tard :  bash ops/tor.sh"
echo "=============================================================="
