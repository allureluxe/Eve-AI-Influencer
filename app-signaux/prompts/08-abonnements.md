# Prompt 8 — Abonnements

**Reçu** le 12 septembre 2026 (document `eve-instructions-claude-code.md`).
**Pas encore appliqué.**

Recopié sans retouche.

---

Tâche : intègre RevenueCat pour l'abonnement Eve Plus.

- un seul produit : abonnement mensuel 29 €, essai gratuit de 7 jours
- déclaré dans Google Play Console comme abonnement
- un webhook RevenueCat met à jour profiles.tier (free / plus) dans Supabase
- l'app ne décide jamais du statut : elle le lit depuis le profil serveur
- écran de gestion : date de prochain prélèvement, bouton résilier qui ouvre
  directement les abonnements Google Play

Teste le cycle complet en sandbox : essai, conversion, résiliation, expiration.
