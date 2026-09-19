# Ou on en est — mis a jour le 19 septembre 2026 (matin)

**Ce fichier est lu automatiquement au demarrage de chaque session Claude Code**
(hook `SessionStart`, voir `.claude/reprise.py`). Il evite de tout re-expliquer.

CLAUDE.md porte les **decisions** — pourquoi le D1, pourquoi le pyramidage
illimite, pourquoi pas IBKR. Ce fichier-ci porte l'**etat courant** : ce qui est
en cours, ce qui attend, ce qui vient de changer. Les deux sont complementaires.

> **A tenir a jour.** Toute session qui laisse un travail en suspens reecrit ce
> fichier avant de s'arreter. Un fichier perime ment plus qu'il n'aide.

---

## Le robot reel — A L'ARRET, volontairement

`robot-dual-live.service` est **inactif**. Le 16 sept., l'operateur a retire
la quasi-totalite du capital (44,49 + 50 + 50 EUR), confirme explicitement
le 18 sept. ("j'ai tout retire"). Capital reel actuel : quasiment zero
(~1e-08 EUR, verifie par lecture directe du solde Bitvavo). Voir memoire
`retrait-total-16-sept`.

**Ne PAS redemarrer `robot-dual-live` sans confirmation d'un nouveau depot
de l'operateur.** Quand il redepose : `ops/chien_de_garde.py --recaler`
(sur le compte reellement approvisionne) PUIS `sudo systemctl start
robot-dual-live`. `data/state.json` porte deja `halted: true` avec un motif
explicite ("compte vide -- lever a la main apres un nouveau depot").

Configuration : `robot.bitvavo.json`, D1 Donchian-**10**, pyramidage
**illimite** (`pyramide_max: 99`) en mode « a l'abri »
(`pyramide_locked_r_min: 0.01`), suiveur 3,0 ATR, stop temporel 5 jours.
CLAUDE.md a ete remis d'accord avec ces valeurs le 19 sept. (il annoncait
encore canal 20 et pyramidage 3) — ne pas y toucher sans repasser par
`comparer.py`.

**L'echantillon des 40 trades de preuve est ATTEINT** (40+, l'operateur a
decide le 16 sept. de laisser accumuler plutot que remettre a zero).
Espérance encore negative — palier reste "preuve" (0,6 % de risque).

## Le robot DEMO — actif, capital virtuel

`robot-demo.service` tourne en continu depuis le 18 sept. : simulation a
500 EUR virtuels, sur les VRAIES cotations Bitvavo en direct, AUCUN ordre
reel. Demande par l'operateur pour valider la strategie avant de deposer
les 500 EUR reellement. Notifications (Telegram compris, meme salon que le
robot reel) toutes prefixees **"[DEMO]"**.

    systemctl status robot-demo
    journalctl -u robot-demo -n 50

Fichiers completement isoles du robot reel : `data/state-demo.json`,
`data/trades-demo.jsonl` (jamais `data/state.json`/`data/trades.jsonl`).

**INCIDENT pendant la mise au point (corrige)** : les deux premiers essais
de `run_demo.py` ont ECRIT DANS `data/state.json` (celui du VRAI robot) --
`os.environ.setdefault()` ne suffisait pas car `.env` definit deja
`GB_STATE_FILE`/`GB_TRADES_FILE` (partage via `EnvironmentFile=` avec
`robot-dual-live.service`), et `setdefault()` n'ecrase jamais une valeur
deja presente. Corrige par une assignation DIRECTE + un filet de securite
qui refuse de demarrer si "demo" n'apparait pas dans les chemins resolus.
`data/trades.jsonl` (les trades REELS clotures) n'a jamais ete touche.
Voir memoire `demo-500eur-18-sept` — **lecon generale : ne jamais utiliser
`setdefault()` pour isoler un processus d'un `.env` partage.**

Deux bugs latents du simulateur (`PaperBroker`, jamais utilise en direct
avant, seulement en backtest) corriges au passage dans `gold_bot/engine.py`,
tous deux proteges par `isinstance(broker, PaperBroker)` (zero effet sur le
robot reel) : il n'etait jamais alimente en prix pour OUVRIR une position,
et sans methode `supports()` il scannait aussi le forex/l'or en plus des
cryptos.

**FAIT le 19 sept.** (l'operateur l'a redemande plus tot que prevu) : la
demo publie vers Supabase avec `is_demo = true` sur chaque ligne, et un
onglet **Demo** dedie l'affiche dans l'app. Les 11 positions ouvertes
pendant la coupure ont ete rattrapees avec
`publier_positions_demo_ouvertes.py`. Voir memoire
`fuite-signals-app-18-sept` (section « etape 2 ») et
`vue-direct-style-trading-19-sept`.

## Ce qui a ete repare le 19 septembre au matin

Quatre pannes que l'operateur a signalees, toutes diagnostiquees jusqu'a
la cause reelle :

1. **L'agent ne repondait ni en vocal ni en ecrit.** Il n'avait JAMAIS
   rien recu : le declencheur de purge de `alluxe_agent_messages` n'etait
   pas `security definer`, donc son DELETE tournait avec les droits de
   l'appelant (qui n'a pas DELETE) et faisait echouer chaque INSERT en
   403/42501. Migration `20260919094500_purge_security_definer.sql`.
   Memoire : `agent-muet-purge-security-definer-19-sept`.
2. **Luna ne generait plus de photo.** Le moteur renvoyait legende+scene
   sans les etiquettes `LEGENDE:`/`SCENE:` et l'analyseur jetait tout.
   Repli positionnel ajoute dans `luna/alluxe_v2.py`. A noter : le quota
   Hugging Face gratuit est EPUISE (HTTP 402), le repli Cloudflare prend
   le relais. Memoire : `luna-parseur-sans-etiquettes-19-sept`.
3. **La « methode » affichee mentait** (canal 20 jours, pyramidage 3).
   Le texte etait ecrit en dur ; il est desormais DEDUIT de la config.
   `rapport_matin.py` faisait pire : il CALCULAIT le canal sur 20 bougies,
   donc listait les mauvaises cryptos. Memoire :
   `methode-affichee-mentait-19-sept`.
4. **CLAUDE.md etait la source du mal** — corrige avec l'accord explicite
   de l'operateur (5 reglages remis d'accord, 12 valeurs verifiees une a
   une contre `robot.bitvavo.json`).

Egalement livre : **deverrouillage par empreinte/Face ID** dans l'app
(verifie par l'operateur : « si l'empreinte c'est bon »), et la **vue en
direct style trading** (nom de la crypto / % / gain-perte en euros) sur
les onglets Direct et Demo, via Supabase Realtime + cotations Bitvavo
cote client.

**Nettoyage fait au passage** : les 21 lignes de la fuite du 18 sept.
sont toutes passees en `is_demo = true` (y compris la fameuse position
« a 600 % de benefice » que l'operateur avait vue) ; la table `signals`
cote reel ne contient plus que les 15 vraies positions du 13-15 sept.
9 lignes fantomes ont ete supprimees avec accord explicite, apres
sauvegarde locale (`data/sauvegarde-signals-fuite-18sept.json`).

## L'application (Alluxe Bot) — fusion terminee le 16 sept.

## L'application (Alluxe Bot) — fusion terminee le 16 sept.

Une seule application, 4 gros boutons sur l'accueil : Alluxbot / Allure /
Luna / Agent. Tout fonctionne, y compris apres correction d'un bug de mot
de passe de service (voir plus bas). Lien de build stable (inchange) :
https://github.com/allureluxe/Eve-AI-Influencer/releases/tag/dernier-build-alluxe-bot

1. **Alluxbot** — pilotage du robot
2. **Allure** — l'app publique integree en mode administrateur
3. **Luna** — personnage + file de generation de contenu, lecture audio/
   video incluse. Pipeline de contenu RENOMME `alluxe_v2.py` (racine ET
   `luna/alluxe_v2.py`) pour ne pas se confondre avec l'agent.
4. **Agent (Alluxe)** — assistant personnel, LECTURE SEULE (etat du robot/
   alertes/Luna, jamais d'action). Chat texte + reponses lues a voix haute.
   **Reveil vocal en arriere-plan code et compile, mais BLOQUE en attente
   de deux elements que seul l'operateur peut fournir** : `PICOVOICE_ACCESS_KEY`
   et `app-alluxe-bot/assets/reveil/alluxe_android.ppn` (voir
   `app-alluxe-bot/assets/reveil/LISEZMOI.txt` pour les etapes exactes sur
   console.picovoice.ai). Aucun test reel sur telephone possible depuis ce
   serveur.

**Delibérement PAS fait** : donner a l'Agent un pouvoir d'action -- decision
separee a prendre explicitement avec l'operateur.

**Service serveur** : `alluxe-agent.service` (systemd, permanent), lecture
seule, verifie actif.

## BUG CORRIGE le 18 sept. : mot de passe de service desynchronise

L'APK affichait "Compte de service non configure." -- le secret GitHub
`ALLUXE_BOT_SERVICE_PASSWORD` ne correspondait plus a celui de `.env`.
Corrige en definissant un nouveau mot de passe (choisi par l'operateur,
jamais affiche dans la conversation -- une protection automatique bloque
l'affichage de credentials) applique aux deux endroits via
`definir_mdp_service_alluxe_bot.py` (Supabase Admin API) + l'operateur
lui-meme cote GitHub. Verifie par une vraie connexion Supabase reussie.

## Outils utiles crees cette semaine

- **`GITHUB_ACTIONS_READ_TOKEN`** (.env) : jeton GitHub lecture seule
  (Actions: Read-only) pour lire les VRAIS journaux d'un build echoue.
  L'API refuse `/actions/jobs/{id}/logs` sans authentification meme sur
  un depot public, et il faut desactiver le suivi de redirection HTTP
  (le Location vers Azure Blob refuse le header d'auth) -- capturer le
  Location, puis GET simple SANS le header.
- **`GITHUB_ACTIONS_WRITE_TOKEN`** (.env) : jeton GitHub Secrets:
  Read-and-write, pour corriger un secret directement
  (`corriger_secret_github.py`, chiffrement libsodium/PyNaCl cote
  client) -- mais voir plus haut, cette action precise est BLOQUEE par
  la protection anti-credentials si la valeur est LUE depuis un secret
  EXISTANT ; fonctionne seulement pour une valeur FRAICHEMENT fournie
  par l'operateur.
- **`verifier_positions_orphelines.py SYMBOLE`** : lecture seule des
  avoirs/ordres reels Bitvavo, pour verifier si une position affichee
  "ouverte depuis X h" est en fait deja fermee sans que le robot le
  sache (trouve le 16 sept. sur ZETAUSD).

## Regle a ne plus oublier

**Lancer Claude Code avec `./claude_persistant.sh`, jamais `claude` nu.** Une
session lancee directement dans le shell SSH meurt avec le SSH, et la
conversation est archivee cote application. Se detacher avec `Ctrl+b` puis `d`.
Detail complet dans CLAUDE.md, section « Les conversations archivees ».

**Ne jamais `os.environ.setdefault()` pour isoler un nouveau processus d'un
`.env` partage** -- une cle deja definie globalement rend le setdefault
silencieusement inoperant. Assignation directe + verification apres coup.
