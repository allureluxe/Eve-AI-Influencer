# Ou on en est — mis a jour le 16 septembre 2026 (soir)

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

    python3 etat.py
    python3 bilan_journee.py
    systemctl status robot-dual-live

**Capital reel au 16 sept. au soir : ~100 EUR** (apres un retrait de
44,49 EUR fait par l'operateur ce jour-la). Chien de garde recale sur cette
base (plancher 45 EUR).

**L'echantillon des 40 trades de preuve est ATTEINT** (exactement 40, puis
au-dela — l'operateur a decide le 16 sept. de laisser accumuler plutot que de
remettre a zero si l'espérance reste negative, voir CLAUDE.md/memoire
correspondante). Espérance encore negative a ce stade — normal, le palier
reste "preuve" (0,6 % de risque). Ne pas monter le risque tant que l'espérance
nette n'est pas positive.

## INCIDENT du 16 sept. — RESOLU, mais a surveiller

Vers 18h (heure francaise), un retrait de 44,49 EUR a declenche a tort le
chien de garde (il ne peut pas distinguer un retrait d'une perte, et c'est
volontaire — voir l'en-tete d'`ops/chien_de_garde.py`). Le robot s'est arrete
tout seul. Diagnostic + recalage + redemarrage faits le soir meme avec
confirmation de l'operateur :

    python3 ops/chien_de_garde.py --recaler
    sudo systemctl start robot-dual-live

**Au passage, un vrai bug decouvert** : `etat.py` affichait ZETAUSD comme
"ouvert depuis 63h" alors que son stop avait REELEMENT ete declenche chez
Bitvavo plus d'une journee avant (perdu au fil de plusieurs redemarrages
anterieurs). Le redemarrage du 16 sept. a spontanement corrige la
reconciliation (voir le journal : "RAPPROCHEMENT ZETA-EUR"), donc rien a
faire cote code dans l'immediat -- mais **si une position affiche a nouveau
un age suspect, verifier avec** :

    python3 verifier_positions_orphelines.py SYMBOLE

(lecture seule chez Bitvavo -- avoirs et ordres reels, aucun ordre envoye).
Le mecanisme exact qui a laisse ZETA orphelin plusieurs jours n'a pas ete
completement instrumente/corrige a la racine (piste : `ACTIFS_PAR_SYMBOLE`
dans `gold_bot/universe.py`, catalogue STATIQUE de 85 symboles, potentiellement
desynchronise avec l'univers DYNAMIQUE de ~215 cryptos utilise par le scanner
-- a verifier si le probleme revient).

## L'application (Alluxe Bot) — fusion terminee le 16 sept.

Plan du 15 sept. (voir memoire `fusion-app-unique-et-agent-alluxe-15-sept`)
**REALISE EN ENTIER** le 16 sept. : une seule application, 4 gros boutons
sur l'accueil.

1. **Alluxbot** — pilotage du robot (deja livre le 15 sept.)
2. **Allure** — l'app publique integree en mode administrateur (session du
   compte de service, pas de 2e connexion)
3. **Luna** — personnage + file de generation de contenu (texte/photo/voix/
   video), declenchable depuis le telephone, lecture audio/video incluse.
   Le pipeline de contenu (script alluxe.py) a ete RENOMME `alluxe_v2.py`
   (racine ET `luna/alluxe_v2.py`) pour ne pas se confondre avec le nouvel
   agent -- toute reference future doit utiliser ce nouveau nom.
4. **Agent (Alluxe)** — assistant personnel, PREMIERE VERSION LECTURE SEULE
   (etat du robot/alertes/Luna, jamais d'action). Chat texte + reponses lues
   a voix haute (expo-speech). **Reveil vocal en arriere-plan ("dire Alluxe")
   code et compile (Picovoice Porcupine, service Android natif custom,
   voir `app-alluxe-bot/plugins/reveil-vocal/`), mais BLOQUE en attente de
   deux elements que seul l'operateur peut fournir** :
   - `PICOVOICE_ACCESS_KEY` (compte gratuit sur console.picovoice.ai)
   - `app-alluxe-bot/assets/reveil/alluxe_android.ppn` (mot-cle "Alluxe"
     genere sur la meme console, langue anglais, plateforme Android)

   Voir `app-alluxe-bot/assets/reveil/LISEZMOI.txt` pour les etapes exactes.
   Une fois recus : `python3 mettre_a_jour_jeton_picovoice.py <cle>`, ajouter
   le meme secret dans GitHub Actions, placer le fichier .ppn, committer,
   pousser (le build se relance tout seul sur `app-alluxe-bot/**`).

   **Aucun test reel sur telephone n'a ete possible depuis ce serveur**
   (pas de SDK Android, pas d'appareil) -- le code compile (verifie sur
   GitHub Actions apres 2 vrais bugs de version de dependances corriges),
   mais seul un essai reel confirmera que la detection fonctionne et que la
   notification permanente imposee par Android est acceptable.

**Service serveur ajoute** : `alluxe-agent.service` (systemd, permanent,
PAS un cron), poll toutes les 2 s sur `alluxe_agent_messages` (Supabase),
lecture seule. Verifie actif et sans interference avec le robot.

**Lien de build stable** (inchange depuis le debut) :
https://github.com/allureluxe/Eve-AI-Influencer/releases/tag/dernier-build-alluxe-bot

**Delibérement PAS fait** : donner a l'Agent un pouvoir d'action (redemarrer
le robot, changer un reglage) -- decision separee a prendre explicitement
avec l'operateur, avec un perimetre precis. Ne pas l'ajouter sur un
"continue, fais tout" generique.

## Outil utile decouvert/cree ce soir

Un jeton GitHub personnel en lecture seule (Actions: Read-only, ce seul
depot) est maintenant dans `.env` sous `GITHUB_ACTIONS_READ_TOKEN` -- permet
de lire les VRAIS journaux d'un build GitHub Actions echoue (l'API refuse
`/actions/jobs/{id}/logs` sans authentification, meme sur un depot public).
Methode : requete avec le jeton, header Authorization, en desactivant le
suivi de redirection HTTP (le Location pointe vers une URL Azure Blob
signee qui refuse le header d'auth) -- capturer le Location, puis refaire
un GET simple SANS le header vers cette URL. Bien plus fiable que deviner
la cause d'un echec de build.

## Regle a ne plus oublier

**Lancer Claude Code avec `./claude_persistant.sh`, jamais `claude` nu.** Une
session lancee directement dans le shell SSH meurt avec le SSH, et la
conversation est archivee cote application. Se detacher avec `Ctrl+b` puis `d`.
Detail complet dans CLAUDE.md, section « Les conversations archivees ».
