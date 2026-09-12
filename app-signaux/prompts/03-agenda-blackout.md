# Prompt 3 — Agenda économique + règle de blackout

**Reçu** le 12 septembre 2026 (document `eve-instructions-claude-code.md`).
**Pas encore appliqué.**

Recopié sans retouche.

---

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
