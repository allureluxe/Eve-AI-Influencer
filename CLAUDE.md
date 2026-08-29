# Décisions de l'opérateur — à lire avant de toucher aux réglages

Ce dépôt pilote un robot qui engage de l'argent réel sur un compte Bitvavo
d'environ 51 EUR. Plusieurs sessions travaillent sur la même branche. Les
décisions ci-dessous ont été prises par l'opérateur ; elles ne sont pas des
valeurs par défaut à optimiser.

## H1, sans levier, achat ET vente

Décision révisée le **29 août**. Elle remplace le « D1 puis H4 » du 27-28
août, dont le raisonnement reste valable et se trouve plus bas.

| réglage | valeur | ne pas |
|---|---|---|
| `risk.max_cost_ratio_pct` | **35.0** | remonter pour « débloquer » une unité plus rapide |
| `strategy.max_cost_ratio_pct` | **35.0** | idem |
| `trade.max_cost_ratio_pct` | **35.0** | idem |
| `risk.max_leverage` | **3.0** | monter à 10x « pour trader plus » : ça n'ouvre aucune position de plus |
| `engine.broker` | **bitvavo_margin** | confondre « vendre » et « lever » |
| bloc `promotion` | **présent** | retirer |
| `strategy.max_spread_atr_ratio` | **0.30** | dépasser `max_cost_ratio_pct/100 × atr_stop_mult` |
| `strategy.min_score` | **0.35** | remettre à zéro « parce que le quorum suffit » |
| `strategy.entry_tf` | **H1** | descendre sous H1 sans baisser les frais |
| `trade.atr_stop_mult` | **1.60** | resserrer sans recalculer le coût |
| `trade.tp_r_multiple` | **2.00** | baisser sans recalculer la réussite nécessaire |
| `trade.time_stop_minutes` | **720** | garder une valeur pensée pour une autre unité |

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

### Le levier : à quoi il sert vraiment, et pourquoi 3x et pas 10x

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
**0,20 point de base, avec un minimum de 2 USD par ordre**. Ce minimum
change tout pour un petit compte :

- lot minimum sur IDEALPRO : 25 000 USD ; en dessous, l'ordre part en
  « odd lot », taille minimale 1 000 unités, avec un spread élargi ;
- un aller-retour de 1 000 EUR coûte 2 USD + 2 USD, soit **0,40 % du
  notionnel** — plus cher que Bitvavo ;
- avec 70 EUR de capital, même à 10x, le notionnel plafonne à 700 EUR :
  **le lot minimum n'est pas atteignable du tout.**

IBKR redevient intéressant à partir du mini-lot (10 000 USD), où les 2 USD
retombent à 0,02 % — donc à partir de quelques milliers d'euros de capital,
ou avec un levier que l'opérateur a exclu.

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
