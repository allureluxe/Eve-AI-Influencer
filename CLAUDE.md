# Décisions de l'opérateur — à lire avant de toucher aux réglages

Ce dépôt pilote un robot qui engage de l'argent réel sur un compte Bitvavo
d'environ 51 EUR. Plusieurs sessions travaillent sur la même branche. Les
décisions ci-dessous ont été prises par l'opérateur ; elles ne sont pas des
valeurs par défaut à optimiser.

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
| `strategy.min_score` | **0.35** | remettre à zéro « parce que le quorum suffit » |
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

### Le levier suivant, non encore tiré : les ordres limite

Le robot entre et sort **au marché**, donc en *taker* : 0,25 % par côté.
Bitvavo facture 0,15 % en *maker* — un ordre limite qui ne s'exécute pas
immédiatement. Passer les entrées en limite « post-only » ferait tomber le
coût de 0,60 % à 0,40 %, soit un tiers de moins :

    H1, ordres au marché  ->  33 % du risque  ->  réussite 44,5 %
    H1, ordres limite     ->  22 % du risque  ->  réussite 40,8 %

Ce n'est pas fait : un ordre limite peut ne pas être servi, et il faut donc
une logique de repli et d'expiration que le broker n'a pas encore. C'est
le chantier au meilleur rapport gain/risque du dépôt.

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

## Où se trouve la vérité

- Audit chiffré : https://claude.ai/code/artifact/182489e5-d5db-4b0d-bdb9-b9cc44e68b0b
- Arithmétique des frais : `gold_bot/calibrage.py`
- Expiration de la fenêtre : `gold_bot/promotion.py`
- La configuration en service est `robot.bitvavo.json`, armée en réel
  (clé `_arme_en_reel`).
