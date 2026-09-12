# Prompt 1 — Supabase : projet et schéma

**Reçu** le 12 septembre 2026. **Appliqué** — voir `/supabase`.

---

Contexte : je construis une app mobile de signaux de trading crypto.
Mon bot de trading (méthode Turtle, connecté à Bitvavo) tourne déjà sur ce VPS.
L'app affichera les signaux du bot, un agenda économique et une analyse quotidienne.

Tâche : configure un projet Supabase et crée le schéma de base de données.

Tables :

1. signals
   - id, created_at, published_at
   - pair (ex: BTC/EUR), side (buy/sell)
   - entry_price, stop_loss, take_profit_1, take_profit_2
   - risk_reward (numeric), position_size_pct (numeric)
   - conviction (0-100)
   - rationale (texte, l'explication en français)
   - status (active / closed_tp / closed_sl / cancelled)
   - closed_at, result_pct
   - macro_flag (booléen : le signal traverse-t-il une annonce à fort impact)

2. economic_events
   - id, event_time, name_fr, country
   - impact (low / medium / high)
   - eve_policy (texte : ce qu'Eve fait autour de cet événement)
   - actual, forecast, previous

3. market_notes
   - id, published_at, headline, body_fr
   - trend_score, volatility_score, fear_greed, btc_dominance

4. profiles
   - id (lié à auth.users), created_at
   - tier (free / plus), risk_level (prudent / normal / agressif)
   - push_token, notif_signals, notif_macro

5. signal_taken
   - user_id, signal_id, taken_at
   (permet à l'utilisateur de marquer un trade comme pris)

Ajoute des politiques Row Level Security :
- un utilisateur ne lit que son propre profil et ses propres signal_taken
- signals, economic_events et market_notes sont en lecture pour tous les
  utilisateurs authentifiés
- seule la clé service_role peut écrire dans signals, economic_events,
  market_notes

Écris le tout en migrations SQL versionnées dans /supabase/migrations.

---

## Ce qui a été livré, et ce qui reste

Livré : cinq migrations, RLS sur les cinq tables, deux défauts de
sécurité trouvés en exécutant le SQL (récursion de politique, verrou du
palier inopérant).

Reste à la charge de l'opérateur : créer le projet sur supabase.com et
lancer `supabase db push`. Marche à suivre dans `supabase/README.md`.
