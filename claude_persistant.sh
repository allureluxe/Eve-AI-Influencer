#!/usr/bin/env bash
# Lance Claude Code dans une session tmux qui SURVIT a la deconnexion SSH.
#
# Pourquoi ce script existe :
#   Une session Claude Code lancee directement dans un shell SSH est un simple
#   processus enfant de ce shell. Quand le SSH tombe -- reseau, telephone mis en
#   veille, terminal ferme, fenetre changee -- le processus est tue. Le pont qui
#   miroite la session vers l'application passe alors en "disconnected", puis la
#   conversation est ARCHIVEE cote application.
#
#   L'archivage ne supprime rien : la conversation reste sur ce VPS, dans
#   ~/.claude/projects/, et "claude --resume" la retrouve. Mais le fil de travail
#   est interrompu, et c'est exactement ce qu'on veut eviter.
#
#   tmux detache le processus du SSH : la session continue de tourner sur le VPS,
#   meme telephone eteint. On s'y rebranche quand on veut.
#
# Usage :
#   ./claude_persistant.sh            # cree la session, ou s'y rebranche
#   ./claude_persistant.sh --statut   # dit si une session tourne, sans y entrer
#
#   Pour se detacher SANS tuer Claude : Ctrl+b puis d
#   Ne PAS taper /exit ni Ctrl+d : ceux-la terminent vraiment la session.

set -euo pipefail

SESSION="${CLAUDE_TMUX_SESSION:-bot}"
PROJET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if ! command -v tmux >/dev/null 2>&1; then
    echo "tmux n'est pas installe. Installe-le d'abord :" >&2
    echo "    sudo apt-get update && sudo apt-get install -y tmux" >&2
    exit 1
fi

if [ "${1:-}" = "--statut" ]; then
    if tmux has-session -t "$SESSION" 2>/dev/null; then
        echo "Session tmux '$SESSION' EN COURS :"
        tmux list-windows -t "$SESSION"
        echo
        echo "Pour la reprendre :  tmux attach -t $SESSION"
    else
        echo "Aucune session tmux '$SESSION'. Lance : ./claude_persistant.sh"
    fi
    exit 0
fi

if tmux has-session -t "$SESSION" 2>/dev/null; then
    echo "Session '$SESSION' deja en cours -- rebranchement."
    echo "Pour te detacher sans rien tuer : Ctrl+b puis d"
    exec tmux attach -t "$SESSION"
fi

echo "Creation de la session tmux '$SESSION' dans $PROJET"
echo "Pour te detacher sans rien tuer : Ctrl+b puis d"
tmux new-session -d -s "$SESSION" -c "$PROJET"
tmux send-keys -t "$SESSION" 'claude --continue || claude' C-m
exec tmux attach -t "$SESSION"
