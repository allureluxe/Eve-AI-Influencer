# Ou on en est — mis a jour le 13 septembre 2026

**Ce fichier est lu automatiquement au demarrage de chaque session Claude Code**
(hook `SessionStart`, voir `.claude/reprise.py`). Il evite de tout re-expliquer.

CLAUDE.md porte les **decisions** — pourquoi le D1, pourquoi 3 etages de
pyramide, pourquoi pas IBKR. Ce fichier-ci porte l'**etat courant** : ce qui est
en cours, ce qui attend, ce qui vient de changer. Les deux sont complementaires.

> **A tenir a jour.** Toute session qui laisse un travail en suspens reecrit ce
> fichier avant de s'arreter. Un fichier perime ment plus qu'il n'aide.

---

## Le robot

Arme en reel sur Bitvavo, configuration `robot.bitvavo.json` (cle
`_arme_en_reel`). Strategie D1 Donchian-20, pyramidage Turtle 3 etages, stop
temporel 5 jours. Voir CLAUDE.md pour le detail et l'interdiction d'y toucher
sans repasser par `comparer.py`.

Pour l'etat du jour, ne pas deviner — lancer :

    python3 etat.py
    python3 bilan_journee.py
    systemctl status gold-bot

## En suspens

- **Application mobile / build APK via Expo.** La session « bot bitvavo v2 » du
  13 septembre s'est arretee la : le build attend un **jeton d'acces Expo**, a
  creer sur expo.dev (Settings -> Access tokens). Rien d'autre ne bloque.

## Regle a ne plus oublier

**Lancer Claude Code avec `./claude_persistant.sh`, jamais `claude` nu.** Une
session lancee directement dans le shell SSH meurt avec le SSH, et la
conversation est archivee cote application. Se detacher avec `Ctrl+b` puis `d`.
Detail complet dans CLAUDE.md, section « Les conversations archivees ».
