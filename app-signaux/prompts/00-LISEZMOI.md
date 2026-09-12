# Les 9 prompts de l'application de signaux

Consigne de l'opérateur, 12 septembre 2026 :

> « Je vais t'envoyer tous les prompts que Claude conversation m'a donnés,
> tu vas tout sauvegarder **sans rien créer**. On va continuer sur le
> robot, et quand je te demanderai, créé-moi l'application : tu lis les
> 9 prompts et tu les appliques. »

Les neuf sont arrivés d'un bloc. Le document d'origine est conservé
intact dans `00-document-original.md` ; chaque prompt est aussi rangé
seul, recopié **sans retouche**.

## État

| n° | sujet | appliqué |
|---|---|---|
| 1 | Supabase — schéma et RLS | **oui** — voir `/supabase` |
| 2 | Le bot publie ses signaux | non |
| 3 | Agenda économique + blackout | non |
| 4 | Le point de marché du matin | non |
| 5 | API de lecture, règle free/plus | non |
| 6 | Notifications push | non |
| 7 | L'application mobile (Expo) | non |
| 8 | Abonnements (RevenueCat) | non |
| 9 | Avant de publier | non |

## Ce qu'il faudra créer avant de commencer

Comptes à ouvrir par l'opérateur — je ne peux pas le faire à sa place :

| service | à quoi ça sert | coût |
|---|---|---|
| Supabase | base + comptes + API | gratuit jusqu'à 500 Mo |
| Firebase | notifications push | gratuit |
| Expo | construire l'app Android | gratuit |
| RevenueCat | abonnements | gratuit sous 2 500 $/mois |
| Google Play Console | publier | 25 € une fois |
| Trading Economics ou Finnhub | agenda économique | gratuit, limité |

Toutes les clés dans `.env`. **Jamais dans le code, jamais sur GitHub.**

## Trois points à trancher AVANT d'appliquer

Ils ne bloquent rien aujourd'hui, mais ils se contrediront le jour venu.
C'est pour ça qu'on garde les prompts mot pour mot : les contradictions
d'un cahier des charges écrit en neuf morceaux ne se voient qu'à la
relecture d'ensemble.

**1. Le prompt 4 nomme `claude-sonnet-4-6`.** Ce modèle n'existe pas ;
les identifiants actuels sont de la forme `claude-sonnet-5`. À corriger
au moment d'écrire le code, sinon l'appel échoue.

**2. Le prompt 3 et le robot ne s'accordent pas sur le blackout.** Le
prompt demande −15 min / +30 min autour d'un événement à fort impact. Le
robot applique déjà −20 / +20 (`NewsFilterConfig`). Il faudra choisir :
aligner le robot sur le prompt, ou l'inverse. Deux endroits qui décident
du même réglage, c'est le piège qui a déjà coûté quatre fois à ce dépôt.

**3. Le prompt 5 promet une courbe « depuis 10 000 € en suivant tous les
signaux ».** Calculée sur les signaux réels, elle est honnête. Mais
affichée à un utilisateur, elle ressemble à une performance — alors que
personne n'a jamais engagé ces 10 000 €. Le prompt 9 interdit justement
« tout chiffre de performance non vérifiable ». À arbitrer.

## Le conseil que le document donne, et qu'il faut garder en tête

> « Ne publie rien sur le Play Store tant que ton bot n'a pas **3 mois de
> performances positives et vérifiables**. »

Le robot est aujourd'hui à **0 trade sur 40** de preuve, résultat
−22,90 EUR sur 190 trades. C'est la contrainte la plus dure du projet, et
aucune ligne de code ne la lève.
