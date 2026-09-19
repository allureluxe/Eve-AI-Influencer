#!/bin/bash
# Les sept variantes, UN PROCESSUS CHACUNE.
#
# Enchainees dans un seul processus elles ont ete tuees par manque de
# memoire : 60 paires gardent en vie 60 jeux d'indicateurs, et
# l'allocateur Python ne rend pas la memoire au systeme entre deux
# variantes. Sortir du processus, si.
#
# Le robot demo reste prioritaire : plafond serre et faible priorite CPU.
cd "$(dirname "$0")/.." || exit 1
SORTIE="${1:-data/mesure-reserve.jsonl}"
PAIRES="${2:-40}"
BOUGIES="${3:-900}"
: > "$SORTIE"
for i in 0 1 2 3 4 5 6; do
    echo "variante $i ..."
    systemd-run --user --scope --quiet -p MemoryMax=900M -p CPUWeight=20 \
        nice -n 19 ./.venv/bin/python -u mesurer_reserve.py \
            --variante "$i" --paires "$PAIRES" --bougies "$BOUGIES" \
            --json "$SORTIE" || echo "  variante $i : ECHEC"
done
echo "termine : $(wc -l < "$SORTIE") variante(s) sur 7"
