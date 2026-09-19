#!/bin/bash
# Isole l'agent Alluxe dans son propre compte systeme -- 19 sept. 2026.
#
# POURQUOI. L'agent recoit le shell complet (voir ops/agent_outils.py) et
# tourne tout seul, pilote par un modele de langage, sur le serveur qui
# heberge le robot de trading et ses cles. Un filtre de texte ne suffit
# pas : la premiere version refusait `cat .env` mais laissait passer
# `printenv`, ce qui affichait 35 cles -- Bitvavo (argent reel), GitHub
# en ecriture, Instagram, TikTok.
#
# CE QUE CE SCRIPT CHANGE. L'agent cesse de tourner sous le compte de
# l'operateur (`ubuntu`, proprietaire de tout) et passe sous un compte
# dedie `alluxe`, qui n'a PHYSIQUEMENT pas le droit de lire les fichiers
# de cles. Ce n'est plus une regle qu'on lui demande de respecter, c'est
# le systeme d'exploitation qui refuse.
#
# L'agent continue de recevoir les cles dont il a besoin (Supabase, le
# moteur) parce que systemd lit `.env` en tant qu'administrateur AVANT
# de rendre la main au compte `alluxe` -- le processus les a en memoire,
# le compte ne peut pas ouvrir le fichier. Et `environnement_sans_cles()`
# les retire des commandes que l'agent lance.
#
#     bash ops/installer_agent_isole.sh
#
# Le script est SANS DANGER a relancer : chaque etape verifie l'etat
# avant d'agir. Il se termine par un test qui PROUVE que les cles sont
# devenues inaccessibles -- s'il echoue, rien n'est acquis.

set -euo pipefail

DEPOT="/home/ubuntu/Eve-AI-Influencer"
COMPTE="alluxe"
UNITE="/etc/systemd/system/alluxe-agent.service"

echo "=== 1/6  Compte dedie '$COMPTE' ==="
if id "$COMPTE" &>/dev/null; then
    echo "    deja present"
else
    sudo useradd --system --create-home --shell /bin/bash "$COMPTE"
    echo "    cree"
fi

echo "=== 2/6  Acces au depot (groupe ubuntu) ==="
sudo usermod -aG ubuntu "$COMPTE"
sudo chmod g+x /home/ubuntu
# Le groupe doit pouvoir lire ET ecrire le code : l'agent modifie des
# fichiers. Le X majuscule ne met le droit d'execution que sur les
# dossiers, jamais sur un fichier de code.
sudo chgrp -R ubuntu "$DEPOT"
sudo chmod -R g+rwX "$DEPOT"
echo "    depot accessible au groupe"

echo "=== 3/6  FERMETURE des fichiers de cles ==="
# APRES le chmod de groupe ci-dessus, jamais avant : sinon le -R les
# rouvrirait. Proprietaire seul, en lecture et ecriture.
sudo chmod 600 "$DEPOT"/.env 2>/dev/null || true
for f in "$DEPOT"/.env.*; do
    [ -e "$f" ] && sudo chmod 600 "$f"
done
sudo chown ubuntu:ubuntu "$DEPOT"/.env* 2>/dev/null || true
echo "    cles refermees (proprietaire ubuntu seulement)"

echo "=== 4/6  Le service passe sous '$COMPTE' ==="
if grep -q "^User=$COMPTE$" "$UNITE"; then
    echo "    deja le cas"
else
    sudo sed -i "s/^User=ubuntu$/User=$COMPTE/" "$UNITE"
    echo "    unite modifiee"
fi

echo "=== 5/6  Redemarrage ==="
sudo systemctl daemon-reload
sudo systemctl restart alluxe-agent
sleep 3
systemctl is-active alluxe-agent | sed 's/^/    service : /'

echo "=== 6/6  PREUVE : les cles sont-elles inaccessibles ? ==="
if sudo -u "$COMPTE" test -r "$DEPOT/.env"; then
    echo "    ECHEC : le compte $COMPTE peut encore lire .env"
    echo "    NE PAS considerer l'agent comme isole."
    exit 1
fi
echo "    OK : le compte $COMPTE ne peut PAS lire .env"

# On VERIFIE EN ECRIVANT, pas en demandant. `test -w` a repondu "non"
# le 19 sept. sur un fichier ou l'ecriture marchait parfaitement --
# /usr/bin/test et le builtin de bash ne donnaient meme pas la meme
# reponse. Un fichier reellement cree puis efface ne ment pas.
TEMOIN="$DEPOT/data/.essai-ecriture-alluxe"
if sudo -u "$COMPTE" bash -c "echo ok > '$TEMOIN'" 2>/dev/null; then
    sudo rm -f "$TEMOIN"
    echo "    OK : il peut travailler dans le depot"
else
    echo "    ATTENTION : il ne peut pas ecrire dans le depot, il ne servira a rien"
    exit 1
fi

echo
echo "Termine. L'agent tourne sous '$COMPTE', sans acces aux cles."
