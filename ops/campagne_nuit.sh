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

exec systemd-run --scope --quiet --unit=campagne-nuit \
    -p MemoryMax=1500M -p MemorySwapMax=0 -p CPUWeight=20 \
    nice -n 19 ./.venv/bin/python comparer.py \
        --univers-complet --spread-x 2 --bars 1200 \
    > "$SORTIE" 2>&1
