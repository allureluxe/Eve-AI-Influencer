# Robot de trading autonome — documentation

Robot multi-actifs (or, forex, cryptos) qui analyse, décide et **passe ses
ordres seul**, 24 h/24, avec stop-loss et take-profit systématiques, un
objectif qui se déplace quand le mouvement continue, et une gestion du
capital qui s'adapte à la courbe de résultats.

---

## 1. Démarrage rapide

```bash
# 1. Vérifier que tout répond (sources de données, calendrier, exécution)
python3 run_bot.py check

# 2. Voir ce que le robot pense du marché, sans rien exécuter
python3 run_bot.py scan
python3 run_bot.py analyse XAUUSD

# 3. Rejouer l'historique
python3 run_bot.py backtest XAUUSD --bars 5000

# 4. Tourner en simulation, en continu
python3 run_bot.py run --broker paper

# 5. Passer en réel sur Bitvavo (le robot exécute seul)
export BITVAVO_API_KEY="..." BITVAVO_API_SECRET="..."
python3 run_bot.py run --config robot.bitvavo.json
```

Deux commandes de diagnostic, à connaître :

```bash
python3 etat.py         # ce que le robot fait, tient, et ce qui le bride
python3 comparer.py     # mesurer une configuration sur l'historique
```

Aucune dépendance à installer : tout est en Python 3.11+ standard.

---

## 2. Comment une décision est prise

Deux étages, dans cet ordre. **Le second n'est jamais atteint si le premier
échoue** — c'est ce qui empêche un beau signal de compenser un contexte
mauvais.

### Étage 1 — Les filtres éliminatoires

Chaque instrument doit franchir *tous* ces filtres. Un seul échec et le robot
passe à la paire suivante.

| Filtre | Ce qu'il vérifie | Pourquoi |
|---|---|---|
| `donnees` | indicateurs prêts sur M5, M15 et H1 | décider sur un historique incomplet, c'est deviner |
| `marche_ouvert` | séance active pour cet actif | l'or dort la nuit, les cryptos non |
| `spread` | ≤ spread max **et** ≤ 22 % de l'ATR | un spread anormal mange le gain espéré |
| `volatilite` | ATR entre le 20ᵉ et le 95ᵉ percentile | marché mort = pas de mouvement ; marché fou = stop balayé |
| `calendrier` | pas d'annonce à fort impact imminente | l'or bouge de 20 à 40 $ en secondes sur NFP/CPI/FOMC |
| `configuration` | un scénario reconnu est présent | pas de scénario, pas de trade |
| `regime` | ADX ≥ 18 et régime exploitable | on ne suit pas une tendance qui n'existe pas |
| `alignement_mtf` | M15 et H1 ne contredisent pas le sens | acheter contre l'unité supérieure coûte cher |
| `marge_structurelle` | ≥ 1,2 ATR avant le prochain niveau **sérieux** | ne pas acheter sous une résistance |
| `ratio_rr` | rendement/risque ≥ 1,5 | un système gagnant a besoin d'un R correct |
| `objectif_atteignable` | ≥ 1,5R de place jusqu'au prochain obstacle | un TP qu'on ne peut pas atteindre ne sert à rien |
| `macro` | pas d'opposition fondamentale marquée | acheter l'or quand les taux réels s'envolent, c'est ramer |
| `score` | confluence ≥ seuil | dernier arbitrage |

`python3 run_bot.py analyse XAUUSD` affiche cette grille ligne par ligne, avec
le détail chiffré de chaque filtre.

### Étage 2 — Le score de confluence

Neuf lectures indépendantes, chacune ramenée dans `[-1, +1]` puis pondérée :

| Brique | Poids | Contenu |
|---|---|---|
| tendance | 0,22 | biais M5/M15/H1, Supertrend, nuage Ichimoku |
| momentum | 0,16 | MACD, RSI, stochastique, ADX |
| bougies | 0,16 | avalement, pin bar, étoile, marubozu, harami, pénétrante… |
| figures | 0,10 | double sommet/creux, épaule-tête-épaule, triangles |
| divergences | 0,08 | RSI vs prix, régulières et cachées |
| zones | 0,08 | Fair Value Gaps, order blocks, profil de volume |
| volume | 0,06 | OBV, MFI, position vs VWAP |
| macro | 0,08 | taux réels, dollar, VIX, positionnement COT |
| news | 0,06 | surprise des dernières publications vs consensus |

Score maximal théorique : 1,00. Seuil par défaut : **0,55** (0,75 à
contre-tendance), relevé automatiquement selon l'avancement de l'objectif.

### Les trois scénarios reconnus

1. **`tendance_repli`** — tendance établie, repli sur EMA / zone / Fibonacci,
   bougie de reprise. Le scénario de référence.
2. **`cassure`** — sortie de canal de Donchian, hors compression, confirmée
   par le volume.
3. **`retournement_niveau`** — uniquement en régime de retour à la moyenne :
   rejet d'un niveau + divergence + bougie de retournement.
4. **`cassure_post_annonce`** — après une publication majeure, une fois la
   première impulsion digérée (6 à 45 min après).

---

## 3. Gestion de position : le cœur du système

C'est le comportement demandé : **à l'approche de l'objectif, si la dynamique
tient, le TP recule d'un cran et le stop remonte dans le même mouvement.**

```
  0R ──────────► 0,8R  break-even : le stop passe à l'entrée, le trade ne peut plus perdre
  0,8R ────────► 1R    prise partielle de 40 % du volume
  1R ──────────► ...   stop suiveur (chandelier ATR) qui ne recule jamais
  85 % du TP ──► ...   ★ extension de l'objectif + verrouillage du stop
  dynamique KO ──►     stop resserré, objectif inchangé, on encaisse
```

### L'extension automatique, en détail

Quand le prix a parcouru **85 %** du chemin vers le TP, le robot mesure la
dynamique (`compute_momentum`) : Supertrend, position vs EMA rapide, expansion
du MACD, force de l'ADX, épuisement du RSI, bougies récentes, marge jusqu'au
prochain niveau — le tout amorti si le marché n'a pas de tendance (ADX < 20,
régime de retour à la moyenne, compression de volatilité).

- **Dynamique ≥ 0,35** → le TP recule de `max(1,2 × ATR ; 0,5R)`, plafonné à
  90 % de la distance jusqu'au prochain obstacle. **Simultanément**, le stop
  monte au plus haut de : 0,35R verrouillé, ou 1,1 ATR sous le prix courant.
  Maximum 4 extensions par trade.
- **Dynamique < 0,35** → le TP ne bouge pas, le stop se resserre à 1,0 ATR.
  On prend ce qui est acquis.

Tout est symétrique à la vente : « monter le TP » veut dire le descendre.

**Garantie testée** : le gain verrouillé ne recule jamais
(`test_le_gain_verrouille_ne_recule_jamais`). Une extension ne peut pas rendre
un trade plus risqué qu'avant.

### Sorties de sécurité

- retournement confirmé alors qu'au moins 0,5R est acquis → on sort ;
- stop temporel : 4 h sans dépasser 0,25R → le capital est libéré ;
- perte anormale (gap, stop non honoré) au-delà de 1,5R → sortie immédiate ;
- annonce imminente → stop resserré sur les positions ouvertes.

---

## 4. Money management

### Dimensionnement

```
volume = (capital × risque%) / (distance au stop × valeur du point)
```

L'arrondi au pas de lot se fait **toujours vers le bas** : dépasser le risque
visé à cause d'un arrondi serait une erreur silencieuse, répétée à chaque
trade.

### Échelle adaptative (anti-martingale)

La taille suit la courbe de capital. On augmente **avec les gains**, jamais
pour se refaire.

| Capital vs référence | Multiplicateur |
|---|---|
| +50 % | ×1,80 |
| +25 % | ×1,45 |
| +10 % | ×1,20 |
| référence | ×1,00 |
| −5 % | ×0,85 |
| −8 % | ×0,75 |
| −15 % | ×0,50 |
| −25 % | ×0,35 |

Bornes dures : ×0,30 à ×2,00. La référence se recale chaque semaine sur le
sommet atteint, pour ne pas re-risquer un capital déjà rendu.

S'y ajoutent : réduction après 2 pertes consécutives, réduction continue en
drawdown, et un **plafond dur de 1,5 % par trade** que rien ne peut franchir.

### Coupe-circuits

| Limite | Défaut | Effet |
|---|---|---|
| perte journalière | 4 % | arrêt jusqu'au lendemain |
| perte hebdomadaire | 8 % | arrêt jusqu'à lundi |
| drawdown maximal | 20 % | arrêt complet, redémarrage manuel |
| gain journalier | +6 % | journée protégée, on ne rejoue pas |
| pertes consécutives | 4 | pause de 90 min |
| positions simultanées | 3 | — |
| risque total ouvert | 3 % | — |
| trades par jour | 12 | — |
| corrélation | 1 par groupe | pas d'or + argent + AUD en même temps |

---

## 5. Le défi hebdomadaire

Objectif de la semaine 1, puis un palier de plus à chaque objectif atteint.

```bash
python3 run_bot.py objectifs
```

**Trois règles qui protègent le compte :**

1. **Un retard ne fait jamais monter le risque.** Il relève le seuil de
   validation : moins de trades, mais meilleurs. C'est l'inverse exact d'une
   martingale.
2. **L'objectif est plafonné par le capital** (8 % par semaine par défaut).
   Viser 100 € sur un compte de 500 € revient à chercher +20 % en une
   semaine : le robot affiche l'objectif nominal, applique l'objectif
   soutenable, et indique le capital nécessaire pour viser le nominal
   (1 250 € pour 100 €/semaine).
3. **Le palier ne monte que sur résultat**, pas sur calendrier. Une semaine
   perdante fait redescendre d'un cran.

Une fois l'objectif atteint : risque ×0,4, seuil +0,15. Au-delà de 160 % de
l'objectif : arrêt jusqu'à lundi.

---

## 6. Univers et couverture 24/7

| Actif | Classe | Séances (UTC) | Groupe corrélé |
|---|---|---|---|
| XAUUSD, XAGUSD | métal | 07 h–21 h, lun–ven | metals |
| EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD | forex | 07 h–21 h, lun–ven | usd_major / commodity_fx |
| BTCUSD, ETHUSD, SOLUSD, XRPUSD | crypto | 24/7 | crypto |

L'or est prioritaire (coefficient de conviction 1,25). Quand le forex et l'or
ferment, seules les cryptos restent dans la liste — le robot continue de
travailler la nuit et le week-end.

---

## 7. Sources de données

Bascule automatique : si une source tombe, la suivante prend le relais, et la
défaillante est mise en quarantaine 5 minutes.

| Source | Clé requise | Couverture |
|---|---|---|
| Binance | non | cryptos, à la minute |
| Yahoo Finance | non | or, forex, cryptos, DXY, VIX, S&P 500, 10 ans US |
| TwelveData | `TWELVEDATA_API_KEY` | XAU/USD natif, forex, crypto |
| Finnhub | `FINNHUB_API_KEY` | forex, crypto + calendrier économique |
| Polygon | `POLYGON_API_KEY` | agrégats forex/crypto |
| AlphaVantage | `ALPHAVANTAGE_API_KEY` | forex, crypto |
| MetalpriceAPI | `METALPRICE_API_KEY` | cotation spot or/argent |
| Stooq | non | historique journalier |
| FRED | `FRED_API_KEY` | taux réels 10 ans (driver n°1 de l'or) |
| CFTC | non | positionnement COT sur l'or |

Optimisation : le robot télécharge la plus petite unité de temps et agrège
localement M5/M15/H1 — moins de requêtes, moins de quota consommé.

---

## 8. Calendrier économique

Sources : Finnhub, Financial Modeling Prep, TradingEconomics, fichier local
`data/economic_calendar.json`, et un **calendrier récurrent intégré** qui
fonctionne sans aucune clé (NFP le 1ᵉʳ vendredi 12 h 30 UTC, CPI vers le 10-15,
FOMC les mercredis de milieu de mois, allocations chômage chaque jeudi).

- **Blackout** : 20 min avant / 20 min après une annonce majeure.
- **Protection** : stops resserrés dès 45 min avant.
- **Breakout** : réouverture possible 6 à 45 min après la publication.
- **Biais** : la surprise vs consensus alimente le score (une inflation
  au-dessus des attentes pèse sur l'or à court terme).

---

## 9. Exécution

Le robot ne sait pas où il passe ses ordres : toute la stratégie est écrite
contre une interface unique (`Broker`). Changer de plateforme ne demande
aucune modification de la logique de trading.

| Lieu | État | Usage |
|---|---|---|
| `paper` | intégré | simulation, backtest, mise au point |
| `bitvavo` | **en service** | plateforme européenne, cotation en euros |
| `ibkr` | prévu | à ajouter à côté de Bitvavo |

Pionex, Binance, MoonX, OKX, Coinbase et Bitstamp ont été retirés le
29 août 2026, à la demande de l'opérateur : des intégrations essayées puis
abandonnées, dont il restait assez de code pour faire échouer un démarrage
sans qu'on comprenne pourquoi.

`tests/test_plateformes_retirees.py` vérifie qu'elles ne reviennent pas, et
qu'une configuration qui en nomme une échoue avec un message clair au lieu
de planter à l'import.

### Bitvavo

```bash
export BITVAVO_API_KEY="..." BITVAVO_API_SECRET="..."
export BITVAVO_DRY_RUN=1          # simulation : aucun ordre ne part
python3 run_bot.py run --config robot.bitvavo.json
```

Sur la clé API : cochez **Consulter** et **Trader**. Ne cochez **jamais**
« Retirer ». Une clé sans droit de retrait ne peut pas sortir un centime du
compte, même volée.

**Achat seul.** Bitvavo au comptant ne permet pas la vente à découvert : la
moitié des signaux du robot — les ventes — est écartée. C'est un choix
assumé, pas une limite subie : le levier a été refusé (voir `CLAUDE.md`,
décision D1) sur un système dont l'espérance n'est pas encore établie.

**Pas d'ordre lié.** Bitvavo expose `stopLossLimit` et `takeProfitLimit`,
mais aucun ordre « l'un annule l'autre ». Poser les deux laisserait le
second vivant après que le premier a vendu, et il revendrait plus tard des
actifs qui ne sont plus là.

Le robot ne pose donc **que le stop** sur la plateforme et surveille
l'objectif lui-même, dans `TradeManager._safety_exits`. Cette vérification
n'existait d'abord que pour le simulateur : en réel, une position ne pouvait
pas se fermer en bénéfice sur son objectif. Voir `CLAUDE.md`, décision D3 —
c'est la panne qui expliquait « le robot n'a jamais clôturé en positif ».

**Précision des prix.** `pricePrecision` compte des *chiffres significatifs*,
pas des décimales. Un prix trop précis est refusé avec l'erreur 429 ; le
broker réessaie alors avec moins de chiffres et retient ce qui a marché.

**Les frais décident de l'unité de temps.** Bitvavo prélève 0,25 % par côté
au tarif normal, soit 0,50 % l'aller-retour, plus environ 0,10 % de spread
et de glissement. Rapporté à la distance du stop, cela donne :

    M15   stop 1,01 %  ->  frais = 59 % du risque
    H4    stop 4,03 %  ->  frais = 15 %
    D1    stop 9,83 %  ->  frais =  6 %

C'est pourquoi l'unité d'entrée est **H4** et le plafond de coût **15 %**.
Le raisonnement complet, avec les ATR réellement mesurés, est dans
`CLAUDE.md` et vérifié par `tests/test_stops_crypto.py`.


## 11. Fonctionnement 24/7

Cadence adaptative : 5 s en position, 20 s en recherche, 5 min marchés fermés.

- **Reprise après redémarrage** : les positions ouvertes sont récupérées avec
  leur état de gestion (extensions déjà faites, break-even, plus haut atteint).
  Sans cela, une position reprise repartirait de zéro et pourrait voir son stop
  reculer.
- **Résilience** : toute exception de cycle est capturée, comptée, suivie d'un
  délai croissant. Il faut 12 cycles en échec consécutifs pour déclencher la
  mise en sécurité.
- **Arrêt propre** (`Ctrl+C`, `SIGTERM`) : l'état est sauvegardé, les positions
  restent ouvertes et protégées par leur stop. Les fermer automatiquement
  transformerait un simple redémarrage en perte sèche.

### Service systemd

```bash
sudo cp deploy/gold-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now gold-bot
journalctl -u gold-bot -f
```

### Docker

```bash
docker build -t gold-bot -f deploy/Dockerfile .
docker run -d --name gold-bot --env-file .env -v $(pwd)/data:/app/data gold-bot
```

---

## 12. Alertes

| Canal | Configuration | Niveau par défaut |
|---|---|---|
| console | toujours actif | info |
| journal JSONL | `GB_JOURNAL_FILE` | tout |
| Telegram | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | trades |
| webhook (Discord/Slack) | `GB_WEBHOOK_URL` | trades |
| boîte d'envoi mail | `GB_ALERT_EMAIL` | alertes |

Sont notifiés : ouverture (avec tous les facteurs validés), **extension
d'objectif**, clôture (avec avancement de l'objectif hebdomadaire), suspension
sur coupe-circuit, signe de vie horaire, bilan quotidien.

---

## 13. Configuration

Trois niveaux, du plus faible au plus fort : valeurs par défaut → fichier JSON
→ variables d'environnement.

```bash
cp robot.example.json robot.json
python3 run_bot.py run --config robot.json
```

Surcharge ponctuelle :
```bash
GB_RISK_BASE_RISK_PCT=0.5 GB_STRATEGY_MIN_SCORE=0.65 python3 run_bot.py run
```

La configuration est **validée au démarrage** : un objectif initial sous le
ratio minimal exigé, un break-even placé après le TP, ou un risque total
inférieur au risque d'un seul trade sont refusés avec un message explicite.

Les clés API ne passent **que** par l'environnement, jamais par le fichier de
configuration.

---

## 14. Tests

```bash
python3 run_tests.py              # 149 tests
python3 run_tests.py trade_manager -v
```

| Fichier | Couvre |
|---|---|
| `test_trade_manager.py` | break-even, trailing, **extension du TP**, sorties |
| `test_indicators.py` | valeurs exactes des indicateurs, agrégation, Hurst |
| `test_candles.py` | patterns de bougies, niveaux, divergences, FVG |
| `test_strategy.py` | filtres éliminatoires, chemin nominal, score borné |
| `test_risk.py` | dimensionnement, échelle adaptative, coupe-circuits |
| `test_objectives.py` | paliers, plafonnement, modulation du risque |
| `test_execution.py` | simulateur, persistance, statistiques |

---

## 15. Ce que ce système ne fait pas

Par honnêteté, et parce que ces limites conditionnent l'usage :

- **Il ne garantit aucun gain.** Les filtres et la gestion du risque
  améliorent l'espérance et bornent les pertes ; ils ne créent pas de
  rentabilité là où le marché n'en offre pas.
- **Les backtests sur données synthétiques ne prouvent rien** sur la
  performance réelle. Ils valident la mécanique, pas le profit. Un backtest
  sur données réelles reste une approximation : il ne reproduit ni
  l'élargissement des spreads sur annonce, ni le slippage, ni les rejets
  d'ordre.
- **(obsolète — MoonX a été retiré le 29 août 2026)** depuis
  l'environnement de développement (domaine bloqué). Le mode `--dry-run`
  existe pour valider le format des ordres avant d'engager de l'argent.
- **Un objectif hebdomadaire chiffré reste une contrainte artificielle.** Le
  marché ne donne pas 100 € parce que c'est écrit dans un fichier. Le
  plafonnement et la modulation de la sélectivité limitent les dégâts de cette
  contrainte, ils ne la rendent pas réaliste sur un petit capital.

## 16. Trading rapide : mode quorum et coût d'exécution

### Le mode quorum

Par défaut, le robot exige une **confluence** : neuf lectures pondérées qui
doivent produire un score élevé. Peu de trades, forte conviction.

Le mode **quorum** renverse la logique : il suffit qu'un nombre minimal de
confirmations **indépendantes** soient d'accord.

```json
"strategy": { "mode": "quorum", "min_confirmations": 3,
              "require_candle_confirmation": true }
```

Les neuf confirmations, chacune interrogeant une famille d'information
différente — additionner trois lectures du même phénomène ne prouverait rien :

| Confirmation | Ce qu'elle regarde |
|---|---|
| `bougies` | motif de price action dans le sens du trade |
| `tendance` | prix du bon côté de l'EMA, moyennes ordonnées |
| `momentum` | histogramme MACD en expansion |
| `supertrend` | filtre directionnel ATR |
| `oscillateur` | RSI en zone saine, croisement stochastique |
| `volume` | pente OBV, Money Flow Index |
| `vwap` | prix du bon côté du VWAP de séance |
| `structure` | appui sur une zone ou un niveau sérieux |
| `contexte` | l'unité supérieure ne s'y oppose pas |

Le sens retenu est celui qui rassemble le plus de confirmations, et il doit
**devancer** l'autre d'au moins `confirmation_margin` : à égalité, le marché
est indécis et le robot passe.

Un retard sur l'objectif hebdomadaire relève le quorum d'un cran — en retard,
le robot ne prend pas plus de risque, il exige une preuve de plus.

### Le coût d'exécution : le paramètre qui décide de tout

C'est le résultat le plus important de la mise au point du mode rapide, et il
n'est pas intuitif : **ce n'est pas le capital qui décide de la viabilité du
scalping, c'est le rapport entre le coût d'un aller-retour et le risque du
trade.**

Simulation Monte-Carlo, 4 000 tirages, compte de 50 €, 20 trades par jour
pendant 3 mois, avec un système réellement bon (55 % de réussite à 1,3 de
ratio) :

| Coût par trade | Rapport coût/risque | Capital médian à 3 mois |
|---|---|---|
| 0,00 € (théorique) | 0 % | 1 107 € |
| 0,08 € (EURUSD 0,01 lot) | 17 % | **446 €** |
| 0,20 € (GBPUSD, USDCAD) | 30 % | **15 € — compte détruit** |
| 0,40 € (or 0,01 lot) | 40 % | **15 € — compte détruit** |

Même système, même nombre de trades, même edge. Seul le coût change.

Le robot refuse donc en amont tout trade dont le coût dépasse
`max_cost_ratio_pct` (15 % par défaut) du risque engagé, plutôt que de le
découvrir sur le relevé de compte.

Conséquence directe, en M1 :

| Unité de temps | Instruments dont le coût reste sous 15 % du risque |
|---|---|
| **M1** | XAUUSD, BTCUSD, ETHUSD, SOLUSD |
| **M5** | + EURUSD, GBPUSD, AUDUSD, USDCAD, USDJPY |
| **M15** | tous, y compris XAGUSD et XRPUSD |

Le forex en M1 coûte 17 à 28 % du risque : le robot l'écarte tout seul. Le
remède n'est jamais « accepter quand même », c'est **élargir le stop** ou
**monter d'une unité de temps**.

### Le plancher de stop : ce qui rend le forex traitable

Le rapport coût/risque se simplifie **exactement** :

```
coût / risque = (spread × valeur) / (stop × valeur) = spread / stop
```

Ni le capital ni le volume n'y entrent. Pour qu'un aller-retour coûte au plus
X % de ce que le trade risque, il suffit donc que :

```
stop  ≥  spread / X          →  à 15 % :  stop ≥ 6,67 × spread
```

Le robot applique ce plancher automatiquement. Effet sur un stop en M1 :

| Instrument | Stop sans plancher | Ratio | Stop avec plancher | Ratio |
|---|---|---|---|---|
| EURUSD | 0,00043 | 19 % | 0,00053 (2,7 ATR) | **14 %** |
| GBPUSD | 0,00055 | 22 % | 0,00080 (3,5 ATR) | **14 %** |
| USDJPY | 0,05900 | 17 % | 0,06700 (2,4 ATR) | **14 %** |
| XAUUSD | 1,93 | 16 % | 2,00 (2,2 ATR) | **14 %** |
| BTCUSD | 109,92 | 7 % | inchangé | 7 % |

Le forex redevient traitable en M1 en élargissant le stop de 20 à 45 % — pas
en changeant de marché. Le plancher est borné par `max_stop_atr_for_cost`
(4 ATR) : au-delà, ce n'est plus le stop qui est en cause mais l'unité de temps.

### L'unité de temps choisie par instrument

Quand même le plancher ne suffit pas, le robot descend d'un cran tout seul :

```json
"strategy": { "adaptive_timeframe": true,
              "timeframe_ladder": ["M1", "M5", "M15"] }
```

| Instrument | Unité retenue | Chemin |
|---|---|---|
| BTCUSD, ETHUSD, SOLUSD | M1 | 6-13 % dès la M1 |
| EURUSD, GBPUSD, USDJPY, USDCAD | M1 | grâce au plancher de stop |
| XAUUSD | M1 | 13 % |
| AUDUSD | **M5** | M1 20 % → M5 12 % |
| XAGUSD | **M5** | M1 36 % → M5 15 % |
| XRPUSD | **M5** | M1 28 % → M5 15 % |

Aucun instrument n'est perdu : chacun est traité à la cadence la plus rapide
qu'il peut se permettre.

### Une note sur la volatilité

Contre-intuitif mais mesurable : le forex majeur est le **moins** volatil des
instruments suivis. Amplitude journalière typique — SOL 6 %, XRP 5 %, ETH
4,5 %, BTC 3,5 %, argent 2 %, or 1,2 %, puis AUDUSD 0,70 %, GBPUSD 0,65 %,
EURUSD 0,55 %.

C'est précisément pour cela que le spread y pèse si lourd en unité de temps
courte : le prix ne parcourt pas assez de distance pour l'amortir. Le forex
compense par une liquidité et des spreads très serrés en valeur absolue — d'où
l'efficacité du plancher de stop, qui suffit à le remettre dans le jeu.

### Mode micro-capital

`robot.bitvavo.json` combine les deux mécanismes pour un compte de 20 à 200 €,
en M1, quorum de 3 confirmations, jusqu'à 40 trades par jour.

```bash
python3 run_bot.py run --config robot.bitvavo.json
```

Backtest de contrôle sur l'univers complet, 2,8 jours de données M1 :

| Instrument | Trades | Par jour |
|---|---|---|
| ETHUSD | 95 | 34,2 |
| BTCUSD | 63 | 22,7 |
| SOLUSD | 31 | 11,2 |
| EURUSD | 6 | 2,2 |
| GBPUSD | 2 | 0,7 |
| **Total** | **197** | **70,9** |

Le plafond `max_daily_trades` (30) et la limite d'une position à la fois
ramènent cela dans la fourchette visée de 20 à 30 trades par jour. Le forex
en produit nettement moins que les cryptos : il est fermé la moitié du temps
et ses motifs de bougies passent moins souvent le test de significativité
en M1.

Gain attendu par trade gagnant au lot minimum, en M1 : environ **0,16 € sur
BTC, 0,08 € sur ETH**. Ce sont de petits montants, c'est le principe du mode.
Ils grossissent avec le capital, puisque la taille suit la courbe de résultats.

### Adaptation automatique au capital

Le robot n'a pas besoin qu'on lui dise quoi trader : le lot minimum et le coût
d'exécution le décident pour lui.

| Capital | Palier | Positions simultanées |
|---|---|---|
| < 100 € | micro | 1 |
| 100 à 500 € | petit | 1 |
| 500 à 2 000 € | moyen | 2 |
| > 2 000 € | confortable | selon la configuration |

Quand un instrument est refusé pour une raison **structurelle** — lot minimum
trop lourd, coût disproportionné, levier dépassé — il est mis en sommeil une
heure au lieu d'être redemandé à chaque cycle. Cela économise le quota d'API et
fait converger le robot sur l'ensemble réellement traitable. Il se réveille
tout seul quand le capital a changé.

---

## 17. Petit capital : ce que le lot minimum impose

Le pas de lot du broker est un **plancher physique** : on ne peut pas risquer
moins que ce que coûte un lot minimum. Sur un petit compte, c'est lui qui
décide de ce qui est tradable, pas la configuration.

Risque représenté par **un seul lot minimum**, selon le capital :

| Instrument | Lot min | Notionnel | 150 € | 250 € | 500 € | 1 000 € |
|---|---|---|---|---|---|---|
| XAUUSD | 0,01 | 2 650 € | refusé | refusé | 1,11 % | 0,55 % |
| XAGUSD | 0,01 | 1 550 € | refusé | refusé | 0,90 % | 0,45 % |
| USDCAD | 0,01 | 1 380 € | 1,03 % | 0,62 % | 0,31 % | 0,16 % |
| GBPUSD | 0,01 | 1 270 € | 0,93 % | 0,56 % | 0,28 % | 0,14 % |
| EURUSD | 0,01 | 1 085 € | 0,77 % | 0,46 % | 0,23 % | 0,12 % |
| AUDUSD | 0,01 | 655 € | 0,54 % | 0,32 % | 0,16 % | 0,08 % |
| BTCUSD | 0,001 | 68 € | 0,23 % | 0,14 % | 0,07 % | 0,03 % |
| ETHUSD | 0,01 | 33 € | 0,11 % | 0,07 % | 0,03 % | 0,02 % |
| SOLUSD | 0,1 | 16 € | 0,06 % | 0,03 % | 0,02 % | 0,01 % |
| USDJPY | 0,01 | 152 000 € | refusé | refusé | refusé | refusé |

« Refusé » = le lot minimum dépasse le plafond de risque, le robot n'ouvre pas.

**Conséquences concrètes :**

- **Sous ~370 €, l'or n'est pas tradable.** Le robot le sait et bascule seul
  sur les cryptos et le forex. Il se remettra à trader XAUUSD automatiquement
  dès que le capital passera ce seuil — aucune configuration à changer.
- **Sous ~300 €, viser un risque de 0,25 % par trade est impossible** sur le
  forex : le lot minimum vaut déjà 0,5 à 1 %. Seules les cryptos offrent une
  granularité assez fine.
- **USDJPY est hors de portée** en dessous de 10 700 € : il est retiré de
  l'univers de rodage.

### Configuration de rodage fournie

`robot.bitvavo.json` est calibré pour un compte réel de moins de 300 € : une
seule position à la fois, risque 0,5 % (plafond 1 %), perte journalière
limitée à 3 %, hebdomadaire à 6 %, drawdown maximal 15 %, 6 trades par jour
maximum, 2 minutes minimum entre deux trades, contre-tendance désactivée et
seuil de score relevé à 0,60.

```bash
python3 run_bot.py run --config robot.bitvavo.json
```

À relever quand le capital dépasse 1 000 € : `max_positions` à 2 puis 3, et
`base_risk_pct` à 0,75.

---

## 18. Avant d'engager de l'argent réel

1. `python3 run_bot.py check` — vérifier que les sources répondent.
2. Faire tourner en `--broker paper` pendant plusieurs jours de marché.
3. Passer en `--broker bitvavo --dry-run` : ordres formatés et journalisés, rien
   envoyé. Vérifier le contenu de `data/journal.jsonl`.
4. Démarrer en réel avec `GB_RISK_BASE_RISK_PCT=0.25` et
   `GB_RISK_MAX_POSITIONS=1`, puis remonter progressivement.
5. Garder les alertes Telegram actives : un robot autonome doit rester
   observable.
