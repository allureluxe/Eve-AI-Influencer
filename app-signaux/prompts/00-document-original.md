# Eve — instructions pour Claude Code

Colle ces prompts **un par un**, dans l'ordre, dans Claude Code sur ton VPS.
Ne passe au suivant qu'une fois le précédent testé et fonctionnel.

---

## Avant de commencer

Crée ces comptes (tous gratuits au départ) :

| Service | À quoi ça sert | Coût |
|---|---|---|
| Supabase | Base de données + comptes utilisateurs + API | Gratuit jusqu'à 500 Mo |
| Firebase | Notifications push | Gratuit |
| Expo | Construire l'app Android | Gratuit |
| RevenueCat | Gérer les abonnements | Gratuit sous 2 500 $/mois |
| Google Play Console | Publier l'app | 25 € une fois |
| Trading Economics ou Finnhub | Agenda économique | Gratuit en version limitée |

Garde toutes les clés API dans un fichier `.env` — **jamais dans le code**, jamais sur GitHub.

---

## Prompt 1 — Base de données

```
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
```

---

## Prompt 2 — Le bot publie ses signaux

```
Tâche : crée un module `signal_publisher` dans mon bot de trading.

Quand le bot génère un signal (entrée, stop, objectif), le module doit :
1. écrire une ligne dans la table `signals` de Supabase
2. calculer et remplir risk_reward automatiquement
3. générer le champ `rationale` : une explication de 2 à 3 phrases, en français
   simple, compréhensible par quelqu'un qui ne connaît rien au trading.
   Pas de jargon. Exemple du ton attendu :
   "Le bitcoin vient de casser son plus haut des 20 derniers jours, avec 40 %
   d'échanges en plus que la moyenne. Ce type de cassure se prolonge souvent
   quelques jours."
4. mettre à jour la ligne quand la position se ferme (status, closed_at,
   result_pct)

Contraintes :
- ne modifie pas la logique de trading existante, ajoute seulement la publication
- si Supabase est injoignable, le bot continue de trader normalement et rejoue
  la publication plus tard (file d'attente locale)
- un signal publié n'est JAMAIS modifié rétroactivement, sauf son statut de
  clôture. C'est la base de la confiance.

Ajoute des tests qui vérifient qu'un signal simulé est bien publié avec tous
ses champs.
```

---

## Prompt 3 — Agenda économique + règle de blackout

```
Tâche : crée un service `economic_calendar` qui tourne une fois par jour.

1. Récupère les événements économiques des 30 prochains jours via l'API
   [Trading Economics ou Finnhub, clé dans .env].
   Garde uniquement : USA, zone euro, et les événements d'impact medium/high.

2. Traduis le nom de chaque événement en français courant :
   - "US CPI" → "Inflation américaine"
   - "Non-Farm Payrolls" → "Emploi américain"
   - "FOMC Rate Decision" → "Décision de taux de la Fed"
   Fais une table de correspondance, avec repli sur le nom d'origine.

3. Remplis eve_policy selon l'impact :
   - high  → "Aucun nouveau signal entre [heure-15min] et [heure+30min]."
   - medium → "Signaux maintenus, taille de position réduite de moitié."
   - low   → "Sans effet attendu."

4. Crée une fonction `is_blackout(datetime)` que le bot de trading appelle
   AVANT d'ouvrir toute position. Si on est dans une fenêtre de -15 min à
   +30 min autour d'un événement high, le bot n'ouvre rien. Les positions déjà
   ouvertes gardent leur stop loss et ne sont pas fermées de force.

5. Marque macro_flag = true sur tout signal dont l'horizon traverse un
   événement high.

Intègre is_blackout() dans la boucle de décision du bot existant.
```

---

## Prompt 4 — Le point de marché du matin

```
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
```

---

## Prompt 5 — API de lecture et règle du gratuit

```
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
```

---

## Prompt 6 — Notifications push

```
Tâche : mets en place les notifications via Firebase Cloud Messaging.

Déclencheurs :
1. nouveau signal publié → envoi immédiat aux utilisateurs `plus`,
   et 2 heures plus tard aux `free`
2. événement économique à fort impact → notification 15 minutes avant,
   uniquement si notif_macro est activé
3. signal clôturé → notification aux utilisateurs qui ont marqué ce trade
   comme pris

Textes des notifications :
- "Nouveau signal — Bitcoin, achat à 58 420 €"
- "Inflation américaine dans 15 minutes. Pense à sécuriser tes positions."
- "Ton trade Bitcoin a atteint son objectif : +4,2 %"

Jamais de point d'exclamation, jamais d'emoji, jamais de promesse de gain.
Respecte le fuseau de l'utilisateur et n'envoie rien entre 23 h et 7 h, sauf
un signal en temps réel pour un utilisateur `plus` qui l'a explicitement activé.
```

---

## Prompt 7 — L'application mobile

```
Tâche : crée une app Expo (React Native) qui reprend exactement la maquette
React que je te fournis en pièce jointe [eve-app-v2.jsx].

4 onglets : Signaux, Analyse, Agenda, Compte.

- garde le design à l'identique : couleurs, arrondis, espacements, textes
- branche chaque écran sur les Edge Functions du prompt 5
- connexion par email + lien magique (Supabase Auth), pas de mot de passe
- écrans de chargement en squelette, pas de roue qui tourne
- gestion hors-ligne : affiche les derniers signaux en cache avec la mention
  "dernière mise à jour il y a X minutes"
- un écran d'accueil au premier lancement : 3 écrans qui expliquent ce qu'Eve
  fait, ce qu'elle ne fait pas (elle ne touche pas à ton argent), et comment
  passer un ordre sur Bitvavo ou Binance

Build Android via EAS.
```

---

## Prompt 8 — Abonnements

```
Tâche : intègre RevenueCat pour l'abonnement Eve Plus.

- un seul produit : abonnement mensuel 29 €, essai gratuit de 7 jours
- déclaré dans Google Play Console comme abonnement
- un webhook RevenueCat met à jour profiles.tier (free / plus) dans Supabase
- l'app ne décide jamais du statut : elle le lit depuis le profil serveur
- écran de gestion : date de prochain prélèvement, bouton résilier qui ouvre
  directement les abonnements Google Play

Teste le cycle complet en sandbox : essai, conversion, résiliation, expiration.
```

---

## Prompt 9 — Avant de publier

```
Tâche : prépare la mise en production et la soumission Play Store.

1. Sécurité
   - aucune clé API dans le code de l'app
   - rate limiting sur les Edge Functions
   - toutes les tables en RLS, vérifiées une par une

2. Conformité Play Store
   - remplis la déclaration "Fonctionnalités financières" dans Play Console
   - politique de confidentialité et CGU hébergées sur une page publique
   - dans la fiche du store et dans l'app : aucune promesse de gain, aucun
     "garanti", aucun témoignage inventé, aucun chiffre de performance
     non vérifiable
   - mention visible : "Eve publie des analyses de marché. Ce n'est pas un
     conseil en investissement personnalisé. Nous ne détenons aucun fonds."

3. Génère les captures d'écran, l'icône et la description du store à partir
   de la maquette.

4. Rédige une checklist de tests avant chaque mise à jour.
```

---

## Ordre et durée réaliste

| Étape | Prompts | Durée |
|---|---|---|
| Backend et bot connecté | 1 à 3 | 4 à 6 jours |
| Analyse et API | 4 à 5 | 3 jours |
| Notifications | 6 | 2 jours |
| App mobile | 7 | 7 à 10 jours |
| Abonnements | 8 | 2 jours |
| Mise en production | 9 | 3 jours |

**Environ 4 semaines de travail avec Claude Code.**

---

## Le conseil le plus important

Ne publie rien sur le Play Store tant que ton bot n'a pas **3 mois de
performances positives et vérifiables**.

Entre-temps, mets l'app en ligne comme site web et donne l'accès gratuit à
20 personnes. Tu apprendras en deux semaines si les gens accrochent — et tu
auras l'historique qui rend l'abonnement défendable.
