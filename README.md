# Eve-AI-Influencer

Ce dépôt contient deux projets indépendants :

1. **Eve AI** — bot d'influence automatisé (Instagram & TikTok) avec génération
   d'images.
2. **Robot de trading autonome** — analyse, décide et exécute seul sur l'or,
   le forex et les cryptos, 24 h/24, via MoonX.

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
| **Exécution** | MoonX (API REST ou pont), simulateur intégré |
| **Fonctionnement** | daemon 24/7, reprise après crash, systemd et Docker fournis |
| **Dépendances** | aucune — Python 3.11+ standard |
| **Tests** | 149 tests |

### Le comportement central

À 85 % du chemin vers l'objectif, si la dynamique tient, **le take-profit
recule d'un cran et le stop-loss remonte dans le même mouvement** — le trade
continue de courir avec un gain déjà verrouillé. Si la dynamique faiblit,
l'objectif ne bouge pas et le stop se resserre pour encaisser. Symétrique à
l'achat et à la vente.

### Avant d'engager de l'argent réel

`--broker paper` pendant plusieurs jours, puis `--broker moonx --dry-run`
(ordres formatés et journalisés, rien envoyé), puis réel avec
`GB_RISK_BASE_RISK_PCT=0.25`. Aucun système ne garantit un gain : les filtres
et la gestion du risque améliorent l'espérance et bornent les pertes, ils ne
créent pas de rentabilité là où le marché n'en offre pas.

---

## Eve AI — bot d'influence

Génération d'images et publication automatisée sur Instagram et TikTok.
Configuration dans `config.py`, variables d'environnement dans `.env.example`.

```bash
pip install -r requirements.txt
```
