# Décisions de l'opérateur — à lire avant de toucher aux réglages

Ce dépôt pilote un robot qui engage de l'argent réel sur un compte Bitvavo
d'environ 51 EUR. Plusieurs sessions travaillent sur la même branche. Les
décisions ci-dessous ont été prises par l'opérateur ; elles ne sont pas des
valeurs par défaut à optimiser.

## Le stop temporel passe de 12 jours à 5 — armé le 6 septembre

Décision de l'opérateur : « aucune limite de temps tant que la position
évolue, même si elle monte pendant 20 jours — on la laisse faire son
chemin. Si elle fait pratiquement peu de mouvement en 5 jours, là elle
se ferme. »

La règle armée est l'ancienne, **avec un seul chiffre changé** :
`time_stop_minutes` **17 280 → 7 200** (12 jours → 5). Le robot ferme au
5e jour une position dont le R **courant** est sous 0,4. Une position à
+3 R au 20e jour a `r_now = 3` : rien ne la ferme, seul le stop suiveur
décidera. La demande est donc satisfaite telle quelle.

### Ce qui a failli être armé à la place, et pourquoi c'était faux

J'avais d'abord codé une règle « stagnation » lisant le **meilleur
parcours atteint** au lieu du R courant, en justifiant : « une position
montée à +3 R puis redescendue à +0,2 R serait fermée à tort ».

**L'opérateur a demandé : « si elle monte à +3 R avec un bon stop
suiveur, elle sera coupée avant de toucher 0,2 R, non ? »**

Oui. 1 R = 1,6 ATR, le suiveur lâche 2,2 ATR sous le plus-haut, soit
1,375 R :

    pic +0,5 R  ->  suiveur PAS actif (démarre à 1,1 R)
    pic +1,5 R  ->  sortie à +0,12 R
    pic +3,0 R  ->  sortie à +1,62 R

**Le cas que mon raffinement protégeait n'existe pas.** Ce qu'il faisait
réellement, c'était épargner les positions dont le pic est resté entre
0,5 et 1,1 R — trop faible pour armer le suiveur — et les garder ouvertes
pendant qu'elles mouraient.

Ma première mesure changeait **deux choses à la fois** (le délai ET le
critère) et je n'aurais pas dû en tirer une conclusion. Le 2×2, hors
échantillon, frais doublés :

    A  12 j / R courant   +46,0 %   Sharpe 0,61   <- ancien
    B   5 j / R courant   +94,5 %   Sharpe 0,91   <- armé
    C  12 j / pic         +34,7 %   Sharpe 0,52
    D   5 j / pic         +73,1 %   Sharpe 0,79   <- ce que j'allais armer

**Tout le gain vient du délai** (A → B). Le critère « pic » dégrade des
deux côtés (A → C et B → D). J'allais armer la moins bonne des deux
variantes qui marchent, sur une mesure qui confondait deux variables.

Le code de la stagnation reste en place, testé et **désarmé**
(`stagnation_jours: 0.0`), pour que personne ne le recode en croyant
l'inventer. `time_stop_minutes` et `stagnation_jours` ne tournent jamais
ensemble (`elif`, verrouillé par un test).

### La leçon

Un raffinement qui « corrige » un cas doit d'abord prouver que le cas
**se produit**. Celui-ci était impossible sous le stop suiveur armé — il
suffisait de faire la division. Et une mesure qui bouge deux variables
ne dit rien sur aucune des deux.

---

## Pyramidage Turtle — armé le 6 septembre, et le plafond de 6 retiré

> **⚠ DÉPASSÉ LES 9 ET 12 SEPTEMBRE — lire la correction en fin de
> section avant d'agir.** Ce qui suit reste vrai comme *histoire* de la
> décision du 6 septembre, mais **le réglage armé n'est plus « 3 unités »
> et l'illimité n'est plus « le pire des six »** : les deux affirmations
> ont été renversées par une mesure posée autrement. Quiconque
> redescendrait `pyramide_max` à 2-3 « pour réparer une régression »
> défairait une décision plus récente, mesurée deux fois.

Décision de l'opérateur, sur mesure. **C'est le seul réglage testé cette
session-là qui passe le walk-forward** — tous les autres (stop suiveur
desserré, sortie canal, budget de risque relevé) ont été mesurés puis
écartés.

70 paires, 7,5 ans, coupe au 7 juin 2024, frais **doublés**, hors
échantillon (2,2 ans) :

    unites          rendement   Sharpe   recul
    sans pyramidage    -10,9 %   -0,17   26,9 %
    2 unites            -0,3 %   +0,14   30,8 %
    3 unites           +35,8 %   +0,53   35,4 %   <- armé
    4 unites           +23,9 %   +0,42   41,3 %
    6 unites           -40,8 %   +0,05   76,6 %
    ILLIMITE           -84,4 %   -0,57   95,3 %

**Le manuel Turtle dit 4 unités ; sur ces marchés et ces frais la mesure
dit 3.** Et l'illimité — demandé à un moment — est le pire des six.
Monter `pyramide_max` n'est pas « débrider » : c'est reproduire un
résultat mesuré à −84 %. **(Cette phrase est fausse depuis le 9
septembre — voir la correction en fin de section. Elle est conservée
parce que c'est elle qui, laissée seule, ferait redescendre
`pyramide_max` à 3 en croyant bien faire.)**

### Armé, cassé en 3 minutes, réparé — ce que ça a appris

Premier armement à 21h47 UTC : **deux étages sur LINKUSD en 39 secondes,
à 0,013 ATR d'écart pour 0,5 exigé.** Désarmé à 21h50, réparé, réarmé.

**Deux défauts, tous deux silencieux.**

**1. L'espacement ne s'exécutait jamais.** Il s'écrivait :

    if cfg.pyramide_espacement_atr > 0 and prix > 0 and atr > 0:

et les deux appelants du moteur réel (`risk.py`, `dual_scalping_engine.py`)
n'ont jamais passé `prix` ni `atr` — ils tournent dans la phase de
**sélection du scanner, avant le chargement des bougies**. La condition
était donc toujours fausse. `backtest.py`, lui, les passait : **le rejeu
mesurait une règle que le robot n'appliquait pas.**

Corrigé en deux temps : le contrôle **échoue fermé** (sans prix ni ATR il
refuse, il ne laisse plus passer), et la vraie porte est descendue dans
`TradingEngine._execute` — passage obligé de tout ordre, seul endroit où
`ev.entry` et `ev.atr` existent. La phase de sélection dit explicitement
`verifier_espacement=False` : c'est un pré-filtre, plus une porte.

**2. Un second achat ÉCRASAIT le premier.** `_positions` est indexé par
symbole. Le deuxième achat LINK remplaçait l'entrée du premier : volume,
prix d'entrée et frais disparaissaient, et le stop reposé ne couvrait plus
que la dernière tranche. **Le reste de l'avoir restait sur le compte sans
protection, sans le moindre message.**

Au comptant, Bitvavo ne connaît qu'un **avoir** par actif, jamais deux
lignes. La seule modélisation juste — et c'est exactement celle du rejeu —
est **une** position dont le volume grossit et dont l'entrée devient la
moyenne pondérée. `Position` porte désormais `etages` et
`derniere_entree` : sans le premier le plafond ne serait jamais atteint
(`len()` rend toujours 1), sans le second l'espacement se mesurerait
depuis une moyenne qui recule à chaque ajout.

La règle Turtle « tous les stops remontent sous la dernière unité » tombe
alors toute seule : le stop demandé pour le nouvel étage vaut déjà
`dernière_entrée − atr_stop_mult × ATR`, et il s'applique à tout l'avoir.
Il ne redescend jamais.

**La leçon, et c'est la même que trois fois avant dans ce fichier :**
vérifier qu'un réglage est *lu* ne prouve rien. Il faut vérifier qu'il
**s'exécute**. Un garde-fou qui ne peut pas vérifier doit refuser.

### Les deux modèles de sécurité ne se mélangent pas

Le pyramidage d'origine du robot n'ajoutait un étage que si les
précédents **ne pouvaient plus perdre** (`pyramide_locked_r_min`). La
Turtle fait l'inverse : elle ajoute tôt, tous les 0,5 N, et **remonte le
stop de toute la pyramide** sous la dernière unité.

Desserrer le premier sans armer le second laisse trois risques pleins sur
une crypto **sans aucun filet**. D'où `trade.pyramide_relevement_turtle`,
et `TradeManager.plancher_turtle()` qui le calcule.
`tests/test_pyramide.py::TestLeRelevementTurtleRemonteToutePyramide`
verrouille le comportement, et un autre test refuse que
`pyramide_locked_r_min` soit desserré sans son remplaçant.

### `max_positions` est passé de 6 à 99, et ça ne change presque rien

Mesuré : retirer le plafond **seul** donne un résultat identique à la
décimale. Le robot butait sur `max_total_risk_pct` (3,5 % ÷ 0,6 % ≈ 5
lignes), pas sur le compteur — 6 lignes n'arrivaient que 2 % du temps,
5 lignes 35 %. Le plafond était décoratif ; il fallait quand même le
retirer, car **chaque étage de pyramide compte comme une position**.

**Un vrai bug est sorti de là :** le partage du cash divisait par
`max_positions - positions ouvertes`. À 99, chaque part tombait à 0,88 EUR
— sous le ticket minimum — et le robot **aurait refusé chaque trade en
croyant partager**. Le diviseur vient désormais du budget de risque
(`max_total_risk_pct // base_risk_pct`), qui est la vraie borne.

### Ce que ça change, et qui n'a PAS été mesuré

Le rejeu ne contraignait les ajouts que par le cash. Le moteur réel, lui,
fait passer chaque étage par `max_total_risk_pct` : à 0,6 % par unité et
5,0 % au total (3,5 % jusqu'au 10 sept.), **trois étages sur une crypto
consomment 1,8 %** et il
reste peu pour le reste. Le robot pyramidera donc **moins** que le rejeu
ne le montrait. C'est plus prudent, pas plus risqué — mais ce n'est pas
exactement la configuration mesurée, et il faut le savoir avant de lire
les premiers résultats.

`pyramide_fraction_risque` est à **1.0** (étages de même taille), décision
explicite de l'opérateur et valeur mesurée. Le défaut du code reste 0,6.

### CORRECTION du 9 et 12 septembre : illimité, et « à l'abri » au lieu de Turtle

Écrite le 19 septembre, avec dix jours de retard — c'est ce retard qui a
fait afficher de faux chiffres dans l'application pendant une semaine.

**Ce qui a changé, et pourquoi la mesure du 6 septembre n'est pas
contredite.** Le 6 septembre, la comparaison portait sur { 0, 2, 3, 4, 6,
illimité } unités **par configuration globale** — et l'illimité y perdait
(−84 %). Les 9 et 12 septembre, la même question est posée autrement :
non plus « quel plafond choisir ? », mais **« que rapporte une position
selon le nombre d'étages qu'elle a réellement atteints ? »**, à l'intérieur
d'un réglage illimité. Deux périodes différentes, même réponse :

    étages   trades   gagnants   résultat   par trade
    1           399      19 %    −646 €     −1,62 €
    2            29      62 %    +114 €     +3,93 €
    3            17      65 %    +173 €    +10,20 €
    4 à 6        23      78 %    +456 €    +19,84 €
    7 et +       15      93 %    +592 €    +39,47 €

**83 % des trades (un seul étage) sont une perte pure ; ils payent le
droit d'entrée des 17 % qui pyramident.** Plafonner à 3, c'est garder
tout le coût et jeter la queue qui le rembourse. Les deux mesures
répondent à des questions différentes, et seule la seconde dit ce qui se
passe quand on laisse courir.

**Le modèle d'ajout, lui, revient en arrière.** Le Turtle « ajoute tous
les 0,5 N » est ABANDONNÉ (9 sept.) : ajouter tôt remonte le prix moyen,
donc une pyramide qui meurt à 2 étages coûte plus qu'une position simple
(les tentatives à 1-5 étages coûtaient −5 517 €, les pyramides à 6+
rapportaient +4 872 €). `pyramide_locked_r_min = 0.01` : **un étage ne
s'ajoute que si le stop de toute la pyramide est déjà au-dessus du prix
moyen** — elle ne peut plus perdre avant chaque nouvel ajout.

    variante                      résultat    recul max      OOS    recul OOS
    illimité SANS l'abri            −64,2 %      93,1 %   +62,1 %      49,5 %
    illimité + À L'ABRI (armé)  +18 620,7 %      34,6 %  +255,1 %      33,7 %
    sans pyramidage                 −35,7 %      61,0 %   −19,7 %      36,6 %

Vérifié avant armement : levier moyen 0,24x (jamais au-dessus de 1x),
1009 trades sur 1222 ne pyramident jamais, et le résultat tient même en
retirant le meilleur trade. Chien de garde recalé sur ce recul :
`PLANCHER_PCT` (`ops/chien_de_garde.py`) à **0,55**.

**Ne pas confondre les deux réglages.** `pyramide_max` = combien d'étages
au total (99, illimité). `pyramide_locked_r_min` = la condition pour en
ajouter un (0,01 = à l'abri). Le second est ce qui rend le premier sûr.

### La leçon de ce retard, qui vaut pour ce fichier entier

Ce fichier est lu au démarrage de **chaque** session. Une décision armée
et non écrite ici ne disparaît pas : elle continue de tourner en prod
pendant que le fichier raconte autre chose — et ce sont les textes
recopiés à la main depuis ce fichier (la « méthode » affichée dans
l'application, le rapport du matin) qui propagent l'erreur jusqu'à
l'opérateur. **Tout changement de configuration armé se réécrit ici dans
la foulée**, et tout affichage qui décrit un réglage doit le *lire* dans
la configuration plutôt que le recopier (corrigé le 19 sept. dans
`ops/publier_alluxe_bot_prive.py` et `rapport_matin.py`, verrouillé par
`tests/test_methode_publiee.py`).

---

## `comparer.py` mesure des COMPTES SÉPARÉS — 19 septembre

> **⚠ CORRECTION DU 20 SEPTEMBRE — les chiffres « UN SEUL compte » de
> cette section sont FAUX, et le raisonnement qu'ils portent avec eux.**
> Le rejeu de portefeuille était **à l'arrêt 99,2 % du temps** quand ils
> ont été produits. Lire le bloc ci-dessous avant de s'appuyer sur quoi
> que ce soit de cette section. Le reste — la critique de `comparer.py`,
> la raison d'être du rejeu de portefeuille, le verrou à un instrument —
> reste exact : c'est la **méthode** qui était juste et la **mesure** qui
> était morte.

### Le rejeu était bloqué par sa propre pause — 20 septembre

Trouvé en cherchant pourquoi une méthode candidate ne prenait que
4 trades sur 580 jours et 40 cryptos. Les motifs de refus, affichés pour
la première fois, ont donné la réponse — et elle ne parlait pas de la
méthode :

    21 720 refus  « pause apres pertes »
       150 refus  « donchian »   <- la strategie
        11 trades

**DEUX HORLOGES.** À la 4e perte consécutive, `record_close` posait
`paused_until = time.time() + 45 min`, soit septembre 2026. Le rejeu,
lui, appelle `can_trade(ts=candle.ts)` avec une date de 2024 :
`now < paused_until` restait vrai pour **toutes** les bougies suivantes.
La pause ne se levait jamais. Et la purge écrite exprès pour ça — « sans
cette remise à zéro, le robot ne sort plus jamais du régime punitif » —
ne pouvait pas s'exécuter : elle vient **après** le `return False`.

**Le robot réel n'a jamais été touché.** Ses quatre appelants
(`engine`, `scalping_engine`, `dual_scalping_engine`) laissent `ts` à
None : même horloge des deux côtés. Seul le rejeu passe une date
historique, et c'est le **mélange** des deux qui cassait. La pause part
désormais de `trade.closed_at` — juste dans les deux mondes.

Mêmes 40 paires, mêmes 900 bougies, avant et après :

    avant :  11 trades   +270 E   recul  7,0 %
    apres : 563 trades   +335 E   recul 27,2 %

**Ce que ça invalide, nommément :**

- « 11 trades en deux ans et demi », et le trade unique à 7 étages qui
  faisait 131 % du bénéfice — il n'y avait pas 11 occasions, il y avait
  563 occasions dont 552 refusées par une pause morte ;
- « le rendement par euro est meilleur sur un compte » (+8,2 % contre
  +1,0 %) : les deux termes ne mesuraient pas la même chose ;
- **« aucune position ne dépasse l'étage 1 sur un compte unique »**,
  qui a motivé `reserve_pyramide_pct` le 19 septembre. Un robot à
  l'arrêt ne pyramide évidemment pas — mais pas pour la raison qu'on
  croyait. **La réserve n'est ni justifiée ni disqualifiée : elle est
  non mesurée.**
- la limite par famille armée sur la démo 2, qui donnait un résultat
  **identique** à 99, 3, 2 et 1. On sait pourquoi : à l'arrêt, aucune
  valeur ne pouvait se distinguer. Cette mesure ne disait pas le faux,
  elle ne disait **rien**.

**Pourquoi aucun test ne pouvait le voir :** tous appellent
`can_trade()` sans `ts`, donc dans le monde où le défaut est invisible.
C'est la variante « deux horloges » du piège recensé quatre fois dans ce
fichier — un garde-fou qui *s'exécute*, mais pas dans le monde qu'on
croit. `tests/test_pause_horloge_du_rejeu.py` le verrouille, dont un
test qui vérifie qu'en réel **rien ne change**.

**La leçon, et elle est opérationnelle :** un rejeu qui rend peu de
trades doit être sommé de dire **pourquoi** avant qu'on lise son
résultat. `mesurer_momentum.py --pourquoi` affiche les motifs de refus ;
sans cette colonne, « 4 trades, −1,4 % » se lit comme un verdict sur une
méthode alors que c'est un verdict sur le banc d'essai.

---

**À lire avant d'interpréter le moindre chiffre de ce fichier.**

`comparer.py` ouvre un compte **neuf par instrument**, doté du capital
entier et du budget de risque entier, puis **additionne les profits** :

    for sym in symboles:
        res = Backtester(cfg).run(sym, start_balance=args.capital)
        profit += res.end_balance - res.start_balance

Mesurer 70 paires ainsi, ce sont **70 comptes**, pas un robot qui les
arbitre. Chaque crypto y pyramide jusqu'à 8 étages sans jamais croiser
les autres. Le robot réel, lui, n'a qu'une enveloppe : mesuré le
19 septembre sur la démo, **165,07 EUR de risque engagé pour 165,00
autorisés** — plein au centime, « risque total déjà engagé (5,00 %) » à
chaque cycle.

L'écart mesuré, 55 paires et 900 bougies :

    comptes separes   581 trades   +1 766 EUR   sur 181 500 EUR engages
    UN SEUL compte     11 trades     +270 EUR   sur   3 300 EUR

Le rendement par euro est **meilleur** sur un compte (+8,2 % contre
+1,0 %) : la concentration travaille. Mais **11 trades en deux ans et
demi**, dont un seul — une pyramide à 7 étages, +354 EUR — fait 131 % du
bénéfice. Sans lui, la période est négative. Le budget se remplit avec
les cinq premières cryptos qui se présentent, puis plus rien pendant des
semaines.

`gold_bot/backtest_portefeuille.py` répond à l'autre question : « que
donne ce réglage sur UN compte ? ». Les instruments y défilent
chronologiquement (tas ordonné) en partageant un courtier et un
`RiskManager`. **Il ne remplace pas `comparer.py`**, qui reste le bon
outil pour comparer deux réglages à armes égales, sans que la
concurrence entre paires brouille le signal.

Le verrou qui empêche ce second moteur de mentir : **à un seul
instrument, il doit rendre exactement le résultat de `Backtester.run`**
(`tests/test_backtest_portefeuille.py`). D'où le refactor de
`Backtester.preparer()` en parcours pilotable — un seul corps de bougie,
deux pilotes. Dupliquer ce corps aurait refait l'erreur que ce fichier
raconte quatre fois déjà.

### Le simulateur ne pyramidait pas du tout

Trouvé en cherchant pourquoi aucune position ne dépassait l'étage 1,
**même avec le budget entier disponible** : 860 trades, aucun étage 2.

`PaperBroker.open_position` créait une position **neuve** à chaque achat.
Au comptant Bitvavo ne connaît qu'un avoir par actif, et le vrai
courtier fusionne (`bitvavo.py` : volume cumulé, entrée moyenne
pondérée, **un seul stop** pour tout l'avoir). Le simulateur, lui,
empilait des lignes indépendantes portant chacune « étage 1 ».

Constaté dans la démo en service : AVAX, NEO et OP portaient chacun DEUX
lignes, la seconde achetée plus cher — du pyramidage manuel du livre —
et l'application affichait « étage 1 » partout.

Le plus grave n'est pas l'affichage : **deux lignes = deux stops
indépendants**, là où le compte réel n'en a qu'un, posé sous la dernière
unité. La démo ne mesurait pas le risque que l'argent réel porterait.

`ClosedTrade.etages` a été ajouté dans la foulée : le chiffre sur lequel
repose le pyramidage illimité n'était enregistré **nulle part** — ni au
journal, ni au rejeu. La mesure du 9 septembre était irreproductible.
Elle a été refaite, et elle tient :

    etages   trades    resultat    par trade
      1        400     -2 295 E     -5,74 E     <- 69 % des trades
      2        112       +954 E     +8,52 E
      3         45     +1 500 E    +33,32 E
      4         16       +935 E    +58,45 E
      5          7       +748 E   +106,86 E
      7          1       +405 E   +404,55 E

### `reserve_pyramide_pct` — REMESURÉE le 20 septembre : elle ne sert à rien

Sur le banc réparé, `robot.demo.json`, 15 paires, 700 bougies, un compte
de 3 300 EUR :

    variante                trades   perdantes   resultat   recul
    aucune reserve             147    92 (63%)     +107 E   18,6 %
    un quart                   147    92 (63%)     +107 E   18,6 %
    UN TIERS (arme le 19)      147    93 (63%)     +102 E   18,6 %
    la moitie                  144    95 (66%)      +74 E   18,2 %

**Elle échoue sur les deux critères à la fois** : plus de perdantes
(92 → 93 → 95) ET moins de résultat (+107 → +102 → +74), pour un recul
inchangé. La progression est monotone sur quatre paliers — une
direction, pas du bruit.

**Le constat qui la justifiait est faux.** On avait écrit « aucune
position ne dépasse l'étage 1 sur un compte unique ». Mesuré :

    etage 1   108 trades   22 gagnants   -565 E    -5,23 E / trade
    etage 2    28 trades   22 gagnants   +242 E    +8,66 E
    etage 3     9 trades    9 gagnants   +373 E   +41,43 E
    etage 4     1 trade      1 gagnant    +19 E   +19,09 E
    etage 5     1 trade      1 gagnant   +123 E  +123,26 E

Les pyramides montent **jusqu'à l'étage 5 toutes seules**, et rapportent
757 EUR contre 565 perdus par les positions à un seul étage. Le budget
ne les empêchait pas — c'est la pause morte qui arrêtait le robot au
bout de quatre pertes. Leur réserver de l'argent ne fait donc
qu'empêcher de nouvelles lignes de s'ouvrir, et comme il faut une
première ligne avant de pouvoir la renforcer, **la réserve se mord la
queue** : à la moitié, on perd trois trades et 33 EUR.

Limite honnête de cette mesure : **15 paires**, parce que le serveur ne
tient pas plus avec deux robots actifs. Sur un univers plus large le
budget saturerait davantage. Le signe est net, l'amplitude est petite.

**La leçon, et c'est la troisième fois dans ce fichier :** un
raffinement qui corrige un cas doit d'abord prouver que le cas **se
produit**. Ici le cas n'existait pas sous la forme qu'on lui prêtait.

### `reserve_pyramide_pct` — décidé, pas encore armé (19 septembre)

Décision de l'opérateur le 19 septembre : « tu bloques désormais un
tiers du capital aux pyramides ». Une nouvelle ligne et un étage
puisaient dans la même enveloppe, premier arrivé premier servi — donc le
robot dépensait tout son budget sur la catégorie qui perd.

`risk.reserve_pyramide_pct` met de côté une part que **seul** un
renforcement peut utiliser. Garde-fou : elle ne descend jamais le
plafond des nouvelles lignes sous le risque d'un seul trade, sinon
aucune première entrée ne passerait, donc aucune pyramide ne naîtrait —
la réserve se mordrait la queue.

**Valeur armée : 0.** `mesurer_reserve.py` tranche avant.

### « Presque aucune position fermée en perte » — ce qu'il faut répondre

Demande de l'opérateur, le même soir. C'est faisable et c'est le piège
le plus cher du métier : **cette stratégie gagne parce qu'elle perd
souvent.** 69 % des trades perdent 2 295 EUR ; les rares pyramides
rapportent 4 542 EUR. Les petites pertes sont le prix d'entrée des
grosses pyramides — c'est le même geste, et on ne sait pas au moment
d'entrer laquelle des deux on achète.

Le seul vrai levier est `breakeven_at_r` (0,7 aujourd'hui) : remonter le
stop au prix d'achat plus tôt réduit les perdantes et coupe des
gagnantes avant qu'elles ne courent. Ne jamais donner le nombre de
perdantes sans le résultat en euros à côté.

---

## Le coussin du suiveur : 3,0 → 2,0 ATR — armé le 22 septembre

Décision de l'opérateur, sur sa propre observation, répétée trois fois
avant que je la mesure :

    « 70 900 stop et cours actuel 74 900, c'est énorme sur le BTC. Pour
    redescendre de 4 000 on perd tout le bénéf. »

    « Le stop doit monter à chaque fois que la position monte. Et 4 000
    entre les deux c'est beaucoup trop. »

### Ce qu'il fallait lui répondre d'abord, et qui reste vrai

Deux de ses trois griefs ne tenaient pas, et il faut les avoir en tête
pour ne pas sur-corriger :

- **Le stop montait déjà à chaque nouveau plus-haut.** `trail =
  max_favorable − mult × ATR`, cliquet, jamais redescendu. Le mécanisme
  ne manquait pas.
- **Le stop en question ne pouvait plus perdre** : à 70 993 pour un
  achat à 70 421, c'était le POINT MORT, pas un stop de perte. Ce que
  l'écran appelait « au pire −17,52 € » était le coût de l'ancien stop,
  disparu depuis. **Défaut d'affichage à corriger.**
- **Le stop est déjà calculé crypto par crypto** — c'est l'ATR. Et en
  pourcentage du prix, le BTC avait le stop LE PLUS SERRÉ des deux
  comptes (4,8 %, contre 8 à 15 % ailleurs). Ce qui trompe l'œil, c'est
  que 4,8 % de 75 000 € fait un gros nombre.
- **Un stop large ne risque pas plus d'argent**, il achète moins. Les
  risques par position de la démo 2 : 17,85 € sur BTC, 17,75 € sur RUNE,
  19,46 € sur ATOM. Identiques par construction.

### Ce sur quoi il avait raison, et que la mesure confirme

Le troisième grief — **le coussin est trop large** — est exact. Banc de
portefeuille (UN compte, le cadre qui reproduit le robot réel),
25 cryptos, 500 jours, `robot.demo.json` :

    coussin                    trades  perdantes  résultat  recul  garde
    3,0 ATR (en service)         162    111 (69%)    −36 €  15,5 %   18 %
    2,5 ATR                      159    107 (67%)   +181 €  13,5 %   21 %
    2,0 ATR                      158    104 (66%)   +297 €  14,0 %   24 %  <- armé
    1,5 ATR                      164    105 (64%)   +174 €  12,2 %   26 %
    1,0 ATR                      158     94 (59%)   +104 €  12,5 %   32 %

Période ANTÉRIEURE (décalage 500), que le réglage n'a pas servi à choisir :

    3,0 ATR                      140     80 (57%)   +580 €  15,5 %   25 %
    2,5 ATR                      141     81 (57%)   +735 €  14,2 %   27 %
    2,0 ATR                      141     81 (57%)   +819 €  12,2 %   29 %
    1,5 ATR                      141     79 (56%)   +657 €   9,9 %   35 %

**Même classement, même vainqueur, sur les deux périodes.** Et le réglage
en service était le SEUL à perdre de l'argent sur la période récente.

La colonne « garde » est celle qui traduit la plainte : part du meilleur
parcours réellement encaissée sur les trades gagnants. 18 % à 3,0 ATR —
on rendait 82 % de ce qu'on avait vu.

**Le bas de l'échelle existe.** À 1,5 puis 1,0 le résultat redescend :
on recommence à couper les gagnants, le frein identifié le 12 septembre.
2,0 est un sommet, pas une direction.

### Pourquoi ça ne contredit PAS la mesure du 12 septembre

Le 12 septembre, 3,0 battait 2,0 — « médiane 697 € contre 519 €, six
périodes sur six ». Cette mesure venait de `comparer.py`, qui ouvre **un
compte neuf par crypto** et additionne. Celle-ci vient de
`backtest_portefeuille.py` : **un seul compte**, budget de risque
partagé, comme le vrai robot.

Ce n'est pas la même question, et le cadre change la réponse : à comptes
séparés, une position qui respire longtemps ne prive personne. Sur un
compte unique, elle occupe le budget que la crypto suivante attend. Un
coussin large y coûte deux fois — en bénéfice rendu, et en occasions
manquées.

Et le rejeu de portefeuille était **à l'arrêt 99,2 % du temps** jusqu'au
20 septembre (voir la section « deux horloges »). Aucune mesure de
coussin n'avait donc jamais été faite dans ce cadre.

`tests/test_pyramide.py` verrouille la plage 1,6–3,5 ATR : 2,0 y entre.
La borne basse tient toujours — sous 1,6 la mesure honnête est négative
hors échantillon dès que le gap d'ouverture est modélisé.

### Ce qui n'est PAS armé, et pourquoi

**Les démos ne sont pas touchées.** Consigne de l'opérateur du
20 septembre : « on laisse tourner les mode démo jusqu'au 28 sans rien
toucher ». Changer leur configuration en cours d'expérience détruirait
la comparaison des deux méthodes. Seule `robot.bitvavo.json` est
modifiée — le robot réel est à l'arrêt depuis le retrait du 16, le
réglage prendra effet au dépôt du 28.

### Le mécanisme demandé : MESURÉ, et il ne bat pas le réglage simple

L'opérateur voulait que le resserrage s'accentue à chaque montée, avec
un plancher « pour pas faire fermer la position sur un petit
retournement ». Les trois réglages existaient déjà : `trail_atr_mult`
(coussin de départ), `trail_serrage_apres_abri` (0,5) et
`trail_min_atr_mult` (0,8, le plancher). Rien à construire, seulement à
doser. Quatre dosages, les deux mêmes périodes :

    variante                            récent          antérieur
    2,0 ATR seul (ARMÉ)           +297 / 14,0 % / 24    +819 / 12,2 % / 29
    2,0 + serrage 3,0 + pl. 0,8   +258 / 13,6 % / 26    +579 /  8,2 % / 35
    2,0 + serrage 3,0 + pl. 1,2   +227 / 13,5 % / 24    +445 / 10,0 % / 30
    2,5 + serrage 3,0 + pl. 1,2   +136 / 13,5 % / 23    +522 / 10,0 % / 28
    2,0 + serrage 6,0 + pl. 1,2   +234 / 13,4 % / 25    +466 / 10,0 % / 31

**Aucun dosage ne bat le réglage simple, sur aucune des deux périodes.**
Le serrage fort achète de la « garde » (24 → 35 %) et un recul plus
petit, mais il le paie plus cher qu'il ne rapporte.

**Et il n'apporte rien de propre.** À `serrage 3,0 / plancher 0,8` sur
la période antérieure, le résultat (+579 €), le recul (8,2 %) et la
garde (35 %) sont ceux de **1,0 ATR tout court** (+584, 8,2 %, 37 %).
Le serrage fort ne fait que ramener le multiple à son plancher : c'est
une façon compliquée d'obtenir un coussin serré, avec deux réglages de
plus à surveiller.

`trail_serrage_apres_abri` reste donc à **0,5** et `trail_min_atr_mult`
à **0,8** — inchangés. La seule variable qui compte est le coussin.

### L'arbitrage a été tranché : « le plus rentable »

Deux réglages se tenaient, et le choix n'était pas calculable :

    2,0 ATR   +297 / +819 EUR   recul 14,0 % / 12,2 %   garde 24 % / 29 %
    1,5 ATR   +174 / +657 EUR   recul 12,2 % /  9,9 %   garde 26 % / 35 %

1,5 rapporte ~160 EUR de moins sur la période mais creuse ~75 EUR de
moins dans les mauvais moments. Question de tempérament, pas de mesure.

**Décision de l'opérateur, 22 septembre : « le plus rentable ».**
`trail_atr_mult = 2.0`, déjà armé. Ne pas redescendre à 1,5 « pour
lisser la courbe » : le recul plus élevé est accepté en connaissance de
cause, les deux chiffres lui ont été donnés côte à côte.

Le corollaire à ne pas oublier quand la courbe piquera : à 2,0 ATR le
recul mesuré monte jusqu'à **14 %**. Ce n'est pas une dérive, c'est le
prix du réglage choisi.

---

## D1 « Turtle » — armé le 3 septembre, remplace le M30

**Le M30 était perdant, et la mesure est certaine :** −0,158 R sur
**3 147 trades** (±0,04). Sur 1 000 EUR de capital de rejeu, −1 643 EUR
en six mois. Ce n'est plus une hypothèse.

    strategie                 in-sample     OOS   total 6m   trades     EUR
    D1 canal-20 (armée)          +0,104  +0,214    +0,130       450    +428
    M30 quorum (remplacée)       -0,171  -0,138    -0,158      3147   -1643

### Pourquoi la décision du 30 août était fausse

Elle reposait sur **8 paires et ~30 jours** — le fournisseur de données
plafonnait là sans le dire, quel que soit le `--bars` demandé. Et
`comparer_famille.py` forçait `entry_tf = "M30"` depuis toujours : **le D1
n'avait jamais été mesuré** sur des données longues aux vrais frais.

Remesuré sur **70 paires** (les instruments du bot qui existent en EUR
chez Bitvavo) et **6 mois** en walk-forward, le classement s'inverse.

### Ce qui est armé

> **⚠ Ce tableau a été corrigé le 19 septembre.** Quatre de ces valeurs
> avaient été remplacées les 9-12 septembre sans que ce fichier soit mis
> à jour, et il a menti pendant une semaine — jusqu'à ce que l'opérateur
> voie « canal 20 jours » affiché dans l'application alors que le robot
> tournait sur 10. Les valeurs ci-dessous sont celles de
> `robot.bitvavo.json`, **vérifiées le 19 septembre**. Les anciennes sont
> conservées en dernière colonne : elles gardent leur raisonnement, mais
> elles ne sont plus armées.

| réglage | valeur ARMÉE | pourquoi | avant |
|---|---|---|---|
| `strategy.famille` | **donchian** | cassure du plus-haut de canal | — |
| `strategy.entry_tf` | **D1** | frais 7 % du risque contre 47 % en M30 | — |
| `strategy.donchian_entrees` | **[10]** | 12 sept. : le canal 10 bat le canal 20 sur les SIX périodes mesurées (médiane 1 109 € contre 323 €) | [20] |
| `trade.tp_actif` | **false** | 9 trades sur 469 font 124 % du bénéfice ; le plafond les coupait tous à 5,77 R | — |
| `trade.micro_profit_enabled` | **false** | coupait ~70 gagnants entre 1 et 2 R — le plus gros frein | — |
| `trade.trail_atr_mult` | **2.0** | 22 sept. : remesuré SUR UN COMPTE UNIQUE, deux périodes — voir la section « le coussin du suiveur » | 2.2 puis 3.0 |
| `risk.pyramide_max` | **99** (illimité) | 9 et 12 sept. : mesuré PAR NOMBRE D'ÉTAGES, pas par présence/absence — voir la section pyramidage | 0 puis 3 |
| `risk.pyramide_locked_r_min` | **0.01** | un étage ne s'ajoute que si la pyramide est déjà à l'abri (stop au-dessus du prix moyen) | 0,5 N « Turtle » |
| `risk.pyramide_espacement_atr` | **0.25** | 12 sept., mesuré avec le canal 10 | 0.5 |
| `risk.max_total_risk_pct` | **5.0** | 10 sept. : seul palier qui améliore l'apprentissage ET le hors-échantillon, et le recul BAISSE (34,0 → 29,7 %) | 3.5 |
| `risk.ticket_min_eur` | **15.0** | 10 sept., correction d'un calcul de référence | 20.0 |
| `risk.base_risk_pct` | **0.6** | palier « preuve » — pas le 1 % du Turtle | — |

Le prix assumé du canal 10 : **le recul maximal double** (13,8 → 26,9 %),
et la cadence passe de 83 à 233 trades par an. C'est une décision
explicite de l'opérateur — « je ne veux pas d'un robot dormeur » — prise
sur une mesure où le nouveau réglage bat l'ancien dans les six périodes,
y compris le pire cas.

### Mesuré puis écarté — ne pas y revenir sans nouvelle mesure

- **Le pyramidage.** Cinq configurations (prudente, Turtle 0,5N, ×2, ×4,
  décroissante). Toutes améliorent l'in-sample et **dégradent l'OOS**
  (+0,134 → −0,027). C'est du sur-ajustement, pas un réglage à trouver.
- **Le Turtle authentique** (stop 2N, sortie canal 10 j, filtre System 1,
  risque 1 %) : **−0,044 à −0,443 R**. Il lui manque la vente à découvert,
  moitié du système, que le compte au comptant interdit.
- Délai de carence après sortie, stop commun de pyramide, bande RSI
  resserrée, regroupement des confirmations corrélées : neutres ou nuisibles.

### Deux pièges rencontrés en armant

**`tp_r_multiple = 99` désarmait un garde-fou.** La réussite nécessaire
vaut `(1 + frais) / (1 + objectif)` : un objectif de 99 la fait tomber à
2 % pour **toutes** les unités, M5 compris. Un nombre magique qui neutralise
une barrière en silence est pire que le problème qu'il résout. D'où
`tp_actif: bool`, et un garde-fou fondé sur le **rapport frais/risque** —
qui protège quel que soit le mode de sortie, et refuse désormais aussi
le M30.

**Deux endroits décidaient du même réglage.** `tp_actif` n'était lu que
dans `initial_levels` ; la stratégie reposait sa propre cible à 2 R par
l'autre bout. L'espérance tombait de +0,130 à +0,044 R — **sans erreur,
sans test rouge, 656 tests verts avec le bug dedans**. Trouvé en
re-mesurant la configuration *réellement armée* au lieu de supposer
qu'elle valait celle du banc d'essai. C'est la règle : ne jamais
interpréter un chiffre sans avoir vérifié que la mesure mesure bien ce
qu'on croit.

### Ce que ça change au quotidien

**~1 trade par jour** sur 70 paires, contre ~30 en M30. Les 40 trades de
preuve prendront **plusieurs semaines**, pas trois jours. Et la stratégie
ne vit que de ses rares gros trades : **9 sur 469 font 124 % du bénéfice**.
Une semaine sans gain n'est pas un signal d'échec, c'est le régime normal.

Chien de garde : **plancher à −55 % du pic** (`PLANCHER_PCT = 0.55` dans
`ops/chien_de_garde.py`, relevé le 9 sept. pour suivre le recul mesuré du
pyramidage illimité ; c'était −37 % auparavant, soit 100 EUR pour un pic
à 158). Décision explicite de
l'opérateur pour laisser respirer une stratégie qui tient ses positions
plusieurs jours. Tolérer −37 % est un choix assumé.

---

## M30 au comptant, achat seul

Décision du **30 août**, prise sur le rejeu et non sur le raisonnement.
Elle remplace le H1 du 29 août, lui-même successeur du H4 et du D1.

### La vente à découvert coûtait de l'argent

Le compte n'a pas la marge activée — Bitvavo répond `Net liquidation not
found` sur `/netLiquidation`. En mesurant la même stratégie **sans les
ventes**, le résultat s'est amélioré :

    M30 avec ventes     159 trades   56,6 %   +0,273 R   +42,83 EUR
    M30 achat seul      130 trades   60,0 %   +0,352 R   +48,31 EUR

Les ventes coûtaient **3,4 points de réussite**. La contrainte du compte
et le meilleur réglage coïncident, ce qui règle la question : `broker`
reste `"bitvavo"` (comptant), `max_leverage` à **1.0**.

Le H4 en tendance, lui, passe de +0,130 R à **−0,098 R** sans les ventes :
tout son avantage venait des ventes à découvert. Il n'est donc plus un
repli.

Attention : le rejeu **ne pose aucune contrainte de cash** et ne tient
qu'une position à la fois. Il mesure des positions PLEINES. C'est pourquoi
le dimensionnement réel doit servir chaque position à la taille voulue par
le risque plutôt que de pré-découper le budget — voir plus bas.

**Ce qui a changé de nature :** les versions précédentes déduisaient
l'unité de temps d'un ratio frais/risque jugé acceptable. Le rejeu du
30 août — 8 cryptos, 4000 bougies, frais pleins et **spread doublé** — a
départagé douze variantes, et le classement contredit ce raisonnement :

    M30, plafond 50 %    159 trades   56,6 %   +0,273 R   +42,83 EUR
    H4 tendance 3R       134 trades   49,3 %   +0,130 R   +18,94 EUR
    H4 tendance 2R       136 trades   48,5 %   +0,096 R   +15,41 EUR
    H1 (ancienne)         81 trades   43,2 %   +0,073 R    +4,80 EUR
    D1 tendance 2R       172 trades   45,3 %   -0,067 R   -11,04 EUR

**L'unité la plus lente est la pire**, alors que c'est elle qui paie le
moins de frais (7 % du risque contre 47 % au M30). Payer cher n'est pas le
problème ; ne pas avoir d'avantage l'est. La littérature académique sur le
momentum crypto — qui pointait vers des horizons longs — ne se vérifie pas
sur ce moteur et ces marchés.

| réglage | valeur | ne pas |
|---|---|---|
| `strategy.entry_tf` | **M30** | changer sans repasser par `comparer.py` |
| `risk.max_cost_ratio_pct` | **50.0** | remonter pour « débloquer » le M15 ou le M5 |
| `strategy.max_cost_ratio_pct` | **50.0** | idem |
| `trade.max_cost_ratio_pct` | **50.0** | idem |
| `risk.max_leverage` | **1.0** | monter : le compte est au comptant, la plateforme refusera |
| `engine.broker` | **bitvavo** | repasser en marge sans avoir remesuré : les ventes faisaient perdre |
| bloc `promotion` | **présent** | retirer |
| `strategy.max_spread_atr_ratio` | **0.30** | monter : à 50 % de plafond, la borne dérivée ne protège plus, ce réglage est la seule barrière |
| `strategy.min_score` | **0.45** | redescendre à 0,35 : quatre rejeux le donnent perdant, voir plus bas |
| `trade.atr_stop_mult` | **1.60** | resserrer sans recalculer le coût |
| `trade.tp_r_multiple` | **2.00** | baisser sans recalculer la réussite nécessaire |
| `trade.time_stop_minutes` | **360** | garder une valeur pensée pour une autre unité |

### La marge est mince, et c'est le point important

Le M30 gagne **7,6 points** de réussite au-dessus de son seuil de
rentabilité (56,6 % mesurés contre 49,0 % nécessaires). Le H4, lui, en
gagne 19,8.

    stratégie        frais/risque   seuil   mesuré    marge
    M30 (retenu)          47 %      49,0 %  56,6 %   +7,6 pts
    H4 tendance 3R        18 %      29,5 %  49,3 %  +19,8 pts

Un système perd toujours en réel une part de ce qu'il montrait en rejeu —
glissement, ordres refusés, élargissements de spread sur annonce, qu'aucun
rejeu ne reproduit. Sur 7,6 points, cette perte se voit.

Conséquence : les coupe-circuits et le palier de croissance ne sont pas du
confort ici, **ils sont la condition de la décision**. Si la réussite
réelle tombe sous 52 % sur 40 trades, il faut basculer sur le H4 plutôt
que d'attendre.

### Ce qui distingue ce plafond de celui du 29 août au matin

Le 29 août, le plafond avait été monté à **70 %** pour laisser passer le
M5. La réussite nécessaire valait alors **122,5 %** : aucune mesure ne
pouvait sauver ça, et le plafond servait à ne pas voir l'impossibilité.

Ici, la réussite nécessaire vaut 49 % et la mesure en donne 56,6. On n'a
pas desserré une mesure pour laisser passer un trade perdant : on a
constaté qu'un ratio de frais élevé reste payant **quand le taux de
réussite le porte**. La différence n'est pas de degré, elle est de nature.

Le M5, lui, reste exclu : il exigerait 75 % de réussite, soit un tiers de
plus que tout ce que ce robot a jamais montré.

`tests/test_garde_fous.py` verrouille ces valeurs. Si un test y échoue, ce
n'est pas le test qu'il faut changer.

### Pourquoi le plafond de coût est passé de 15 % à 35 %

**Ce n'est pas un desserrage : le plafond suit le stop.**

Bitvavo prélève 0,25 % par côté au marché. Le robot entre et sort au
marché, donc 0,50 % l'aller-retour, plus 0,10 % de spread et de glissement
qu'aucune promotion n'annule : **0,60 % à absorber par trade**.

Le plafond à 15 % avait été calculé pour un stop H4 de 3,1 % du prix. Le
H1 divise le stop par deux : à 1,6 ATR il vaut 1,79 %, et les mêmes 0,60 %
y pèsent 33 %. Exiger 15 % au H1 reviendrait à imposer un stop de 4 % —
c'est-à-dire du H4 déguisé en H1.

Le plafond reste donc une **mesure**, et la division est refaite :

    unité   ATR      stop 1,6 ATR   frais / risque
    M5      0,30 %      0,48 %          125 %
    M15     0,56 %      0,90 %           67 %
    M30     0,80 %      1,28 %           47 %
    H1      1,12 %      1,79 %           33 %   <- retenu
    H4      2,24 %      3,58 %           17 %

Avec un objectif à 2,0 R, la réussite nécessaire pour une espérance nulle :

    H1  ->  44,5 %      M5  ->  impossible

### Ce qui s'est passé le 29 août au matin, et qu'il ne faut pas refaire

La configuration avait été passée en **M5, plafond de coût 70 %**. À ce
réglage :

    frais = 182 % du risque  ->  réussite nécessaire : 122,5 %

**Un chiffre supérieur à 100 % n'est pas un objectif difficile : c'est une
impossibilité arithmétique.** Le robot n'était pas mal réglé, il était
mathématiquement condamné, et le plafond à 70 % existait précisément pour
laisser passer ça.

C'est la même erreur que le 28 août, sous une autre forme : desserrer la
mesure au lieu de changer le problème.

### Le cash limite le NOMBRE de positions, jamais leur taille

Au comptant, on ne peut pas engager plus qu'on ne possède. Le nombre de
positions simultanées est donc borné par le cash, et c'est normal.

Ce qui n'est pas normal, c'est de **rétrécir chaque position** pour en
loger davantage. Le budget était pré-découpé en parts égales entre les
places libres : à 96 EUR avec six places, chacune recevait 14,40 EUR de
notionnel au lieu des 45 EUR que le risque demandait — soit **0,19 % de
risque par trade pour 0,60 % configurés**, et des tickets sous le minimum
de 5 EUR de la plateforme.

Or le rejeu qui a mesuré +0,352 R ne pose aucune contrainte de cash et ne
tient qu'une position à la fois : **il mesure des positions pleines**. Des
positions six fois plus petites ne sont pas la stratégie mesurée.

Chaque position est donc servie à la taille voulue par le risque, dans la
limite de ce qui reste. À 96 EUR cela donne **2 positions pleines** :

    position 1   45,00 EUR de notionnel   risque 0,58 EUR (0,60 %)
    position 2   41,40 EUR de notionnel   risque 0,53 EUR (0,55 %)
    position 3   refusée — budget épuisé

`tests/test_garde_fous.py::TestLevierMaitrise` verrouille la taille de la
première position ; c'est elle qui trahit un budget pré-découpé.

### Le partage suit les occasions RÉELLES (30 août, mesuré en réel)

Les deux décisions ci-dessus — « servir chaque position pleine » et
« partager le cash entre les places » — semblaient s'opposer. Elles ne
s'opposent que si l'on divise par les places **théoriques**.

Mesuré le 30 août : 97,37 € de capital, **70,82 € disponibles toute la
journée**. Le partage divisait par six places libres en pariant sur six
occasions ; il y en a eu **deux**. Quatre sixièmes du compte ont dormi,
et les deux positions prises ont porté 0,25 % de risque au lieu des
0,60 % configurés.

Le dimensionnement reçoit désormais `places_visees` — le nombre
d'occasions que le moteur a réellement sous la main :

    occasions      notionnel     risque
    6 (avant)        14,61 E     0,192 %
    3                29,21 E     0,384 %
    2                43,82 E     0,576 %   <- la journée du 30 août
    1                45,64 E     0,600 %

Quand six occasions existent, le partage est inchangé : six positions de
14,60 € risquent autant que deux de 43,80 €. Quand il n'y en a que deux,
le capital travaille au lieu d'attendre des places imaginaires.
`max_total_risk_pct` reste la borne dure au-dessus : diviser par moins ne
peut pas faire dépasser le risque total.

Ne pas remplacer ce mécanisme par un remplissage séquentiel « pour
investir plus » : quand les occasions sont nombreuses, il concentrerait
le compte sur les deux premières.

### Le levier : pourquoi il a été retiré

L'opérateur l'avait autorisé le 29 août, et il servait à occuper les places
que le budget de risque autorisait déjà. Le passage au comptant le rend
sans objet : sans compte de marge, il n'y a rien à emprunter, et une
configuration qui demanderait 3x ferait dimensionner des positions que
Bitvavo refuserait faute de liquidités.

Le raisonnement d'origine reste valable si la marge est un jour activée —
il est conservé ci-dessous — mais il ne s'applique plus au réglage actuel.

### Ce que le levier faisait, quand il était armé

L'opérateur a autorisé le levier le 29 août. La décision du 27 août
(« aucun levier ») est levée, mais son raisonnement reste vrai et
délimite l'usage.

**Ce que le levier ne fait pas.** Il ne corrige pas les frais. Il
multiplie la taille de la position ET les frais dans la même proportion :
le rapport frais/risque est **invariant au levier**. À 33 % du risque en
H1, c'est 33 % à 1x comme à 10x. Aucun levier ne rend le M5 viable — c'est
la même division qu'avant.

**Ce qu'il fait, et qui compte ici.** Le dimensionnement part du risque :
une position vaut `capital × 0,6 % / distance au stop`, soit ~23 EUR de
notionnel sur un compte de 70 EUR. Le budget de risque
(`max_total_risk_pct: 3.5`) en autorise 5 en parallèle. Mais 5 × 23 EUR
= 117 EUR, et le compte n'a que 70 EUR : **le cash bloquait à 2
positions**. Mesuré :

    1x   ->  2 positions   (le CASH bloque)
    2x   ->  5 positions   (le budget de RISQUE bloque)
    3x   ->  5 positions
    5x   ->  5 positions
    10x  ->  5 positions

Le levier sert donc à occuper les places que le budget de risque autorise
déjà. **Au-delà de 2x, il n'ouvre plus aucune position** — il n'ajoute que
du risque de liquidation. 3x est retenu comme marge pour les variations
de capital et de volatilité.

Le risque par trade, lui, **ne suit pas le levier** : c'est la confusion
qui coûte cher. Un levier de 3 n'autorise pas 3 × 0,6 %. Le
dimensionnement remonte du risque vers la taille, jamais l'inverse, et
`tests/test_garde_fous.py::TestLevierMaitrise` le vérifie.

Corollaire : sous levier, une série de pertes va plus vite. Les
coupe-circuits (perte journalière 4 %, drawdown 25 %, 4 pertes d'affilée)
ne sont plus du confort, et le stop temporel devient nécessaire — une
position à levier paie des intérêts d'emprunt tant qu'elle est ouverte.

### La vente à découvert

Bitvavo a ouvert la vente à découvert (BTC, ETH, XRP, SOL, ADA et une
dizaine d'autres, à partir de 10 EUR). Elle passe par un compte de marge —
c'est le seul chemin — d'où `engine.broker: "bitvavo_margin"`.

Ce que ça débloque : au comptant, une alerte de vente parfaitement valide
était jetée **avant même d'être évaluée** (`supports_short = False` retire
le sens VENTE du scan). Dans un marché qui baisse, le robot regardait
passer la moitié des occasions sans pouvoir rien en faire. C'est la
deuxième cause, après le cash, du « zéro trade » constaté le 29 août.

Le coût d'emprunt est de ~0,0274 % par jour. Sur un trade H1 tenu quelques
heures, c'est négligeable devant les 0,60 % de frais — mais il court tant
que la position est ouverte, ce qui est une raison de plus de garder le
stop temporel (`time_stop_minutes: 720`).

### Pourquoi le bloc `promotion` doit rester

C'est lui qui ramène AUTOMATIQUEMENT le robot au D1 quand la fenêtre sans
commission se ferme. Sans lui, plus rien ne le fait. Le commentaire de
`gold_bot/promotion.py` dit ce qui arrive alors, mot pour mot :
« viderait le compte en quelques jours, sans erreur ni alerte ».

### Pourquoi les filtres d'entrée restent serrés

Desserrés — spread à 0,6 ATR, volatilité minimale à 0,001 — ils ont produit
**72 trades à 2,8 % de réussite**, une espérance de **−0,406 R** et une
progression médiane de **0,25 R** là où l'objectif était à 2,20 R. Les
trades n'allaient nulle part : le robot entrait sur des cryptos immobiles
où le spread mangeait un tiers du risque.

La distinction qui compte : quand un trade monte à 1,20 R avant de
retomber, c'est la protection qui manque. Quand il ne dépasse jamais
0,25 R, **c'est l'entrée qui ne vaut rien** — et aucun réglage de stop n'y
changera quoi que ce soit.

Le 28 août, à 0,1, ce filtre écartait **94 % de l'univers** — trois fois
plus strict que le plafond de coût ne l'exige — et plus aucune crypto
n'atteignait les filtres suivants. Porté à 0,25, il reste sous le plafond
(13,9 % du risque contre 15 % permis) tout en laissant le contrôle de coût
exact, calculé sur le vrai spread au dimensionnement, faire son travail.

La borne n'est donc pas un chiffre choisi : c'est
`max_cost_ratio_pct/100 × atr_stop_mult`. Ces deux réglages doivent rester cohérents avec le plafond de coût : le
stop vaut `atr_stop_mult` ATR, soit 1 R, donc un spread de M ATR pèse
`M / atr_stop_mult` en R. `BotConfig.validate()` refuse désormais la
contradiction au démarrage, en donnant la valeur à corriger.

### Correction du 9 septembre : c'était vrai du FOREX, pas des actions

Tout ce qui suit reste exact **pour le forex**, et la conclusion s'est
propagée trop loin. Le minimum de 2 USD est celui du forex ; sur les
**actions US en tarif Tiered**, le minimum est de **0,35 USD par ordre**.

À 366 EUR de capital et 0,6 % de risque (2,20 EUR) :

    plan IBKR                      aller-retour   cout / risque
    Tiered, actions US                  0,64 E         29 %     <- passe
    Fixed, actions US                   1,84 E         84 %
    Tiered, ETF europeens               2,50 E        114 %
    Forex (l'analyse d'origine)         3,68 E        167 %

**Le Tiered actions US passe sous le plafond de 50 %.** IBKR n'est donc
pas disqualifié par les frais — la ligne « pas utilisable à ce capital »
ne vaut que pour le forex et les ETF européens.

Ce qui bloque vraiment est ailleurs : **IBKR Ireland exige 2 000 EUR sur
un compte de marge**, et le compte de marge est obligatoire pour vendre à
découvert. Sans marge, IBKR n'offre que de l'achat seul — donc rien de
plus que Bitvavo, sur un marché où **aucune mesure n'existe** (toutes les
données du dépôt sont crypto).

Ce que ça donnerait aux paliers supérieurs, Tiered actions US :

    capital    risque 0,6 %   cout / risque
     2 000 E        12,00 E        5 %      <- marge + ventes possibles
     3 000 E        18,00 E        4 %

Contre **~48 %** chez Bitvavo aujourd'hui. À 2 000 EUR, les frais sont
divisés par dix ET la vente à découvert s'ouvre — c'est la combinaison
qui donnait les meilleurs rejeux de la session.

**Demande de marge envoyée le 9 septembre 2026.** Elle ne débloque rien
tant que le compte n'atteint pas 2 000 EUR. Avant d'y transférer quoi que
ce soit : remesurer la stratégie sur des **données actions**, qui n'ont
jamais été téléchargées. Un Donchian 20 jours sur actions n'est pas le
même animal qu'en crypto — horaires, gaps d'ouverture, corrélations.

### IBKR n'est pas utilisable à ce capital, et ce n'est pas un bug

Vérifié le 29 août, tarif public IBKR : la commission forex vaut
**0,20 point de base, avec un minimum de 2 USD par ordre**. C'est un
montant **fixe** en dessous de 100 000 USD de notionnel — et c'est lui,
pas la taille de lot, qui ferme la porte.

Le compte IBKR porte **90 EUR** (distinct des 70 EUR de Bitvavo).

Le piège à éviter : croire que le levier résout le problème. Il ne le
résout pas, il le déplace. Le robot dimensionne par le risque, pas par le
levier disponible. Avec 90 EUR, l'aller-retour à 3,70 EUR pèse :

    risque 0,6 %  ->  0,54 EUR  ->  686 % du risque
    risque 1,0 %  ->  0,90 EUR  ->  412 %
    risque 1,5 %  ->  1,35 EUR  ->  274 %   (plafond dur du robot)

Même au risque maximal que `validate()` autorise, le filtre de coût
refusera chaque trade — et il aura raison.

    notionnel   risque    commission   coût/risque
      1 000 E    1,54 E      3,70 E        246 %
      5 000 E    7,70 E      3,70 E         53 %
     10 000 E   15,40 E      3,70 E         29 %
     25 000 E   38,50 E      3,70 E         15 %

Pour tenir sous les 35 % du plafond, il faut ~8 000 EUR de notionnel, soit
~12,40 EUR de risque par trade :

    à 0,6 % de risque par trade  ->  capital ~ 2 070 EUR
    à 1,0 % de risque par trade  ->  capital ~ 1 240 EUR
    à 1,5 % de risque par trade  ->  capital ~   830 EUR

**Plancher absolu ~830 EUR**, et seulement en risquant le maximum autorisé.
Confortable à partir de ~2 000 EUR. En dessous, IBKR n'est pas un mauvais
réglage : c'est une addition qui ne tombe pas juste.

En attendant, le compte **papier** d'IBKR (port 4002) coûte zéro et permet
de valider toute la chaîne — Gateway, code SMS, connexion API, contrats,
moteur — pour qu'elle soit prête le jour où le capital suit. C'est le seul
usage d'IBKR qui ait du sens aujourd'hui.

(Correction du 29 août : une première version disait que le lot minimum de
1 000 unités était inatteignable à 70 EUR. C'est faux — le levier forex
d'IBKR, jusqu'à 30:1 en Europe sur les majeures, le rend accessible. La
conclusion tient, mais la raison est la commission fixe, pas la taille.)

Le code IBKR reste en place et fonctionne (voir `verifier_ibkr.py`). Il
n'est simplement pas armé tant que le capital ne le justifie pas. Ne pas
le rebrancher « pour faire tourner les deux plateformes » : chaque ordre
coûterait plusieurs fois le risque qu'il prend.

### Les ordres limite : essayés, mesurés, ABANDONNÉS

C'était présenté ici comme « le chantier au meilleur rapport gain/risque
du dépôt ». **Le rejeu du 30 août dit le contraire**, et le raisonnement
qui le portait était faux.

L'idée : Bitvavo facture 0,25 % au preneur et 0,15 % au maker, donc une
entrée en limite « post-only » ferait tomber l'aller-retour de 0,60 % à
0,40 %. Implémenté puis mesuré, mêmes 8 cryptos, 4000 bougies, spread
doublé :

    ordres au marché   130 trades   60,0 %   +0,352 R   +48,31 EUR
    ordres limite      108 trades   57,4 %   +0,267 R   +30,63 EUR

Moins de frais, et pourtant **37 % de profit en moins**.

**Pourquoi — et c'est la leçon.** Sur les 22 trades non servis, 16 étaient
gagnants : **72,8 % de réussite contre 57,4 % pour ceux qui l'ont été.**
L'ordre non exécuté n'est pas un tirage au hasard. Quand le prix ne revient
pas toucher la limite, c'est parce que le mouvement était réel — donc on
rate exactement les trades qu'on voulait prendre. C'est de la sélection
adverse, et elle coûte plus cher que les frais qu'elle économise.

Le raisonnement d'origine ne comptait que les frais, en supposant les
exécutions acquises. Une économie de coût ne vaut rien si elle change
*lesquels* des trades on obtient.

Le code reste en place et testé (`BITVAVO_ENTREE_LIMITE`, désactivé par
défaut ; `comparer.py --entree-limite` pour remesurer). Il pourrait
redevenir favorable sur une unité plus lente, où le prix a le temps de
revenir. À ce jour, sur le M30 au comptant, il fait perdre.

### Pourquoi H4 avait été retenu le 28 août

Pendant deux jours, les réglages ont été essayés **en argent réel** : 72
trades, 2,8 % de réussite, espérance −0,406 R. Le 28 août au soir, le
moteur de rejeu a été mis à contribution — sept configurations, huit
cryptos, 2 000 bougies, **frais pleins et spread triplé** :

    H4  plafond 15 %    69 trades   53,6 %   +0,267 R   +16,89 EUR
    D1  plafond 15 %    88 trades   54,5 %   +0,230 R   +13,13 EUR
    M15 plafond 25 %    39 trades   56,4 %   +0,453 R   +17,57 EUR

H4 l'emporte : meilleur profit parmi les variantes qui respectent le
plafond de 15 %, sur un échantillon deux fois plus grand que le M15.

Le plafond à 15 % ne coûte que **6 trades et 0,71 EUR** sur 75 par
rapport à 25 %, et donne une **meilleure** réussite. La décision de
l'opérateur tient donc sans qu'on ait rien à sacrifier.

### Une correction d'arithmétique

Le premier calcul annonçait « M15 = 78 % du risque en frais », tiré d'un
tableau de stops types qui ne correspondait pas à la crypto. Avec les ATR
**réellement mesurés** dans les journaux du 28 août :

    M15   ATR 0,56 %   stop 1,01 %   ->  frais = 60 % du risque
    H4    ATR 2,24 %   stop 4,03 %   ->  frais = 15 %
    D1    ATR 5,46 %   stop 9,83 %   ->  frais =  6 %

La conclusion tenait pour le M15 — il reste hors de portée du plafond —
mais elle écartait le **H4 à tort**, en le calculant à 19 % au lieu de 15.
C'est cette erreur qui a fait perdre une journée sur le D1.

### Ne jamais changer l'unité sans repasser par le rejeu

`comparer.py` mesure une configuration sur l'historique en quelques
minutes, sans engager un centime. Deux jours d'essais en argent réel
n'avaient produit qu'un seul échantillon, faux de surcroît — le stop ne
suivait pas encore. Un changement d'unité de temps, de plafond de coût ou
de filtre passe par là **avant** d'atteindre le compte.

### Pourquoi la confirmation par les bougies est facultative

Passée à `false` le 28 août, après être devenue le seul motif de rejet :
cinq cryptos sur cinq écartées sur « aucun motif », alors qu'elles avaient
6 ou 7 confirmations sur 11 quand le quorum n'en demande que 5.

Deux raisons, et la seconde est propre au D1 :

- **C'est un doublon.** Les bougies comptent déjà comme une confirmation
  parmi les onze. Les rendre obligatoires en plus, c'est exiger cette
  lecture-là deux fois.
- **La bougie du jour n'est pas finie.** Le détecteur lit les trois
  dernières bougies, celle en cours comprise. En D1 elle se déforme toute
  la journée : un marteau à midi n'en est plus un le soir.

Ce retrait ne vaut que tant que les autres barrières tiennent — quorum,
score, ratio R/R, volatilité minimale, plafond de coût. Un test les vérifie
ensemble.

### Pourquoi le score doit rester une barrière

Le 28 août, un achat XRP **réel** s'est ouvert sur un score de **0,24**
— tendance +0,01, momentum +0,18, bougies +0,14 — alors que la
configuration portait `min_score` à 0,55. Le seuil était forcé à zéro dans
`_finish_quorum` : le réglage existait, s'affichait dans le journal, et ne
servait à rien.

Un compte de confirmations ne dit pas la même chose qu'une force de
signal : **cinq confirmations faibles restent cinq confirmations.** Le
score est donc redevenu une porte en mode quorum, à 0,35.

Le bonus d'objectif n'est pas ajouté à ce seuil : en quorum il relève déjà
le nombre de confirmations exigées, et le compter deux fois punirait deux
fois la même situation — le robot cesserait d'entrer exactement quand il
doit se refaire.

### Le seuil est passé de 0,35 à 0,45 le 31 août

Le 31 août, le marché crypto a décroché dans la nuit. Le robot, achat
seul, a enchaîné six stops pleins (ALGO, CRO, PENDLE, CAKE, STRK, EGLD).
Les trois pertes les plus nettes — PENDLE, STRK, EGLD — étaient entrées
sur les signaux les plus faibles qui passaient encore la porte :
**score 0,39, 0,36 et 0,36** pour un seuil à 0,35. Sur quatorze entrées
M30, sept étaient sous 0,45.

Quatre rejeux successifs — 2500, 4000 et 8000 bougies, huit cryptos,
spread doublé, frais pleins — désignent **score 0,45 comme la meilleure
variante**, à chaque fois :

    variante                  trades   réussite   espérance nette
    score 0,45                    65     67,7 %       +0,396 R
    config en service (témoin)   103     57,3 %       +0,245 R

C'est le seul changement où le rejeu et le réel pointent le même doigt :
le robot entrait sur ses signaux les plus médiocres, et ce sont eux qui
saignaient. La règle des 40 trades sert à ne pas courir après du bruit ;
ici la preuve est convergente, pas du bruit.

Le prix : 65 trades contre 103, soit un échantillon réel plus lent à
construire. `tests/test_garde_fous.py` verrouille le plancher à 0,45.

Ce que ce changement ne règle **pas** : le robot achat seul dans un
krach corrélé. Aucun réglage de score n'y protège — seuls les
coupe-circuits le font. La vente à découvert n'aide pas non plus (mesurée
trois fois, jamais favorable : le M30 ne produit quasiment aucune entrée
VENTE qui passe ses filtres).

## Le plan de croissance : 186 EUR -> 3 000 EUR

Décidé le 29 août. Les 90 EUR d'IBKR rejoignent Bitvavo (186 EUR au
total) ; IBKR n'est plus touché jusqu'à 3 000 EUR, où 1 500 EUR y seront
reversés — au-dessus du seuil de ~830 EUR calculé plus haut.

### Ce que « vite » veut dire, arithmétiquement

Un compte grandit par `risque × espérance`, composé à chaque trade :

    jours = ln(cible / capital) / (trades_par_jour × ln(1 + risque × espérance))

186 → 3 000, c'est **×16**. À 6 trades par jour :

    espérance      0,6 %       1,0 %       1,5 %   <- risque par trade
      −0,10 R     jamais      jamais      jamais
      +0,00 R     jamais      jamais      jamais
      +0,05 R      1545 j       927 j       618 j
      +0,10 R       773 j       464 j       309 j
      +0,20 R       386 j       232 j       155 j
      +0,30 R       258 j       155 j       103 j

Le rejeu H4 du 28 août donnait +0,267 R. En prenant ce chiffre pour
argent comptant — ce qu'il ne faut pas faire, il vient d'un rejeu et non
du réel — la cible demande **entre 4 et 8 mois**. Il n'y a pas de réglage
qui raccourcisse cela : seule l'espérance le peut, et elle ne se décide
pas.

### La ligne à ne jamais franchir

**Une espérance négative ne se rattrape pas en montant le risque.** Le
risque, la cadence et le levier amplifient le *signe* de l'espérance ; ils
ne le changent pas. Le 28 août, 72 trades à −0,406 R : doubler le risque
aurait divisé le temps de survie par deux, pas rapproché la cible.

C'est pourquoi le risque est désormais **verrouillé sur la preuve**, dans
`gold_bot/croissance.py`, et appliqué à chaque cycle par
`TradingEngine._appliquer_palier_de_croissance` :

| palier | risque | conditions d'entrée |
|---|---|---|
| `preuve` | 0,60 % | aucune — c'est lui qui produit l'échantillon |
| `croissance` | 1,00 % | ≥ 40 trades **et** espérance ≥ +0,05 R |
| `acceleration` | 1,50 % | ≥ 150 trades **et** espérance ≥ +0,15 R |

L'espérance lue ici est **nette de frais** (`esperance_R_nette`). Le
`r_multiple` du journal se calcule sur les prix seuls : au M30 les frais
valent 47 % du risque, et promouvoir sur le brut ferait monter la mise
sur un avantage inexistant. Mesuré le 30 août : +0,446 R bruts pour
+0,186 R nets sur les mêmes sept trades.

`risk.max_risk_pct` valait **1,00 %** jusqu'au 30 août, ce qui rendait le
palier `acceleration` inatteignable — annoncé dans le journal, rabaissé
en silence au dimensionnement, donc une projection de croissance fausse
de 50 %. Porté à **1,50 %** sur décision de l'opérateur. Le plafond dur
**borne**, il n'autorise pas : c'est le palier qui décide, et il exige
150 trades. `tests/test_audit_coherence.py::TestLePlafondDurNeContourneRienDuTout`
vérifie qu'à 7 trades le risque reste à 0,60 %.

Le palier **plafonne** le risque : une configuration qui demande 1,5 %
n'obtient 1,5 % qu'une fois l'avantage établi. Il ne descend jamais sous
le plancher imposé par le ticket minimum de la plateforme — sinon le robot
se figerait en croyant se protéger.

Une espérance flatteuse sur 10 trades ne débloque rien : à 40 trades
l'incertitude vaut encore ±0,32 R. `Diagnostic.esperance_fiable()` exige
que l'espérance dépasse deux fois cette incertitude avant qu'on puisse
parler d'avantage.

### Le premier objectif n'est pas 3 000 EUR

C'est **40 trades avec une espérance positive**. Tant que ce n'est pas
acquis, la vitesse ne veut rien dire : composer une espérance négative
n'amène pas à 3 000, ça amène à zéro — simplement plus vite si on
accélère.

    python3 plan_croissance.py --capital 186 --cible 3000

répond avec le journal réel, dit à quel palier le robot se trouve, ce
qu'il manque pour monter d'un cran, et ce que coûte la série noire à
chaque niveau de risque.

## Trois défauts trouvés en préparant le rejeu (29 août)

Ils ne venaient pas de la stratégie. Ils la rendaient invisible.

**1. BTCUSD était rejeté à chaque évaluation.** L'instrument portait un
plafond de spread ABSOLU, `max_spread = 30`, hérité d'une autre échelle de
prix. Le spread modélisé vaut 5 points de base, soit 34 à 68 000 : la
crypto la plus liquide de l'univers était écartée sur le filtre « spread »,
450 fois sur 450 au rejeu — et de la même façon en argent réel. Les 81
paires générées utilisaient déjà `inf` pour cette raison exacte, documentée
dans `instrument_crypto`. Les quatre réglées à la main ne l'avaient jamais
été. Corrigé : `max_spread = inf` partout, le contrôle qui vaut est le
rapport spread/ATR.

**2. Deux modèles de coût dans le même rejeu.** Le filtre de la stratégie
utilisait `spread_estime()` — relatif — pendant que le dimensionnement,
faute de recevoir le paramètre, retombait sur `typical_spread`, absolu.
Les quatre paires réglées à la main étaient donc pénalisées (8,0 de spread
sur BTCUSD) et les 81 générées flattées (spread nul). Le moteur réel, lui,
passe `spread=ev.spread`. Le rejeu ne mesurait pas la stratégie qui tourne.

**3. Les tailles de lot écrites en dur rendaient BTCUSD indimensionnable.**
`min_lot = 0,001` vaut 68 EUR de notionnel à 68 000 — plus du tiers d'un
compte de 186 EUR — quand Bitvavo n'impose qu'un ticket de 5 EUR. En réel
`apply_market_rules` remplace ces valeurs au démarrage ; en rejeu, jamais.

La leçon commune : **une constante absolue sur un catalogue qui va du BTC
à 68 000 au PEPE à 0,00001 est fausse quelque part, toujours.** Trois tests
la verrouillent désormais (`tests/test_backtest_pipeline.py`), dont un qui
vérifie que la chaîne évaluation → dimensionnement → ouverture produit
réellement des trades sur une tendance franche. Un rejeu qui rend zéro
trade partout ressemble à une stratégie sans avantage ; c'était un filtre
qui refusait tout en silence.

## Deux règles de méthode

**Ne jamais supprimer un test pour faire passer la suite.** Si un test
échoue sur du code correct, c'est l'assertion qu'il faut corriger — et le
dire. Deux tests Pionex exigeaient l'inverse de ce que leur nom annonçait.

**Le simulateur (`paper`) doit rester constructible.** Il a été retiré des
brokers valides : plus de dry-run, plus de rejeu historique, et aucun
moteur constructible en test. Un lieu d'exécution qui n'engage rien doit
toujours être disponible.

## Claude Code sur le VPS

Installé le 30 août pour piloter le robot sans copier-coller.

    curl -fsSL https://claude.ai/install.sh | bash
    cd ~/Eve-AI-Influencer && claude

`.claude/settings.json` — versionné, donc il suit le dépôt — pré-autorise
la **lecture et le diagnostic** : `journalctl`, `systemctl status`,
`git status/log/diff/pull`, les tests, et les outils du dépôt
(`bilan_journee.py`, `etat.py`, `pourquoi_pas_de_trade.py`,
`plan_croissance.py`, `comparer.py`, `verifier_*.py`). Rien de tout cela
n'engage un centime.

Restent en **demande explicite**, parce qu'elles touchent au robot armé
ou sortent du VPS : `systemctl restart/start/stop`, `git push`,
`git reset`, `git checkout`, les lanceurs `run_*.py`, et
`reinitialiser_arret.py`.

Sont **refusées** : la lecture de `.env` (il porte les clés Bitvavo, et
ce qui est lu part dans la conversation), `rm -rf`, et `git push --force`.

Cette barrière ne remplace pas la seule qui compte vraiment : **le retrait
doit être désactivé sur la clé API Bitvavo**. Avec « trade » et « view »
seuls, le pire cas est un compte mal tradé, pas un compte vidé — et ça ne
dépend d'aucun code de ce dépôt.

Pour que la session survive à une déconnexion SSH : **`./claude_persistant.sh`**,
qui crée ou reprend la session tmux `bot`. Voir la section suivante — ce n'est
pas du confort, c'est ce qui empêche la conversation d'être archivée.

---

## Les conversations archivées : la cause, et le seul remède — 13 septembre

L'opérateur est parti une heure ; à son retour la conversation « bot bitvavo
v2 » était **archivée**, le fil de travail coupé. Ce n'est pas la première fois.

### Ce qui s'est réellement passé

La session lancée sur le VPS n'est **pas hébergée chez Anthropic**. C'est un
`claude` qui tourne sur le VPS, dont l'application n'affiche qu'un **miroir**
(le pont « remote control », `environment_kind: bridge`). Le miroir n'a pas de
vie propre : il suit le processus.

Or ce processus est un simple enfant du shell SSH. SSH qui tombe — réseau,
téléphone en veille, terminal fermé, application changée — et le processus est
tué avec lui. Le pont passe en `disconnected`, puis la conversation est
archivée côté application.

**L'archivage est la conséquence, pas la cause.** Personne n'a archivé la
conversation : le lien s'est rompu, et l'application a rangé ce qui ne
répondait plus. Le journal de la session confirme d'ailleurs qu'elle
n'« était pas en plein travail » : elle attendait un jeton Expo depuis un
moment. Une session qui attend et dont le lien tombe est exactement le cas
que la mise en archive vise.

### Ce que l'archivage ne fait PAS

**Il ne supprime rien.** Trois choses distinctes, et aucune n'a été perdue :

| ce qui existe | où c'est stocké | survit à l'archivage ? |
|---|---|---|
| le code | git, sur le VPS et sur GitHub | oui — les 12 commits étaient poussés |
| le fil de conversation | `~/.claude/projects/` sur le VPS | oui — `claude --resume` le retrouve |
| le miroir dans l'application | serveurs Anthropic | il passe en lecture seule, on le désarchive |

La panique porte donc sur la seule des trois qui se répare en une commande.

### Le remède

`./claude_persistant.sh`. tmux détache le processus du SSH : la session
continue de tourner sur le VPS, téléphone éteint, et on s'y rebranche.

    ./claude_persistant.sh            # crée la session, ou s'y rebranche
    ./claude_persistant.sh --statut   # dit si elle tourne, sans y entrer

**Se détacher avec `Ctrl+b` puis `d`.** Jamais `/exit` ni `Ctrl+d` : ceux-là
terminent vraiment la session, et là l'archivage est légitime.

Ajouter aussi, dans `~/.ssh/config` du poste client, de quoi que le lien ne
lâche pas au premier silence :

    Host mon-vps
        ServerAliveInterval 30
        ServerAliveCountMax 10

### Ce qu'il ne faut pas chercher

Il n'existe **aucun réglage « ne jamais archiver »** dans ce dépôt, ni dans
`.claude/settings.json` : l'archivage est décidé côté application, à partir de
l'état du pont. Le seul levier qui existe est de ne pas laisser le pont tomber.
Chercher une option à cocher est une perte de temps ; lancer tmux prend trois
secondes.

### Ne plus jamais ré-expliquer : REPRISE.md

Garder un fil de conversation ouvert n'est **pas** la bonne façon de conserver
le contexte — il finira toujours par tomber. Le contexte durable vit dans le
dépôt, pas dans une conversation.

Deux fichiers, deux rôles, et il ne faut pas les mélanger :

| fichier | contient | change |
|---|---|---|
| `CLAUDE.md` | les **décisions** : pourquoi le D1, pourquoi 3 étages, pourquoi pas IBKR | rarement, sur mesure |
| `REPRISE.md` | l'**état courant** : ce qui est en cours, ce qui attend une réponse | à chaque session |

`.claude/reprise.py`, branché sur le hook `SessionStart`, injecte REPRISE.md
**plus l'état git réel** (branche, dernier commit, fichiers non commités,
commits non poussés) au démarrage de chaque session. Toute session qui laisse
un travail en suspens réécrit REPRISE.md avant de s'arrêter.

Le hook échoue en silence si quoi que ce soit cloche : un hook qui plante ne
doit jamais empêcher une session de démarrer.

### La leçon

C'est la même que partout ailleurs dans ce fichier : **une protection qui n'est
pas exécutée ne protège pas.** La ligne « pour que la session survive, `tmux
new -s bot` » était écrite ici depuis le 30 août. Elle était *lue* et jamais
*exécutée*. Elle est donc devenue un script qu'on lance, pas une phrase qu'on
espère avoir retenue.

## Où se trouve la vérité

- Audit chiffré : https://claude.ai/code/artifact/182489e5-d5db-4b0d-bdb9-b9cc44e68b0b
- Arithmétique des frais : `gold_bot/calibrage.py`
- Expiration de la fenêtre : `gold_bot/promotion.py`
- La configuration en service est `robot.bitvavo.json`, armée en réel
  (clé `_arme_en_reel`).
