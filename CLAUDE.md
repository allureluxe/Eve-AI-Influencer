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

### La correction était dans ce fichier, pas dans le code

Le 29 août : le raisonnement ci-dessus avait bien été corrigé **ici**,
mais `calibrage.py` portait toujours le tableau de stops du **forex** —
H4 à 3,08 % au lieu des 4,03 % mesurés. Le texte disait une chose, le
code en calculait une autre.

Conséquence concrète, et elle tombait ce jour-là : à la fermeture de la
fenêtre sans commission, le calibrage déclarait encore le **M15
« tenable »**. Or en crypto le M15 coûte **59 % du risque** en frais. Le
robot serait passé sur l'unité que ce fichier interdit, tout seul, sans
erreur ni alerte — le scénario exact que `promotion.py` est censé
empêcher.

`STOP_TYPIQUE_CRYPTO` contient désormais les ATR **réellement mesurés**
(× `atr_stop_mult` = 1,8), et `Universe.classe_dominante()` choisit le bon
tableau. Le tableau du forex reste intact pour le forex.

Vérifié par `tests/test_stops_crypto.py` : hors promotion, le M15 sort des
unités tenables et le H4 y entre.

`etat.py` recopiait ce même tableau en dur. C'est cette copie qui avait
gardé les anciennes valeurs. Elle est supprimée : il n'y a plus qu'une
source.

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

## D2, six positions au lieu de trois

Le 29 août, l'opérateur : « il prend peu de positions à mon goût, sur une
journée il y a énormément d'opportunités avec 70 instruments, donc il y a
un truc qui va pas ». L'observation était juste.

Quatre plafonds limitent le nombre de positions simultanées, et c'est le
plus petit qui décide :

| plafond | avant | après |
|---|---|---|
| `risk.max_positions` | 3 | **6** |
| `risk.max_total_risk_pct` | 1,8 | **3,0** |
| groupes corrélés (14 groupes × 1) | 14 | 14 |
| capital (186 €, ticket 5 €) | 29 | 29 |

**Deux verrous étaient à la même hauteur** : `max_positions` à 3, et le
budget de risque à 1,8 / 0,5 = 3 lui aussi. Remonter le premier seul
n'aurait rien changé — le second aurait repris le relais exactement au
même endroit, et le réglage serait passé pour cassé alors qu'il était
seulement masqué. Les deux ont donc été desserrés ensemble.

Ni les groupes corrélés ni le capital ne bridaient : il reste 14 groupes
disponibles, et de quoi tenir 29 tickets.

`etat.py` affiche ces quatre chiffres et nomme celui qui bride, pour que
la prochaine fois la question se règle en une commande.

### Pourquoi 3,0 % et pas plus

Six positions à 0,5 % engagent 3,0 % du capital en même temps — soit
5,58 € sur 186 €. La limite de perte journalière vaut 3,0 % elle aussi.

Ce n'est pas une coïncidence, c'est la contrainte : **si les six tombent
le même jour, la perte atteint exactement la limite journalière et le
robot s'arrête de lui-même.** Au-delà de 3,0 %, il pourrait perdre en une
journée plus que la limite n'autorise, et la limite ne servirait plus à
rien. Un test le vérifie.

Et en crypto, « les six tombent le même jour » n'est pas improbable :
dans une baisse générale les positions ne sont pas indépendantes. Six
positions corrélées se comportent alors comme une seule position de
3 %. La diversification par groupe réduit ce risque, elle ne l'annule
pas.

### Ce que le rejeu ne peut pas trancher

`comparer.py` rejoue **un instrument à la fois et n'en tient qu'une
position à la fois**. `max_positions` et `max_per_correlation_group`
n'ont donc aucun effet sur ses chiffres. Ce réglage-là se raisonne, il ne
se mesure pas — contrairement à l'unité de temps et au plafond de coût,
qui eux doivent passer par le rejeu. Le rapport le dit lui-même en bas de
page, pour qu'on ne lise pas ses chiffres comme ceux d'un portefeuille.

## D3, le robot ne pouvait pas prendre ses bénéfices

Le 29 août, l'opérateur : « les bénéfices que tu vois, c'est **moi** qui
ai fermé une position, pas le bot ». C'était littéralement vrai, et voici
pourquoi.

Bitvavo n'a pas d'ordre lié « l'un annule l'autre ». Poser à la fois un
stop et un objectif laisserait le second vivant après que le premier a
vendu, et il revendrait plus tard des actifs qui ne sont plus là. Le robot
ne pose donc **que le stop** sur la plateforme et garde l'objectif pour
lui — décision correcte.

Mais **personne ne comparait le prix à cet objectif.** Le simulateur le
fait dans `check_tick` ; or `engine.py` n'appelle `check_tick` que :

```python
if isinstance(self.broker, PaperBroker):
```

En réel, `position.take_profit` n'était donc qu'un nombre en mémoire que
rien ne lisait. Les seules sorties possibles étaient le stop de la
plateforme, le stop temporel, le retournement et le filet de perte
anormale.

**Une position réelle ne pouvait pas se fermer en bénéfice sur son
objectif.** Elle montait vers la cible, ne se fermait pas, redescendait,
et sortait sur le stop.

### Pourquoi aucun test ne l'avait vu

Ils passaient **tous** par le simulateur — le seul endroit où la
vérification existait. C'est aussi ce qui explique l'écart resté
inexpliqué entre le rejeu (+0,267 R) et le réel (−0,406 R) : au rejeu, le
simulateur encaissait les objectifs que le robot réel n'encaissait jamais.

La vérification vit désormais dans `TradeManager._safety_exits`, commun à
**tous** les lieux d'exécution. Elle se juge au prix de sortie réel — le
bid pour un achat — et non au milieu de la fourchette, sinon chaque trade
encaisserait une demi-fourchette de moins que son objectif annoncé.

`tests/test_objectif_en_reel.py` verrouille les deux points.

### Les libellés du broker réel ne sont pas ceux du simulateur

Corollaire découvert en même temps : `gold_bot/sorties.py` classait les
fermetures sur « stop-loss touché », le libellé du **simulateur**. En réel
Bitvavo écrit « stop déclenché sur la plateforme » — et **75 % des trades
réels tombaient dans « motif non reconnu »**.

Deux catégories manquaient aussi, et elles ne disent pas du tout la même
chose qu'une perte :

- **abandon technique** — « stop impossible à poser », « stop sous le
  minimum » : le robot n'a pas pu protéger la position et l'a fermée. Ce
  n'est pas un résultat de marché, c'est un incident d'exécution. Les
  confondre ferait chercher un défaut de stratégie là où il y a un défaut
  de plomberie.
- **sécurité** — « perte anormale » : le filet contre un gap.

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
