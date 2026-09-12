# Prompt 2 — Le bot publie ses signaux

**Reçu** le 12 septembre 2026 (document `eve-instructions-claude-code.md`).
**Pas encore appliqué.**

Recopié sans retouche.

---

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
