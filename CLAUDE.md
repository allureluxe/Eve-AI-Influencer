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
| `strategy.max_spread_atr_ratio` | **0.1** | desserrer pour « prendre plus de trades » |
| `strategy.min_atr_price_ratio` | **0.0035** | idem |

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

Ces deux réglages doivent rester cohérents avec le plafond de coût : le
stop vaut `atr_stop_mult` ATR, soit 1 R, donc un spread de M ATR pèse
`M / atr_stop_mult` en R. `BotConfig.validate()` refuse désormais la
contradiction au démarrage, en donnant la valeur à corriger.

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
