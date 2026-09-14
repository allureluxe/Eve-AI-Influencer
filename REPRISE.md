# Ou on en est — mis a jour le 14 septembre 2026

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

**Le service systemd s'appelle `robot-dual-live.service`, PAS `gold-bot`** —
`gold-bot.service` existe toujours dans systemd mais est desactive/mort,
c'est un piege de nommage historique. Pour l'etat du jour, ne pas deviner :

    python3 etat.py
    python3 bilan_journee.py
    systemctl status robot-dual-live

## En suspens

- **Correctif devise crypto (commit 523f888, pousse le 14 sept.) pas encore
  charge par le robot en cours d'execution.** `instrument_crypto()` et les 4
  instruments crypto regles a la main (BTC/ETH/SOL/XRP) ne passaient jamais
  `quote_currency`, qui retombait sur le defaut "USD" -- l'application
  affichait donc `/USD` sur CHAQUE crypto fraichement publiee, pas seulement
  XTZ et ZETA (les deux seules vues jusqu'ici, car les seules publiees en
  reel depuis le cablage de `SignalPublisher` le 13 sept.). Corrige dans le
  code, verrouille par `tests/test_univers_bitvavo.py::TestToutesLesCryptosSontCoteesEnEuro`,
  mais **le processus tourne avec l'ancien code en memoire** : un
  `systemctl restart robot-dual-live` est necessaire pour que les PROCHAINS
  signaux publient la bonne devise. Pas fait automatiquement -- un restart
  du robot en reel reste une demande explicite de l'operateur (CLAUDE.md).
  Les deux lignes deja publiees (XTZ/USD, ZETA/USD) resteront fausses
  jusqu'a leur cloture : un garde-fou en base interdit de modifier `pair`
  apres publication, et c'est la bonne protection a garder.

- **Application mobile : build EAS en cours** (id
  `aa7bdfd6-e7cd-493c-9b93-88b466449012`, vrai logo + versionCode 2 + liste
  compacte). Etait `IN_QUEUE` au 14 sept. en fin d'apres-midi. Pour verifier
  son etat depuis le VPS, le token Expo n'est plus dans l'environnement du
  shell (il avait ete `export`e a la main, perdu au changement de session) --
  soit le redemander a l'operateur, soit consulter la page de build sur
  expo.dev directement.

- **« Mode TradingView » : deja construit, pas un chantier a rouvrir.**
  L'onglet Analyse -> segment « Marche » -> segment « Cours » (fichier
  `Cours.tsx`) contient deja un vrai widget TradingView (WebView, selecteur
  de symbole qui priorise les positions ouvertes, theme accorde, origine
  whitelistee). La demande de l'operateur du 14 sept. (« je veux le mode
  TradingView ») est donc deja satisfaite -- le seul risque est qu'il ne le
  trouve pas depuis la fusion des onglets, a le lui montrer au prochain
  echange plutot qu'a coder quoi que ce soit.

## Regle a ne plus oublier

**Lancer Claude Code avec `./claude_persistant.sh`, jamais `claude` nu.** Une
session lancee directement dans le shell SSH meurt avec le SSH, et la
conversation est archivee cote application. Se detacher avec `Ctrl+b` puis `d`.
Detail complet dans CLAUDE.md, section « Les conversations archivees ».
