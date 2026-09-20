#!/bin/bash
# Campagne de mesure des strategies, lancee la nuit.
#
# POURQUOI LA NUIT. Mesurer 17 variantes sur l'univers complet demande
# plus de memoire que ce serveur n'en a de libre en journee : le robot
# demo en occupe 1,4 Go sur 3,7. Le 19 sept., lancee a 12h13 sous un
# plafond de 700 Mo, la campagne a ete tuee a 12h01 -- le plafond a
# protege le robot, ce qui etait son role, mais elle n'a jamais fini.
#
# La nuit, rien d'autre ne tourne : on peut lui laisser 1,5 Go sans
# menacer le robot, qui reste prioritaire (le plafond de 1,8 Go pose sur
# robot-demo le protege de toute facon).
#
# Lancee par cron a 01h00, apres la generation des photos de Luna (00h05)
# pour ne pas se disputer la memoire avec elle.

cd "$(dirname "$0")/.." || exit 1
SORTIE="data/campagne-strategies-$(date +%Y%m%d).txt"

# ELLE NE DEMARRE PAS SI LA PLACE MANQUE.
#
# Le 20 septembre, DEUX simulations tournent en parallele (comptes demo
# et demo2) et occupent ~2,2 Go des 3,8 de ce serveur. Une campagne qui
# en reclame 1,5 de plus ne se contenterait pas d'echouer : le noyau
# tuerait un processus au hasard, possiblement la simulation sur
# laquelle Monsieur decide son depot du 28.
#
# Une mesure vaut moins qu'une mesure en cours. Si la place manque, on
# passe notre tour et on le DIT -- un silence laisserait croire qu'elle
# a tourne.
LIBRE=$(awk '/MemAvailable/ {print int($2/1024)}' /proc/meminfo)
BESOIN=1600
if [ "${LIBRE:-0}" -lt "$BESOIN" ]; then
    echo "campagne reportee : ${LIBRE} Mo libres, il en faut ${BESOIN}." \
         "Les simulations en cours passent avant." >> "$SORTIE"
    echo "campagne reportee : ${LIBRE} Mo libres sur ${BESOIN} necessaires"
    exit 0
fi

exec systemd-run --scope --quiet --unit=campagne-nuit \
    -p MemoryMax=1500M -p MemorySwapMax=0 -p CPUWeight=20 \
    nice -n 19 ./.venv/bin/python comparer.py \
        --univers-complet --spread-x 2 --bars 1200 \
    > "$SORTIE" 2>&1
