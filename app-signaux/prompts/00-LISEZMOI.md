# Les 9 prompts de l'application de signaux

Consigne de l'opérateur, 12 septembre 2026 :

> « Je vais t'envoyer tous les prompts que Claude conversation m'a donnés,
> tu vas tout sauvegarder **sans rien créer**. On va continuer sur le
> robot, et quand je te demanderai, créé-moi l'application : tu lis les
> 9 prompts et tu les appliques. »

## État

| n° | sujet | reçu | appliqué |
|---|---|---|---|
| 1 | Supabase — schéma et RLS | oui | **oui** (voir `/supabase`) |
| 2 | — | non | non |
| 3 | — | non | non |
| 4 | — | non | non |
| 5 | — | non | non |
| 6 | — | non | non |
| 7 | — | non | non |
| 8 | — | non | non |
| 9 | — | non | non |

## Règle de travail

**Rien ne se construit avant le signal.** Les prompts arrivent, ils sont
rangés ici tels quels, et le travail sur le robot continue en parallèle.

Le prompt 1 fait exception : il avait été demandé avant cette consigne et
il est déjà livré — cinq migrations dans `/supabase/migrations`, rejouées
sur PostgreSQL 18 et testées contre neuf tentatives d'abus.

## Pourquoi les garder mot pour mot

Un prompt reformulé est un prompt perdu. Ils sont recopiés **sans
retouche**, y compris ce qui paraît redondant : c'est en les relisant
tous ensemble qu'on verra les contradictions entre eux — et il y en a
toujours, sur un cahier des charges écrit en neuf morceaux.
