# Ou on en est — mis a jour le 22 septembre 2026

## CE QUI A ETE ARME CE SOIR, ET CE QUI NE L'A PAS ETE

**`trail_atr_mult` 3,0 -> 2,0 dans `robot.bitvavo.json`.** Parti d'une
observation de l'operateur sur le BTC de la demo 2, repetee trois fois
avant que je la mesure : « le stop est a 4 000 du cours, c'est enorme ».
Mesure sur le banc de PORTEFEUILLE (un seul compte), 25 cryptos, deux
periodes : 3,0 ATR etait **le seul reglage a perdre de l'argent** sur la
periode recente. Detail complet dans CLAUDE.md, section « le coussin du
suiveur ». 1 092 tests verts.

**Les demos ne sont PAS touchees** — gel jusqu'au 28 demande par
l'operateur. Elles tournent toujours a 3,0 ATR. Le robot reel est a
l'arret depuis le retrait du 16 : le nouveau reglage prendra effet au
depot du 28.

**Son mecanisme de resserrage progressif : mesure, ecarte.** Les trois
reglages qu'il decrivait existaient deja. Aucun dosage ne bat le reglage
simple, et `serrage 3,0 / plancher 0,8` reproduit exactement `1,0 ATR` —
le serrage ne fait que pousser le multiple a son plancher.
`trail_serrage_apres_abri` reste a 0,5, `trail_min_atr_mult` a 0,8.

**Arbitrage TRANCHE** : le choix etait entre 2,0 ATR (le plus rentable,
recul 14,0 % / 12,2 %) et 1,5 ATR (le plus calme, recul 12,2 % / 9,9 %
pour ~160 EUR de moins). L'operateur a choisi **le plus rentable** :
2,0 ATR, deja arme. Le recul de 14 % est accepte en connaissance de
cause — ne pas redescendre a 1,5 « pour lisser la courbe ».

## DEUX DEFAUTS TROUVES AU PASSAGE

1. **CORRIGE** — l'ecran d'une position affichait « Au pire -17,52 EUR »
   alors que son stop etait AU-DESSUS du prix d'achat (gain garanti de
   +3,02). Il lisait le stop d'origine, remplace depuis. C'est ce
   chiffre qui a lance toute la discussion du soir.
2. **EN ATTENTE** — deux lignes EGLD a **volume zero** dans
   `state-demo2.json` (`bc2a33259540`, `11851843dfe0`). Fiches vides qui
   occupent une place pour 0 EUR investi. A nettoyer le 28, demos gelees.

## AVANT CA, LA NUIT DU 21 AU 22

La carte de prix de `ops/battement_comptes.py` etait indexee par ACTIF
et non par MARCHE : les cotations USDC ecrasaient les EUR (+15 % sur onze
actifs), d'ou une courbe a 3 716 EUR contre 3 569 sur la carte de
l'application. **L'application avait raison, pas moi**, et je lui avais
dit l'inverse. Corrige, les quatre releves contamines retires de
`alluxe_bot_capital`.

## A FAIRE LE 28

- recompiler l'APK (correction d'affichage « Au pire » non livree)
- nettoyer les deux lignes EGLD fantomes
- decider si on arme 2,0 ATR aussi sur les demos (demande un redemarrage)
- depot Bitvavo < 500 EUR, moteurs d'images de Luna, domaine reel
- tester ChatGPT Images 2.5 pour Luna : ~3 EUR/mois a notre rythme, mais
  le filtre d'OpenAI refuse peut-etre l'envoi du visage de reference.
  5 EUR de credit suffisent a le savoir.

---

# Ce qui precede date du 20 septembre 2026 (02h30)

## TROIS COMPTES DEMO, dont DEUX qui tournent

Chacun part de 3 300 EUR et ne differe du compte 1 que par UN reglage :

    demo    reference    reserve 1/3, a l'abri des 0,7x le risque   TOURNE
    demo2   experience   MEME chose sauf AUCUNE reserve             TOURNE
    demo3   experience   MEME chose sauf a l'abri des 0,5x          EN ATTENTE

demo3 n'est pas demarre : ~700 Mo libres, il en faudrait 1 300. Ce
serveur ne tient pas trois robots. Son service est pret
(`systemd/robot-demo2.service` comme patron, `robot.demo3.json` existe).

**La question que ces deux robots mesurent** : reserver du budget aux
renforcements change-t-il quelque chose quand le budget sature ? Le
rejeu ne peut PAS y repondre -- sur 40 paires, zero reserve et la
moitie reservee donnent le meme resultat au centime, parce que le
budget n'y sature jamais. Il faut les 240 cryptos du vrai robot.

## MEMOIRE : deux erreurs a moi, corrigees le 20 a 02h20

1. `systemctl set-property MemoryMax=2400M` (19 sept. 19h50) **n'a
   jamais pris effet** : systemd applique les fragments par ordre de NOM
   de fichier, et `memoire.conf` passe apres `50-MemoryMax.conf`. Le
   robot est reste a 1 800 Mo pendant que je le croyais a 2 400.
2. `MemorySwapMax=0` interdisait au robot d'utiliser le swap. Les 2 Go
   ajoutes la veille, justement pour qu'un pic ne tue plus rien, ne lui
   servaient a RIEN.

Reglage actuel, ecrit dans
`/etc/systemd/system/robot-demo{,2}.service.d/memoire.conf` :

    demo    high 1400M  max 2000M  swap 1G
    demo2   high 1000M  max 1400M  swap 512M

Principe : le compte de REFERENCE ralentit sous pression au lieu de
mourir ; si le serveur manque d'air, c'est le compte d'EXPERIENCE qui
cede. **Toujours verifier avec `systemctl show -p MemoryMax --value`,
jamais supposer qu'un set-property a pris.**

## DISQUE : 83 % -> 42 %

`/var/log/syslog` pesait 7,6 Go, ses archives 4,6, le journal 3,8. Le
robot ecrivait un message PAR CRYPTO ecartee, 240 fois par cycle --
pres d'un million de lignes par jour. Corrige a la source (un motif
repete ne s'ecrit plus qu'une fois) + limites posees
(`/etc/systemd/journald.conf.d/taille.conf`, `/etc/logrotate.d/syslog-taille`).

## L'AGENT PEUT GERER LES COMPTES D'EXPERIENCE

Depuis le 20 sept. : il modifie `robot.demo2.json` / `robot.demo3.json`
et pilote `robot-demo2` / `robot-demo3` (`piloter_simulation`, sudoers
nominatif). Il refuse de demarrer sous 1 300 Mo libres.

**Restent interdits** : `robot.bitvavo.json` (argent reel),
`robot.demo.json` (la mesure de reference), `robot-dual-live`,
`alluxe-agent` lui-meme.

## LA CAMPAGNE DE NUIT CEDE LA PLACE

`ops/campagne_nuit.sh` ne demarre plus sous 1 600 Mo libres, et l'ecrit
dans son fichier de sortie. Avec deux simulations en cours elle passera
son tour -- une mesure vaut moins qu'une mesure EN COURS.

## A FAIRE AU REVEIL

1. Envoyer le lien de l'APK (build de 9844b7b lance a 00h09). Il
   contient : 3 onglets demo, ecran de detail d'une position avec
   graphique, tri, Discussion, jaune adouci.
2. Point du matin sur les deux simulations : comparer demo et demo2.
3. Luna : les deux generateurs d'images etaient a sec (HF 402,
   Cloudflare 429). Cloudflare se remet a zero a 00h00 UTC -- verifier
   que ca reproduit.

---

# Ou on en est — mis a jour le 20 septembre 2026 (00h45)

## TELEGRAM EST RETIRE. Tout passe par l'onglet Discussion.

Decision de l'operateur le 19 sept. au soir : il supprime son compte
Telegram. `TelegramChannel` est retire des canaux par defaut et de
`run_demo.py` ; la classe reste en place et testee (la rebrancher est
une ligne).

Verifie de bout en bout avant la coupure :

    commandes (rapport allure / jour / semaine, etat)   OK
    page ALLURE 48 ko avec logo et graphiques           OK
    alertes du robot fusionnees dans le meme fil        OK
    questions au robot avec lecture des vraies donnees  OK
    recherche universitaire (arXiv + Semantic Scholar)  OK

`tests/test_rien_ne_se_perd_sans_telegram.py` verrouille l'equivalence.

**DEUX ECOUTEURS SE PARTAGENT LE FIL, ne pas les fusionner :**

    ops/ecoute_discussion.py   cron, compte `ubuntu`, A les cles   -> commandes
    service alluxe-agent       compte `alluxe`, PAS de cles        -> le reste

L'agent ne PEUT pas faire le rapport (`page_allure` lit le compte
Bitvavo, et il efface les cles de sa memoire au demarrage). Chacun
reclame puis rend la main, via la MEME `gold_bot.commandes.est_une_commande()`.

## L'agent repond dans la Discussion

Le service `alluxe-agent` sert maintenant DEUX tables :
`alluxe_agent_messages` (onglet Agent) et `alluxe_bot_discussion`
(onglet Discussion, avec un prompt oriente robot).

Trois defauts corriges en l'essayant pour de vrai — voir memoire
`telegram-remplace-par-discussion-19-sept` :
message reclame sans reponse, appel d'outil malforme par le modele
(400 `tool_use_failed`, on retente), et `positions_ouvertes` qui
additionnait demo et reel (« 22 positions »).

**Le palier gratuit Groq sature vite** sur ce fil (17 outils +
historique + index memoire a chaque aller-retour). Si les reprises 429
s'enchainent, c'est la premiere chose a alleger.

## APK a jour

https://github.com/allureluxe/Eve-AI-Influencer/releases/download/dernier-build-alluxe-bot/app-release.apk

Construit depuis 0d4ef47. Contient : onglet Discussion, ecran de detail
d'une position (graphique 1m->1j, stop d'ouverture ET stop actuel,
quantite en euros), tri des positions, jaune adouci sur les aplats.

## Luna : moteurs a changer LE 28

Decision : « ok on fait ca le 28 ». Le vrai defaut n'est pas le modele
mais la CONSTANCE DU VISAGE. Image d'abord (Seedream ~2,50 EUR/mois),
voix ensuite, video en dernier. **Tester avant de payer.** Voir memoire
`luna-moteurs-a-changer-le-28`.

---

# Ou on en est — mis a jour le 19 septembre 2026 (23h)

## EN COURS CE SOIR : simulation de 48 h a 3 300 EUR, avec le tiers reserve

Le robot demo tourne depuis **21h06 UTC le 19 sept.** avec deux nouveautes
armees a la demande de l'operateur :

  - capital **3 300 EUR** (il a ajoute 2 800 EUR virtuels ; le depot ne doit
    apparaitre nulle part dans l'application) ;
  - **`reserve_pyramide_pct: 1.67`** dans `robot.demo.json` — un tiers du
    budget de risque que SEUL un renforcement peut utiliser.

Verifie au journal : « budget des nouvelles lignes epuise (5.00% engage,
plafond 3.33% — 1.67% reserve aux renforcements) ». 21 positions reprises,
solde conserve (3 300,00 au centime).

**Premier point a lui donner demain matin**, et a comparer a ce que
500 EUR reels auraient donne : c'est cette mesure qui decide du depot du
28 septembre.

Sauvegardes avant armement : `robot.demo.json.avant-reserve-tiers`,
`data/state-demo.json.avant-reserve-tiers`.

### Ce qui reste a mesurer

`mesurer_point_mort.py` tourne sur 0,4 / 0,5 / 0,7 / 1,0 / 1,5 R, PAR
INSTRUMENT (des centaines de trades, la ou le compte unique n'en donne que
huit). Resultats a lire dans
`/tmp/.../scratchpad/point_mort.jsonl` s'ils y sont encore, sinon relancer.

Deja acquis, sur compte unique (8 trades, donc indicatif seulement) :
point mort a **0,4 R fait tomber le benefice de 321 a 17 EUR** et l'etage
maximum de 7 a 4 — le stop remonte trop tot tue les pyramides qui payent.
Reponse a « presque aucune position fermee en perte » : c'est faisable et
ca coute 95 % du gain. Ne jamais donner le nombre de perdantes sans le
resultat en euros a cote.

### Memoire du serveur — deux morts le 19 sept.

`robot-demo` a ete tue a 10h28 (OOM global) et 19h45 (plafond cgroup). Il
veut ~1,9 Go a lui seul. Corrige : **swap de 2 Go** (`/swapfile`, dans
`/etc/fstab`) et `MemoryMax=2400M`. Surveiller avec
`systemctl show robot-demo -p MemoryPeak -p NRestarts`.

Toute mesure lourde se lance donc **un processus par variante**
(`ops/mesurer_reserve_une_a_une.sh`) : enchainees, elles se font tuer.

---

# Ou on en est — mis a jour le 19 septembre 2026 (soir)

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

## LE PLUS IMPORTANT, decouvert le 19 sept. : la strategie n'a jamais ete testee

Les 41 trades qui donnaient une esperance NEGATIVE ont tous ete produits
par du code bugge. Le break-even posait le stop AU-DESSUS du prix (jusqu'a
+5 000 000 % sur PEPE, mesure) : toute position atteignant +0,7 R etait
donc fermee de force au marche. Une strategie de cassure vit de ses rares
gros gains -- celle-ci n'en a jamais eu le droit. Meilleur gain de tout
l'echantillon : +1,98 R.

Corrige le 18 au soir. **La demo est desormais la seule mesure honnete** :
3 trades termines, 3 gagnants, +1,17 EUR, et l'un est monte a +2,07 R --
mieux en 3 trades qu'en 41. **3 trades ne prouvent rien** (il en faut ~30),
mais on est passe de "ca ne marche pas" a "on ne sait pas encore".

Voir memoire `bug-breakeven-volume-18-sept`.

## Ce qui tourne tout seul chaque nuit

    00h05  ops/photos_profil_luna.py    portrait + couverture de Luna
    01h00  ops/campagne_nuit.sh         17 variantes sur 215 cryptos
    */2    ops/executer_luna.py         file de generation Luna
    */2    ops/suivre_memoire.sh        journal memoire (data/memoire.log)

Les deux taches de nuit sont espacees exprès : les fournisseurs d'images
et le backtest se disputaient la memoire. La campagne de 12h13 est morte
de mon propre plafond de 700 Mo -- elle a 1,5 Go la nuit, quand rien
d'autre ne tourne.

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

## L'agent Alluxe AGIT depuis le 19 sept.

13 outils : fichiers, terminal, web, publications universitaires,
memoire persistante, atelier (`~/atelier`), Tor en option. Il repond en
1,4 s. Tourne sous un compte Unix dedie `alluxe` qui n'a PAS le droit de
lire `.env`. Voir memoire `agent-alluxe-agit-19-sept` -- et l'incident
du jour meme : il a modifie `robot.demo.json` tout seul, d'ou les
configs `robot*.json` passees en LECTURE SEULE.

## Comptes Instagram / Facebook — en cours

`allure._.luxe` + Page `Allure luxe`, separes du compte perso. Application
Meta creee (META_APP_ID et META_APP_SECRET dans .env). **BLOQUE** a
l'etape du jeton d'acces : l'explorateur Graph API est trop confus, et
l'ordinateur de l'operateur s'eteint faute de batterie. A reprendre.

Rappels : TikTok en compte PERSONNEL/CREATEUR (les comptes Business sont
exclus de la remuneration), et la mention "personnage cree par IA" est
obligatoire sur les deux plateformes.

## L'application (Alluxe Bot) — fusion terminee le 16 sept.

## L'agent Alluxe AGIT depuis le 19 sept.

13 outils : fichiers, terminal, web, publications universitaires,
memoire persistante, atelier (`~/atelier`), Tor en option. Il repond en
1,4 s. Tourne sous un compte Unix dedie `alluxe` qui n'a PAS le droit de
lire `.env`. Voir memoire `agent-alluxe-agit-19-sept` -- et l'incident
du jour meme : il a modifie `robot.demo.json` tout seul, d'ou les
configs `robot*.json` passees en LECTURE SEULE.

## Comptes Instagram / Facebook — en cours

`allure._.luxe` + Page `Allure luxe`, separes du compte perso. Application
Meta creee (META_APP_ID et META_APP_SECRET dans .env). **BLOQUE** a
l'etape du jeton d'acces : l'explorateur Graph API est trop confus, et
l'ordinateur de l'operateur s'eteint faute de batterie. A reprendre.

Rappels : TikTok en compte PERSONNEL/CREATEUR (les comptes Business sont
exclus de la remuneration), et la mention "personnage cree par IA" est
obligatoire sur les deux plateformes.

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
