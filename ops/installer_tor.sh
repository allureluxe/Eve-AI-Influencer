#!/bin/bash
# Installe Tor pour la navigation de l'agent UNIQUEMENT -- 19 sept. 2026.
#
# Demande de l'operateur : « mets Tor en option, on garde le systeme
# normal ; si je veux faire des recherches sur le dark web il utilise
# Tor ». C'est exactement ce que fait cette installation.
#
# CE QUI NE CHANGE PAS, ET C'EST LE POINT IMPORTANT. Le trafic du
# SERVEUR n'est pas touche. Le robot continue de parler a Bitvavo depuis
# l'adresse habituelle -- une cle d'API qui arriverait soudain d'un autre
# pays, c'est un blocage au mieux, un compte gele au pire. Seules les
# pages que l'agent demande explicitement en Tor passent par Tor.
#
# POURQUOI DEUX PROGRAMMES. `tor` parle le protocole SOCKS5, qu'urllib
# (la bibliotheque utilisee par l'agent) ne sait pas utiliser. `privoxy`
# fait la traduction HTTP -> SOCKS, et surtout il transmet les noms en
# .onion a Tor au lieu d'essayer de les resoudre par le DNS public --
# sans quoi aucune adresse .onion ne s'ouvre, et la demande fuite.
#
#     bash ops/installer_tor.sh
#
# Se termine par un test reel : il demande son adresse IP a travers Tor
# et la compare a celle du serveur. Si elles sont identiques, rien n'est
# acquis et le script echoue.

set -euo pipefail

echo "=== 1/4  Installation de tor et privoxy ==="
if command -v tor &>/dev/null && command -v privoxy &>/dev/null; then
    echo "    deja installes"
else
    sudo apt-get update -qq
    sudo apt-get install -y tor privoxy
fi

echo "=== 2/4  Branchement de privoxy sur Tor ==="
# privoxy ecoute en HTTP sur 8118 et renvoie tout a Tor (SOCKS5 sur 9050).
# Le 'forward-socks5t' transmet aussi la resolution des noms a Tor.
if grep -q "^forward-socks5t / 127.0.0.1:9050 ." /etc/privoxy/config 2>/dev/null; then
    echo "    deja configure"
else
    echo "forward-socks5t / 127.0.0.1:9050 ." | sudo tee -a /etc/privoxy/config >/dev/null
    echo "    passerelle ajoutee"
fi

echo "=== 3/4  Demarrage ==="
sudo systemctl enable --now tor
sudo systemctl enable --now privoxy
sudo systemctl restart privoxy
sleep 4
echo "    tor     : $(systemctl is-active tor)"
echo "    privoxy : $(systemctl is-active privoxy)"

echo "=== 4/4  PREUVE : l'adresse est-elle vraiment differente ? ==="
DIRECTE=$(curl -s --max-time 20 https://api.ipify.org || echo "inconnue")
PAR_TOR=$(curl -s --max-time 40 --proxy http://127.0.0.1:8118 https://api.ipify.org || echo "echec")

echo "    adresse du serveur : $DIRECTE"
echo "    adresse via Tor    : $PAR_TOR"

if [ "$PAR_TOR" = "echec" ] || [ -z "$PAR_TOR" ]; then
    echo "    ECHEC : Tor ne repond pas. L'agent continuera en direct."
    exit 1
fi
if [ "$PAR_TOR" = "$DIRECTE" ]; then
    echo "    ECHEC : meme adresse, le trafic ne passe PAS par Tor."
    exit 1
fi

echo
echo "Termine. L'agent navigue normalement par defaut ; il passe par Tor"
echo "quand il le demande, et automatiquement pour toute adresse .onion."
echo
echo "A savoir : Tor est plus lent, et beaucoup de sites ordinaires"
echo "refusent les connexions qui en viennent -- c'est normal, pas une"
echo "panne. Les annuaires .onion sont par ailleurs remplis de sites"
echo "morts ou frauduleux : ne rien y telecharger, ne rien y acheter."
