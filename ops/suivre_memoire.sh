#!/bin/bash
# Note la memoire des services du projet, une ligne par passage.
#
# POURQUOI. Le 19 sept., `robot-demo` a ete tue TROIS fois par le noyau
# pour manque de memoire (09h55, 10h09, 10h28) puis redemarre tout seul.
# Il tournait a 1,4 Go et montait vers 2 Go. Une mesure ponctuelle ne dit
# pas si ca FUIT (croissance continue) ou si ca MONTE PAR PALIERS sur un
# evenement precis -- et les deux se reparent differemment.
#
# Lance par cron toutes les 2 minutes. Le fichier reste minuscule (une
# ligne de 60 caracteres), et il tourne meme si le robot est arrete.
#
#     bash ops/suivre_memoire.sh
#     column -t data/memoire.log | tail -30

FICHIER="$(dirname "$0")/../data/memoire.log"

mesurer() {
    local pid
    pid=$(systemctl show "$1" -p MainPID --value 2>/dev/null)
    if [ -z "$pid" ] || [ "$pid" = "0" ]; then echo "-"; return; fi
    local rss
    rss=$(ps -o rss= -p "$pid" 2>/dev/null | tr -d ' ')
    if [ -z "$rss" ]; then echo "-"; else echo $((rss / 1024)); fi
}

LIBRE=$(free -m | awk 'NR==2{print $7}')
printf "%s  demo=%sMo  agent=%sMo  libre=%sMo\n" \
    "$(date '+%Y-%m-%d %H:%M')" \
    "$(mesurer robot-demo)" "$(mesurer alluxe-agent)" "$LIBRE" >> "$FICHIER"

# Ne jamais laisser ce journal grossir : on garde les 3 derniers jours.
tail -n 2200 "$FICHIER" > "$FICHIER.tmp" && mv "$FICHIER.tmp" "$FICHIER"
