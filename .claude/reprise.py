#!/usr/bin/env python3
"""Injecte l'etat de reprise au demarrage de chaque session Claude Code.

Branche sur le hook SessionStart de .claude/settings.json. Sans lui, chaque
nouvelle session repart de CLAUDE.md seul -- qui porte les DECISIONS mais pas
l'etat COURANT : ou on en etait, ce qui attend une reponse, ce qui est en
cours. C'est ce trou qui obligeait l'operateur a tout re-expliquer apres
chaque conversation archivee.

Sortie : le JSON que Claude Code attend, avec REPRISE.md et l'etat git reel
dans additionalContext. En cas de pepin, on sort en silence : un hook qui
plante ne doit jamais empecher une session de demarrer.
"""

import json
import os
import subprocess
import sys

RACINE = os.environ.get("CLAUDE_PROJECT_DIR") or os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)


def git(*args: str) -> str:
    try:
        return subprocess.run(
            ("git", "-C", RACINE) + args,
            capture_output=True, text=True, timeout=10,
        ).stdout.strip()
    except Exception:
        return ""


def main() -> int:
    morceaux = []

    chemin = os.path.join(RACINE, "REPRISE.md")
    if os.path.isfile(chemin):
        with open(chemin, encoding="utf-8") as f:
            morceaux.append(f.read().rstrip())

    branche = git("branch", "--show-current")
    if branche:
        dernier = git("log", "--oneline", "-1")
        sales = git("status", "--porcelain")
        nb_sales = len([l for l in sales.splitlines() if l.strip()])
        devant = git("rev-list", "--count", "@{upstream}..HEAD") or "?"
        morceaux.append(
            "## Etat git a l'instant du demarrage\n\n"
            f"- branche : `{branche}`\n"
            f"- dernier commit : {dernier}\n"
            f"- fichiers modifies non commits : {nb_sales}\n"
            f"- commits non pousses : {devant}"
        )

    if not morceaux:
        return 0

    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": "\n\n---\n\n".join(morceaux),
            },
            "suppressOutput": True,
        },
        sys.stdout,
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)
