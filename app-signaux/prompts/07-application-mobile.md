# Prompt 7 — L'application mobile

**Reçu** le 12 septembre 2026 (document `eve-instructions-claude-code.md`).
**Pas encore appliqué.**

Recopié sans retouche.

---

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
