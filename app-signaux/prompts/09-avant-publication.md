# Prompt 9 — Avant de publier

**Reçu** le 12 septembre 2026 (document `eve-instructions-claude-code.md`).
**Pas encore appliqué.**

Recopié sans retouche.

---

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
