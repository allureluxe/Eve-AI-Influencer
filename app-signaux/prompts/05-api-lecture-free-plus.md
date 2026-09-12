# Prompt 5 — API de lecture et règle du gratuit

**Reçu** le 12 septembre 2026 (document `eve-instructions-claude-code.md`).
**Pas encore appliqué.**

Recopié sans retouche.

---

Tâche : crée les Edge Functions Supabase que l'app appellera.

- GET /signals : renvoie les signaux actifs et les 50 derniers clôturés.
  Si le profil de l'utilisateur est `free`, ne renvoie que les signaux
  publiés il y a plus de 2 heures, et seulement pour BTC, ETH et SOL.
  Si `plus`, tout, en temps réel.

- GET /market-note : la dernière note publiée.
- GET /events : les événements des 14 prochains jours.
- GET /performance : courbe de capital simulée depuis 10 000 € en suivant tous
  les signaux, plus les statistiques (taux de réussite, gain moyen, perte
  maximale, facteur de profit). Calcule-la à partir des signaux réels de la
  base, jamais de valeurs écrites en dur.
- POST /signal-taken : enregistre qu'un utilisateur a pris un trade.

Le filtrage free/plus se fait CÔTÉ SERVEUR uniquement. L'app ne doit jamais
recevoir un signal auquel l'utilisateur n'a pas droit.
