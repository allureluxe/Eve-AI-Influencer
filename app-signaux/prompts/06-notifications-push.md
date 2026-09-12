# Prompt 6 — Notifications push

**Reçu** le 12 septembre 2026 (document `eve-instructions-claude-code.md`).
**Pas encore appliqué.**

Recopié sans retouche.

---

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
