# Prompt 4 — Le point de marché du matin

**Reçu** le 12 septembre 2026 (document `eve-instructions-claude-code.md`).
**Pas encore appliqué.**

Recopié sans retouche.

---

Tâche : crée un service `market_note` qui tourne chaque matin à 9 h 30 (Paris).

Il doit :
1. rassembler les données du jour : prix et variation 7 jours du BTC et de l'ETH,
   position par rapport à la moyenne 50 jours, indice Fear & Greed
   (API alternative.me, gratuite), dominance BTC, volatilité (ATR 14),
   et les événements économiques du jour
2. appeler l'API Claude (modèle claude-sonnet-4-6) avec ces données pour
   rédiger une note de marché

Règles pour le prompt envoyé à Claude :
- 3 paragraphes maximum, en français simple, niveau grand public
- un titre d'une phrase qui dit ce qui compte aujourd'hui
- interdiction absolue de prédire un prix ou de promettre un gain
- si un événement à fort impact a lieu aujourd'hui, il doit être mentionné
- ton factuel et calme, jamais vendeur, jamais alarmiste

3. écris le résultat dans market_notes avec les scores numériques

Prévois un mode "brouillon" : la note est stockée avec published_at = null,
je la valide manuellement depuis un petit script CLI avant publication.
