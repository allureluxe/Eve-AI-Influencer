# Turtle : le baseline contre 4 variantes

**Rejeu du 6 septembre 2026** — 70 paires EUR Bitvavo, 127 189 bougies
journalières, **8 mars 2019 → 6 septembre 2026 (7,5 ans)**.
Coupe walk-forward au **7 juin 2024** : 5,3 ans d'apprentissage,
2,2 ans jamais regardés avant le verdict.

Branche `test/turtle-variants`, arbre de travail séparé.
**Aucun fichier de production n'a été touché, aucun merge, aucun déploiement.**

---

## 1. Le verdict d'abord

| variante | verdict | pourquoi |
|---|---|---|
| **B_REGIME** | ❌ **non retenue** | Sharpe −0,21 contre −0,17 : moins bon |
| **C_UNIVERS** | ⚠️ **retenue au sens strict du critère** | Sharpe −0,12 > −0,17 **et** DD 21,9 % < 26,9 % |
| **D_SIGNAL** | ❌ **non retenue** | Sharpe −0,34 contre −0,17 : nettement moins bon |
| **E_COMBO** | ❌ **non retenue** | Sharpe −0,47 contre −0,17 : le pire du lot |

**Le critère est appliqué à la lettre : une seule variante le passe.**

Mais il faut lire la suite avant d'en faire quoi que ce soit — **C_UNIVERS
« gagne » avec un Sharpe de −0,12**. Elle bat le baseline uniquement en
perdant moins que lui. Le critère tel qu'il est écrit ne contient aucune
condition « bat zéro », et aucune des cinq configurations n'est rentable
hors échantillon.

---

## 2. Le résultat qui domine tous les autres

| | rendement | CAGR | Sharpe | max DD |
|---|---|---|---|---|
| **A_BASELINE** (le bot actuel) | **+70,6 %** | 7,4 % | 0,48 | 36,4 % |
| **Acheter du BTC et attendre** | **+1 910,6 %** | **49,2 %** | **0,97** | 73,6 % |

Sur 7,5 ans, aux **frais réels**, la stratégie fait **+70 %** là où garder
du bitcoin sans rien faire fait **+1 910 %**. Vingt-sept fois moins, avec
un Sharpe deux fois plus faible.

Le seul avantage du Turtle est le drawdown : 36 % contre 74 %. Il protège
mieux à la baisse — mais il paie cette protection en renonçant à
l'essentiel de la hausse.

---

## 3. Tableau complet — frais réels, période entière

| variante | rend. % | CAGR % | Sharpe | maxDD % | trades | réussite % | PnL moy € | exposé % | frais € |
|---|---|---|---|---|---|---|---|---|---|
| A_BASELINE | +70,6 | 7,4 | 0,48 | 36,4 | 1040 | 32,7 | +0,67 | 66,2 | 605 |
| B_REGIME | +2,6 | 0,3 | 0,10 | 39,2 | 690 | 31,3 | +0,03 | 39,4 | 256 |
| C_UNIVERS | +1,7 | 0,2 | 0,07 | 26,7 | 443 | 32,7 | +0,04 | 43,1 | 157 |
| D_SIGNAL | +44,7 | 5,0 | 0,42 | 29,8 | 648 | 33,8 | +0,68 | 45,7 | 322 |
| E_COMBO | +0,1 | 0,0 | 0,04 | 24,2 | 233 | 31,3 | −0,00 | 21,9 | 79 |
| **BENCHMARK BTC** | **+1910,6** | **49,2** | **0,97** | 73,6 | — | — | — | 100,0 | 0 |

## 4. Frais et glissement **doublés** — période entière

| variante | rend. % | CAGR % | Sharpe | maxDD % | trades | frais € |
|---|---|---|---|---|---|---|
| A_BASELINE | +5,3 | 0,7 | 0,13 | 49,0 | 1046 | 961 |
| B_REGIME | −21,8 | −3,2 | −0,15 | 47,5 | 692 | 446 |
| C_UNIVERS | −17,1 | −2,5 | −0,19 | 38,5 | 443 | 284 |
| D_SIGNAL | −13,4 | −1,9 | −0,07 | 44,9 | 649 | 478 |
| E_COMBO | −9,5 | −1,3 | −0,15 | 28,5 | 233 | 150 |
| BENCHMARK BTC | +1910,6 | 49,2 | 0,97 | 73,6 | — | 0 |

**Le baseline passe de +70,6 % à +5,3 % quand on double les coûts.**
Il ne survit donc que grâce à une hypothèse de frais favorable — c'est la
mesure la plus fragile de tout ce rapport. Les quatre variantes deviennent
franchement perdantes.

## 5. Walk-forward — frais doublés

**In-sample (8 mars 2019 → 7 juin 2024, 5,3 ans)**

| variante | rend. % | Sharpe | maxDD % | trades |
|---|---|---|---|---|
| A_BASELINE | +18,1 | 0,26 | 35,8 | 720 |
| B_REGIME | −13,3 | −0,11 | 30,9 | 508 |
| C_UNIVERS | −12,9 | −0,24 | 27,5 | 268 |
| D_SIGNAL | −1,8 | 0,04 | 27,3 | 449 |
| E_COMBO | −1,0 | 0,01 | 17,9 | 148 |
| BENCHMARK BTC | +1778,6 | 1,18 | 73,6 | — |

**Out-of-sample (7 juin 2024 → 6 septembre 2026, 2,2 ans)**

| variante | rend. % | Sharpe | maxDD % | trades |
|---|---|---|---|---|
| A_BASELINE | −10,9 | −0,17 | 26,9 | 330 |
| B_REGIME | −9,9 | −0,21 | 25,2 | 188 |
| C_UNIVERS | −4,8 | **−0,12** | **21,9** | 176 |
| D_SIGNAL | −11,8 | −0,34 | 24,1 | 201 |
| E_COMBO | −8,6 | −0,47 | 19,0 | 86 |
| BENCHMARK BTC | +7,0 | 0,29 | 51,7 | — |

**Tout perd hors échantillon.** Le benchmark, lui, gagne +7 %.

### Variantes suspectes

Aucune variante ne bat le baseline en in-sample tout en échouant en OOS —
le drapeau « sur-ajustement » automatique ne s'est déclenché pour aucune.
La raison est moins rassurante qu'il n'y paraît : **elles échouent dans
les deux périodes**. Il n'y a pas de sur-ajustement parce qu'il n'y a rien
à sur-ajuster.

Le seul renversement notable concerne **le baseline lui-même** :
Sharpe **+0,26 en in-sample**, **−0,17 en out-of-sample**. C'est le
comportement classique d'une stratégie qui marchait dans un régime et ne
marche plus dans le suivant.

---

## 6. Limites — à lire avant toute décision

### Le critère de décision a un angle mort

Tel qu'il est formulé, il compare deux Sharpe sans exiger qu'ils soient
positifs. **C_UNIVERS est « retenue » avec un Sharpe de −0,12** : elle perd
moins vite que le baseline. Mécaniquement le critère est satisfait ;
concrètement, retenir cette variante revient à choisir la moins mauvaise
façon de perdre de l'argent.

### Biais du survivant — il gonfle TOUS les résultats

Les 70 paires sont celles **cotées aujourd'hui** sur Bitvavo. Les cryptos
retirées de la cote entre 2019 et 2026 sont absentes du jeu de données.
Le rejeu ne peut donc pas acheter un actif qui a disparu — un privilège
qu'aucune stratégie réelle n'a. **Les rendements affichés sont surestimés,
y compris ceux du baseline.**

### La capitalisation est approximée

La variante C demandait « au-dessus de la médiane de capitalisation ».
Bitvavo ne publie pas de capitalisation. J'ai utilisé le **volume échangé
médian sur 30 jours** comme approximation. C'est corrélé à la
capitalisation, ce n'est pas la même chose, et **la variante C n'est donc
pas exactement celle que tu as demandée**.

### Tailles d'échantillon

| variante | trades OOS | conclusion possible ? |
|---|---|---|
| A_BASELINE | 330 | oui |
| D_SIGNAL | 201 | oui |
| B_REGIME | 188 | oui |
| C_UNIVERS | 176 | oui, avec prudence |
| **E_COMBO** | **86** | **non — trop peu** |

Sur 86 trades, l'incertitude à deux écarts-types dépasse l'écart mesuré.
**Le verdict « non retenue » de E_COMBO est correct mais faiblement fondé** :
on ne peut pas exclure qu'elle fasse mieux sur un échantillon plus grand.

### La période hors échantillon est courte et particulière

2,2 ans, et une période où **tout perd sauf le bitcoin**. Elle peut être
représentative d'un régime durable — ou n'être qu'un mauvais moment. Un
seul découpage 70/30 ne permet pas de trancher ; il faudrait plusieurs
fenêtres glissantes pour cela.

### Le harnais n'est pas le moteur live

Écrit à part pour respecter la règle « exécution en t+1 à l'ouverture »,
que le moteur du robot n'applique pas (il exécute à la clôture du signal).
Il reproduit fidèlement **le signal, le stop, le stop suiveur et le
dimensionnement**, mais **pas** les filtres accessoires du robot :
plancher et plafond de volatilité, filtre de spread, stop temporel
« sans progression », calendrier d'annonces. L'ATR est une moyenne
arithmétique des True Range et non un lissage de Wilder.

Ces écarts vont plutôt dans le sens d'un rejeu **plus permissif** que le
robot réel.

---

## 7. Ce que je retiens, et ce que je n'affirme pas

**Ce que la mesure établit solidement :**

1. Sur 7,5 ans et 1 040 trades, le Turtle en service **sous-performe très
   largement l'achat-conservation du bitcoin** — +70 % contre +1 910 %.
2. **Aucune des 4 variantes n'améliore le baseline** de façon convaincante.
   Trois le dégradent nettement.
3. Le baseline **ne survit pas à un doublement des coûts** (+70,6 % → +5,3 %).
4. Sur les 2,2 dernières années, **les cinq configurations perdent de
   l'argent**.

**Ce que je n'affirme pas :**

- Que le Turtle « ne marche pas ». Il protège réellement du drawdown
  (36 % contre 74 %), et une stratégie de tendance se juge sur un cycle
  complet, pas sur 2,2 ans.
- Que C_UNIVERS mérite d'être déployée. Elle passe le critère écrit, pas
  le bon sens.
- Que ces chiffres se transposent au compte réel : le biais du survivant
  et les filtres absents du harnais les rendent optimistes.

**Recommandation :** ne déployer aucune des quatre variantes.
La question ouverte n'est pas « quelle variante choisir » mais
**« le suivi de tendance long-only sur crypto justifie-t-il ses frais
face à une simple détention »** — et sur cet historique, la réponse
mesurée est non.

---

## Fichiers

| fichier | contenu |
|---|---|
| `donnees.py` | téléchargement et cache des bougies D1 Bitvavo |
| `moteur.py` | harnais portefeuille, exécution t+1, frais et glissement |
| `comparer.py` | les 6 configurations, walk-forward, application du critère |
| `courbes.py` | génération des graphiques |
| `resultats.json` | toutes les métriques brutes |
| `equity.png` | courbes superposées avec le benchmark (échelle log) |
| `equity_variantes.png` | les variantes entre elles, benchmark retiré |
