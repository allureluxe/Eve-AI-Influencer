# Eve-AI-Influencer

Ce dépôt contient trois projets indépendants :

1. **Luna** — compagne virtuelle IA : messages, appel vocal et visio avec un
   avatar animé.
2. **Eve AI** — bot d'influence automatisé (Instagram & TikTok) avec génération
   d'images.
3. **Robot de trading autonome** — analyse, décide et exécute seul sur l'or,
   le forex et les cryptos, 24 h/24, via MoonX.

---

## Luna — compagne virtuelle IA

Personnage de fiction adulte, généré par une IA. Elle n'est pas une personne
réelle et ne prétend jamais l'être.

```bash
python3 luna.py app       # http://127.0.0.1:8765 — messages, appel, visio
python3 luna.py chat      # la même conversation, dans le terminal
python3 luna.py check     # ce qui est configuré, ce qui manque
```

**Documentation complète : [`docs/LUNA.md`](docs/LUNA.md)**

| | |
|---|---|
| **Modes** | messages, appel vocal, visio avec avatar animé |
| **Avatar** | dessiné et animé dans le navigateur : clignements, expressions, lèvres synchronisées |
| **Voix** | synthèse et reconnaissance du navigateur — rien ne sort de la machine |
| **Personnage** | journée de travail, retour, soirée, nuit : le ton suit l'heure |
| **Mémoire** | prénom, goûts, dates, fil des échanges, dans `data/luna/` |
| **Cadre** | porte 18+, registres tendre / sensuel / adulte, plafond par canal |
| **Moteur** | API Anthropic, tout endpoint compatible OpenAI, ou mode hors ligne |
| **Dépendances** | aucune — Python 3.11+ et un navigateur |
| **Tests** | 37 tests |

Le plafond par canal est la garantie centrale : même vérifié 18+, **rien de
sensuel ne part vers Instagram, Snapchat ou par SMS**. Ces plateformes
interdisent ce contenu, et un compte banni ne revient pas.

---

## Robot de trading

Système court terme multi-actifs qui ne prend une position que si **tous** ses
filtres de validation passent — sinon il passe à l'instrument suivant.

```bash
python3 run_bot.py check            # vérifier l'installation et les accès
python3 run_bot.py analyse XAUUSD   # voir la décision, filtre par filtre
python3 run_bot.py backtest XAUUSD  # rejouer l'historique
python3 run_bot.py run              # lancer en continu (simulation par défaut)
```

**Documentation complète : [`docs/ROBOT_TRADING.md`](docs/ROBOT_TRADING.md)**

### En bref

| | |
|---|---|
| **Actifs** | XAUUSD, XAGUSD, 5 paires forex, BTC/ETH/SOL/XRP — l'or prioritaire |
| **Unités de temps** | déclenchement M5, contexte M15, biais H1, affinage M1 |
| **Décision** | 13 filtres éliminatoires, puis un score de confluence sur 9 lectures |
| **Analyse** | 20 indicateurs, 12 patterns de bougies, S/R, Fibonacci, pivots, divergences, FVG, order blocks, profil de volume |
| **Fondamental** | taux réels 10 ans, DXY, VIX, positionnement COT, calendrier économique |
| **Gestion** | SL/TP systématiques, break-even, prise partielle, trailing ATR, **extension automatique de l'objectif** |
| **Capital** | taille indexée sur la courbe de résultats, plafond dur de 1,5 % par trade, 8 coupe-circuits |
| **Objectifs** | défi hebdomadaire par paliers, plafonné par la capacité du compte |
| **Exécution** | Binance Futures (testnet inclus), simulateur intégré, MoonX prêt |
| **Fonctionnement** | daemon 24/7, reprise après crash, systemd et Docker fournis |
| **Dépendances** | aucune — Python 3.11+ standard |
| **Tests** | 204 tests |

### Le comportement central

À 85 % du chemin vers l'objectif, si la dynamique tient, **le take-profit
recule d'un cran et le stop-loss remonte dans le même mouvement** — le trade
continue de courir avec un gain déjà verrouillé. Si la dynamique faiblit,
l'objectif ne bouge pas et le stop se resserre pour encaisser. Symétrique à
l'achat et à la vente.

### Avant d'engager de l'argent réel

`--broker paper` pendant plusieurs jours, puis Binance **testnet**
(`BINANCE_TESTNET=1`, même API, argent fictif), puis réel avec
`GB_RISK_BASE_RISK_PCT=0.5`. Aucun système ne garantit un gain : les filtres
et la gestion du risque améliorent l'espérance et bornent les pertes, ils ne
créent pas de rentabilité là où le marché n'en offre pas.

---

## Eve AI — bot d'influence

Génération d'images et publication automatisée sur Instagram et TikTok.
Configuration dans `config.py`, variables d'environnement dans `.env.example`.

```bash
pip install -r requirements.txt
```
