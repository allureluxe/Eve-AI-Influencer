# Eve-AI-Influencer

Ce dépôt contient deux projets indépendants :

1. **Eve AI** — bot d'influence automatisé (Instagram & TikTok) avec génération d'images.
2. **Robot de trading autonome** — module de trading connecté exclusivement à **Bitvavo**.

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
