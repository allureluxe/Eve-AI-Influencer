# Décisions de l'opérateur — à lire avant de toucher aux réglages

Ce dépôt pilote un robot qui engage de l'argent réel sur un compte Bitvavo
d'environ 51 EUR. Plusieurs sessions travaillent sur la même branche. Les
décisions ci-dessous ont été prises par l'opérateur ; elles ne sont pas des
valeurs par défaut à optimiser.

## D1, sans levier

Le 27 août, après audit chiffré, l'opérateur a tranché :

| réglage | valeur | ne pas |
|---|---|---|
| `risk.max_cost_ratio_pct` | **15.0** | remonter pour « débloquer » une unité de temps plus rapide |
| `strategy.max_cost_ratio_pct` | **15.0** | idem |
| `trade.max_cost_ratio_pct` | **15.0** | idem |
| `risk.max_leverage` | **1.0** | passer en marge |
| bloc `promotion` | **présent** | retirer |
| `strategy.max_spread_atr_ratio` | **0.25** | dépasser `max_cost_ratio_pct/100 × atr_stop_mult` |
| `strategy.min_atr_price_ratio` | **0.0035** | idem |
| `strategy.min_score` | **0.35** | remettre a zéro « parce que le quorum suffit » |
| `strategy.entry_tf` | **H4** | changer sans repasser par `comparer.py` |
| `trade.time_stop_minutes` | **2880** | garder une valeur pensée pour une autre unité |

`tests/test_garde_fous.py` verrouille ces valeurs. Si un test y échoue, ce
n'est pas le test qu'il faut changer.

### Pourquoi le plafond de coût reste à 15 %

Bitvavo prélève 0,25 % par côté. Le robot entre et sort au marché, donc
0,50 % l'aller-retour, plus 0,10 % de spread et de glissement qu'aucune
promotion n'annule : **0,60 % à absorber par trade**.

Rapporté à la distance du stop :

    M15   stop 0,77 %  ->  frais = 78 % du risque
    H1    stop 1,54 %  ->  frais = 39 %
    H4    stop 3,08 %  ->  frais = 19 %
    D1    stop 6,00 %  ->  frais =  8 %

Avec un objectif à 2,2R, cela donne le taux de réussite nécessaire pour
seulement rentrer dans ses frais :

    M15  ->  55,6 %      D1  ->  34,4 %

Remonter le plafond à 80 % « garde le M15 viable » en retirant la mesure,
pas en changeant le problème. Vérifié : à 0,25 % par côté, **aucun capital
entre 51 EUR et 20 000 EUR ne rend une unité plus rapide que D1 tenable.**
Ce n'est pas un problème d'argent, c'est une division.

### Pourquoi pas de levier

Un levier multiplie les gains ET les pertes. Sur un système dont
l'espérance n'est pas encore établie — 5 trades réels, 0 gagnant — il ne
rend rien gagnant : il fait perdre plus vite. Le compte est au comptant.

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

### Pourquoi H4, et comment on l'a su

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
