# Eve-AI-Influencer

Ce dépôt contient trois projets indépendants :

1. **Luna** — compagne virtuelle IA : messages, appel vocal et visio avec un
   avatar animé.
2. **Eve AI** — bot d'influence automatisé (Instagram & TikTok) avec génération d'images.
3. **Robot de trading autonome** — module de trading connecté exclusivement à **Bitvavo**.

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

## Robot de trading Bitvavo

Le robot analyse les marchés, applique ses règles de stratégie et de gestion du risque, puis peut exécuter les ordres via Bitvavo.

```bash
python3 run_bot.py check
python3 run_bot.py analyse BTC-EUR
python3 run_bot.py backtest BTC-EUR
python3 run_bot.py run
```

Les anciennes intégrations Binance et MoonX ne font plus partie du projet.

### Sécurité

Les clés API Bitvavo doivent être fournies uniquement via les variables d'environnement ou le gestionnaire de secrets. Ne jamais les commit dans Git.

### Avant le réel

Le robot doit être validé avec les tests automatisés et une connexion Bitvavo de validation avant toute exécution engageant des fonds réels. Aucun système de trading ne garantit un gain.

---

## Eve AI — bot d'influence

Génération d'images et publication automatisée sur Instagram et TikTok.

```bash
pip install -r requirements.txt
```

<!-- Bitvavo-only trading cleanup validation marker -->
