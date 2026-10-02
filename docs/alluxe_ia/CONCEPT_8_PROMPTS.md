# alluxe.ia — les 8 prompts de @_mind__vision_, exécutés un par un

3 octobre 2026. Chaque étape cite le prompt **mot pour mot** (relu sur les
captures envoyées par l'opérateur), puis donne la réponse. La première
version du concept (2 octobre) avait sauté l'étape 1 : la niche avait été
reprise du compte d'exemple sans recherche. Celle-ci repart de zéro.

Règles qui s'appliquent partout : le robot de trading n'apparaît que comme
histoire technique (jamais de résultat, de gain, de stratégie présentée
comme gagnante, ni de lien vers Bitvavo) ; aucune clé ni donnée
personnelle à l'écran ; « Publicité » sur tout lien rémunéré (loi du
9 juin 2023).

---

## Prompt n°1 — trouver la niche

> Identifie une liste de niches Instagram à fort potentiel de croissance,
> optimisées pour une page thématique faceless, qui restent encore
> sous-exploitées par rapport à la demande actuelle de l'audience.
> Pour chaque niche, analyse trois éléments : le principal moteur de
> demande qui explique sa dynamique actuelle, le meilleur format de
> contenu faceless qu'elle permet — Reels, carrousels, visuels avec
> citations ou compilations de données — et le signal de marché précis
> qui confirme l'opportunité, qu'il s'agisse d'un écart entre engagement
> et nombre d'abonnés, d'un faible nombre de créateurs ou de sujets
> tendance exploitables.
> Privilégie les niches avec des structures de contenu reproductibles, un
> fort potentiel de sauvegardes et de partages, ainsi qu'une voie claire
> vers la monétisation dès le premier jour.

| niche | moteur de demande | meilleur format sans visage | signal de marché | verdict |
|---|---|---|---|---|
| Packs de prompts IA | tout le monde veut « savoir utiliser ChatGPT » | carrousel de prompts | **négatif** : « pas de place pour le 700e compte qui fait 5 prompts » | saturée |
| Finance personnelle | inflation, épargne | carrousel de chiffres | meilleur revenu par abonné (annonceurs 3 à 5× plus chers) | **éliminée** : promotion crypto interdite hors prestataires agréés, AMF |
| Psychologie, développement perso | stress, recherche d'équilibre | citations, carrousels | beaucoup de sauvegardes | pas d'avantage propre |
| Productivité avec l'IA | gagner du temps au travail | carrousel tuto | sauvegardes élevées | concurrence forte, avantage faible |
| Automatisation IA (n8n, Make) | « travailler moins » | écran filmé | Yyov7 : 866 k sur TikTok | occupée par de gros comptes |
| **Construire des systèmes avec l'IA sans être développeur** | le « vibe coding » : 63 % de ses utilisateurs ne sont pas développeurs | **écran filmé (Reel) + carrousel tuto** | **écart offre/demande** : formations, écoles et guides 2026 en français partout, mais aucun créateur français trouvé qui montre un système réel en service ; construire en public = 4,5 % d'engagement contre 1,5 % de médiane | **retenue** |

**Pourquoi elle coche les trois critères du prompt.**
- *Structure reproductible* : chaque semaine produit sa matière — ce que
  le labo a fait, ce qui a cassé, ce qui a été construit.
- *Sauvegardes et partages* : le tuto « comment j'ai fait » se sauvegarde,
  l'erreur racontée se partage.
- *Monétisation dès le jour 1* : l'affiliation aux outils réellement
  utilisés et l'aimant à emails ne demandent aucun abonné (voir n°5).

---

## Prompt n°2 — la page « déjà établie » dès le premier jour

> Tu es un stratège de marque Instagram spécialisé dans les pages
> thématiques faceless. Ma niche est [NICHE].
> Crée-moi un plan complet de mise en place de la page : la formule exacte
> du nom d'utilisateur qui inspire de l'autorité, une bio de moins de 150
> caractères qui indique clairement aux visiteurs ce qu'ils vont obtenir
> et pourquoi ils devraient s'abonner, un système de noms pour les stories
> à la une, une stratégie de publications épinglées et un plan de contenu
> pour les neuf premières publications afin qu'une toute nouvelle page
> donne l'impression d'exister depuis plusieurs mois.
> Chaque élément doit être optimisé pour convertir la première impression,
> avec pour objectif de transformer un visiteur du profil en abonné en
> moins de 10 secondes.

**Nom d'utilisateur.** Formule : `marque` + `.` + `sujet en deux lettres`.
**@alluxe.ia** la respecte déjà : court, prononçable, et « ia » dit le
sujet avant même la bio.

**Nom affiché** (c'est le champ que la recherche Instagram lit) :
`alluxe.ia · je construis avec l'IA`

**Bio** (119 caractères) :

    Je construis des systèmes réels avec Claude et ChatGPT, sans être dev.
    Coulisses + tutos chaque semaine.
    👇 Commente KIT

Ce qu'elle dit en 10 secondes : qui (quelqu'un qui n'est pas développeur),
quoi (des systèmes réels, pas des astuces), ce qu'on y gagne (coulisses et
tutos), l'action (KIT).

**Stories à la une** — un mot chacune, même couverture (pastille menthe
« a. » sur fond sombre), dans cet ordre :
`Commencer` · `Le labo` · `L'appli` · `Tutos` · `Kit` · `Questions`

**Publications épinglées** (3) :
1. « Tout ce que j'ai construit seul avec l'IA » — la vue d'ensemble, celle
   qui fait s'abonner.
2. Le Reel du labo qui tourne 24 h/24 — la preuve en mouvement.
3. Le post du kit gratuit — celui qui récolte les emails.

**Les 9 premières publications** (la grille 3 × 3 qu'un visiteur voit
d'un coup) — dans `alluxe_ia/posts.json` :

| # | titre de couverture | pilier |
|---|---|---|
| 1 | Tout ce que j'ai construit seul avec l'IA, sans être développeur. | coulisses |
| 2 | Mon labo pose des questions à Claude et ChatGPT jour et nuit. | coulisses |
| 3 | 108 testées, 108 rejetées. Le bug n'était pas où je cherchais. | erreurs |
| 4 | Le prompt que j'utilise pour démarrer n'importe quel projet. | prompt de constructeur |
| 5 | Ce compte se publie tout seul. Voici la machine. | tuto |
| 6 | Le fichier qui empêche l'IA d'oublier mes décisions. | tuto |
| 7 | 656 tests verts. Avec le bug dedans. | erreurs |
| 8 | J'ai donné un terminal à mon agent IA. Voici ses 3 garde-fous. | coulisses |
| 9 | La méthode des 4 cases pour écrire n'importe quel prompt. | prompt de constructeur |

---

## Prompt n°3 — 30 jours de contenu

> Génère 30 idées de contenu Instagram conçues pour une page thématique
> faceless dans la niche [NICHE].
> Chaque idée doit être pensée pour maximiser les sauvegardes et les
> partages.
> Pour chaque idée, donne-moi : le hook, le format du contenu (carrousel,
> Reel ou publication statique), pourquoi elle fonctionne
> psychologiquement et l'heure idéale de publication.
> Privilégie les idées qui sont devenues virales dans des niches
> similaires au cours des 90 derniers jours.

**Limite honnête** : je n'ai pas accès aux chiffres des posts Instagram
d'autres comptes. Ce qui est « devenu viral ces 90 jours » est pris des
analyses publiées en 2026 : les cinq structures qui reviennent (point de
vue « POV », hook d'autorité, micro-histoire en boucle, révélation
avant/après, boucle ouverte) et la série « construit en public ».

**Heures** (audience française, études 2026) : mardi à jeudi **12 h–13 h**
(mercredi midi en tête), second créneau **19 h–21 h**. Notées M (midi) et
S (soir) ci-dessous. À remplacer par les vraies heures du compte après
30 jours de statistiques.

| # | hook | format | pourquoi ça marche | heure |
|---|---|---|---|---|
| 1 | Tout ce que j'ai construit seul avec l'IA, sans être développeur. | carrousel | autorité + « moi aussi je pourrais » | M |
| 2 | Mon labo pose des questions à Claude et ChatGPT jour et nuit. | Reel écran | curiosité, preuve en mouvement | S |
| 3 | 108 testées, 108 rejetées. | carrousel | boucle ouverte : on veut la cause | M |
| 4 | Le prompt que j'utilise pour démarrer n'importe quel projet. | carrousel | utilité immédiate → sauvegarde | M |
| 5 | Ce compte se publie tout seul. | Reel écran | méta : le post se prouve lui-même | S |
| 6 | Le fichier qui empêche l'IA d'oublier mes décisions. | carrousel | douleur connue de tous les utilisateurs | M |
| 7 | 656 tests verts. Avec le bug dedans. | carrousel | contradiction → arrêt du défilement | M |
| 8 | J'ai donné un terminal à mon agent IA. | Reel écran | peur + curiosité | S |
| 9 | La méthode des 4 cases. | carrousel | cadre réutilisable → sauvegarde | M |
| 10 | Claude contre ChatGPT : je leur pose la même question chaque nuit. | carrousel | comparaison, camp à choisir → commentaires | M |
| 11 | POV : tu demandes une appli à l'IA et tu ne sais pas coder. | Reel | identification | S |
| 12 | La phrase qui fait que l'IA arrête d'inventer. | carrousel | gain immédiat | M |
| 13 | Ce que l'IA m'a fait casser cette semaine. | carrousel (série hebdo) | rendez-vous, honnêteté rare | S |
| 14 | Mon agent a voulu supprimer un dossier. Voici pourquoi il n'a pas pu. | Reel | tension + résolution | S |
| 15 | 5 erreurs qui rendent tes réponses d'IA nulles. | carrousel | liste à garder | M |
| 16 | Avant / après : mon premier prompt et celui d'aujourd'hui. | carrousel | transformation | M |
| 17 | Comment j'explique un bug à l'IA pour qu'elle le trouve. | carrousel | tuto concret | M |
| 18 | Une journée de mon labo en 30 secondes. | Reel accéléré | satisfaction visuelle | S |
| 19 | « Vérifie que ça s'exécute, pas que c'est écrit. » | carrousel | leçon courte, citable → partage | M |
| 20 | Combien me coûte mon système IA par mois. | carrousel | transparence chiffrée (outils, pas trading) | M |
| 21 | J'ai demandé à l'IA de critiquer mon propre code. | Reel | autodérision | S |
| 22 | Les 3 outils que j'utilise tous les jours, et ceux que j'ai arrêtés. | carrousel | décision d'achat → sauvegarde | M |
| 23 | Ce que je fais quand l'IA se trompe avec assurance. | carrousel | méfiance partagée | M |
| 24 | Mon téléphone pilote un serveur. Sans écrire une ligne. | Reel écran | « c'est possible ? » | S |
| 25 | La checklist que je fais relire à l'IA avant chaque mise en ligne. | carrousel | modèle à copier | M |
| 26 | Construit en public, semaine 4 : le bilan sans filtre. | carrousel (série) | rendez-vous | S |
| 27 | Une appli sur mon téléphone, faite avec l'IA : visite guidée. | Reel écran | preuve | S |
| 28 | Le prompt pour transformer une idée floue en cahier des charges. | carrousel | utilité | M |
| 29 | Crée ton assistant IA perso en 5 minutes. | carrousel | gain rapide | M |
| 30 | 30 jours à construire en public : ce que j'ai appris. | carrousel | bilan, appel au kit | M |

---

## Prompt n°4 — décortiquer la formule des meilleurs concurrents

> Prends les 10 publications les plus performantes de ma niche — Reels ou
> carrousels ayant le plus fort engagement par rapport au nombre
> d'abonnés.
> Décompose chacune d'elles étape par étape : la première image ou le hook
> utilisé pour arrêter le scroll, la structure et le rythme du contenu, le
> pattern interrupt audio ou visuel, ainsi que le CTA ou le déclencheur
> d'engagement utilisé à la fin.
> Identifie les schémas reproductibles présents dans plusieurs
> publications — les structures qui rendent le contenu viral dans cette
> niche, quel que soit le créateur.
> Synthétise ensuite tes conclusions en un seul modèle de contenu
> réutilisable que je pourrai reproduire encore et encore sans jamais
> copier le contenu original de quelqu'un.

**Ce que je ne peux pas faire, et comment le débloquer.** Les chiffres
d'engagement des posts d'autres comptes ne sont pas accessibles d'ici :
l'API Instagram branchée sur le compte (connexion « Instagram ») ne
permet pas de lire les autres comptes ; il faut la connexion « Facebook »
et sa fonction `business_discovery`. Deux façons d'obtenir les 10 vrais
posts : **(a)** tu m'envoies 10 captures des posts les plus forts que tu
vois passer dans la niche, ou **(b)** on branche un jeton de Page Facebook
et le script lit lui-même les comptes concurrents.

**Ce que j'ai pu décortiquer pour de vrai : le post de @_mind__vision_
que tu m'as envoyé**, capturé 2 h après publication.

| élément | ce qu'il fait |
|---|---|
| chiffres | 196 j'aime, **111 commentaires**, 67 partages, 7 republications |
| hook | « Tu viens de récupérer 8 prompts » — la valeur est annoncée comme déjà acquise |
| structure | 1 slide par prompt, même gabarit : numéro en jaune, promesse en gros, prompt dans une fenêtre |
| rythme | 12 slides, la promesse change à chaque slide (niche → page → contenu → concurrents → argent → messages → 90 jours → système) |
| interruption visuelle | fond noir + un seul accent jaune ; la fenêtre de prompt « fait outil » |
| déclencheur | « Commente CLAUDE pour débloquer les 7 autres » **sur la slide du prompt n°1** — alors que les 8 sont déjà visibles |

**Le schéma** : 111 commentaires pour 196 j'aime, soit 57 % — c'est le
mot-clé qui fabrique l'engagement, pas le contenu. Placé tôt (slide 3),
il est vu par tous ceux qui commencent à glisser.

**Les schémas confirmés par les analyses 2026** (toutes niches) : hook
en moins de 1,5 seconde ; Reels de 7 à 15 secondes pour la complétion ;
cinq structures (POV, autorité, micro-histoire en boucle, révélation,
boucle ouverte) ; séries à rendez-vous ; second hook au milieu.

**Le modèle réutilisable alluxe.ia — « la preuve, puis la recette »** :

1. **Slide 1, le fait** : une chose réelle et surprenante, en 12 mots
   maximum (« 108 testées, 108 rejetées »). Jamais une promesse vague.
2. **Slide 2, l'enjeu** : pourquoi ça compte pour celui qui lit.
3. **Slide 3, le mot-clé** : « Commente KIT pour recevoir… », tôt.
4. **Slides 4 à 7, la recette** : ce que j'ai fait, étape par étape, avec
   un prompt copiable.
5. **Slide 8, la leçon** : une phrase citable (c'est elle qui se partage).
6. **Dernière slide, l'appel** : le mot-clé à nouveau.

Rien n'y est copié : le contenu vient des vrais systèmes du dépôt, que
personne d'autre n'a.

---

## Prompt n°5 — l'argent dès le premier jour

> Dresse la liste de toutes les méthodes de monétisation possibles pour
> une page Instagram thématique faceless, classées selon leur facilité de
> mise en place pour une toute nouvelle page.
> Pour chaque méthode, indique : les conditions minimales pour commencer,
> les efforts nécessaires pour la mettre en place, le niveau de croissance
> requis et la toute première action précise à réaliser cette semaine.
> Privilégie les méthodes qui fonctionnent sans montrer son visage, sans
> appels de vente et sans posséder son propre produit — notamment
> l'affiliation, les placements sponsorisés, la revente de newsletters et
> la recommandation de produits numériques.
> Identifie le chemin le plus rapide vers les premiers revenus et
> construis un plan d'activation simple à partir du premier jour.

| # | méthode | conditions minimales | effort | abonnés requis | première action cette semaine |
|---|---|---|---|---|---|
| 1 | **Affiliation aux outils réellement utilisés** | un compte sur l'outil, l'utiliser vraiment | faible | **0** | lister les outils du système qui ont un programme (repères 2026 : Make 30 % à vie, ElevenLabs 22 % sur 12 mois, Lovable jusqu'à 100 $ par abonné) et s'inscrire à ceux qu'on utilise |
| 2 | Recommandation de produits numériques d'autres créateurs | un produit qu'on a lu et trouvé bon | faible | 0 | en choisir un seul, le tester, demander son lien affilié |
| 3 | Recommandation payée de newsletters | une newsletter à soi (le kit récolte les emails) | moyen | ~500 emails | créer la newsletter et brancher le kit dessus |
| 4 | Placements sponsorisés (outils IA) | une audience engagée et une fiche média | moyen | ~5 000 | préparer la fiche média dès J1, la remplir à J60 |
| 5 | Produit à soi (guide « construire son premier système avec l'IA ») | une liste d'emails et un test « commente GUIDE » | élevé | ~1 000 | rien avant J45 — c'est la phase 2 du plan |
| 6 | Prestations (installer un système pour une petite entreprise) | du temps | élevé | 0 | **écartée** : le prompt exclut les appels de vente |

**Règle qui ne se négocie pas** : on ne recommande qu'un outil qu'on
utilise vraiment, et tout lien rémunéré porte « Publicité » ou
« Collaboration commerciale » (loi du 9 juin 2023). Aucun lien vers une
plateforme crypto, jamais.

**Le chemin le plus rapide** : affiliation (1) + kit gratuit qui récolte
les emails (3). Les deux marchent à 0 abonné.

**Plan d'activation**
- **J1** : s'inscrire aux programmes des outils réellement utilisés ; créer
  la page du kit (Gumroad ou Lemon Squeezy, gratuit) ; ManyChat sur KIT.
- **J2–J7** : chaque tuto cite l'outil utilisé, lien en message privé
  seulement à ceux qui le demandent, mention « Publicité ».
- **J30** : premier email à la liste — le récapitulatif du mois.
- **J45** : test « commente GUIDE » ; si ≥ 50 commentaires, le guide est
  écrit et vendu.

---

## Prompt n°6 — les messages privés qui convertissent

> Crée-moi une séquence complète d'automatisation des DM pour ma page
> Instagram thématique faceless dans la niche [NICHE].
> La séquence se déclenche lorsqu'un abonné commente un mot-clé sous ma
> publication.
> Conçois tout le parcours : la réponse automatique instantanée qui
> apporte de la valeur et suscite la curiosité, le message de suivi qui
> qualifie son intérêt, le message d'offre douce qui présente mon produit
> ou mon offre d'affiliation sans donner l'impression de vendre, puis le
> message de relance final pour les personnes qui ne répondent pas.
> Chaque message doit sembler humain, personnel et naturel — jamais comme
> celui d'un robot automatisé.
> Inclus le mot-clé déclencheur, le délai entre les messages et le texte
> exact de chaque étape.

**Mot-clé** : `KIT` (sur tous les posts). Repères 2026 : un commentaire
qui déclenche un message privé convertit autour de 15 à 25 %, et la
réponse en moins d'une minute fait toute la différence.

**Contrainte Meta, à respecter sinon le compte est limité** : après le
dernier message de la personne, on n'a que **24 heures** pour lui écrire
des messages automatiques. Toute la séquence tient donc dans 24 h ; si
elle répond, la fenêtre se rouvre.

**Réponse publique sous le commentaire** (instantanée, 3 variantes
tirées au hasard) : « Envoyé en privé 👀 » · « Regarde tes messages ! » ·
« C'est parti, je t'ai écrit. »

**Message 1 — immédiat**
> Salut {prénom} ! Voilà le kit : {lien}
> Dedans, les prompts que j'utilise vraiment pour construire mes
> systèmes, dans l'ordre où je m'en sers.
> Petite question pour savoir quoi t'envoyer ensuite : tu pars de zéro, ou
> tu as déjà construit quelque chose avec l'IA ?
> [Je pars de zéro] [J'ai déjà commencé]

**Message 2 — 3 heures après, selon la réponse** (qualification)
- *De zéro* :
  > Parfait, c'est exactement là où j'étais. Le premier prompt du kit
  > (le cahier des charges) est celui qui m'a fait gagner le plus de
  > temps. Tu voudrais construire quoi, toi ? Même une idée floue, ça
  > m'aide à te répondre.
- *Déjà commencé* :
  > Top ! Tu bloques plutôt sur quoi : l'IA qui oublie ce que tu lui as
  > dit, ou les bugs qu'elle ne trouve pas ? J'ai un post sur chacun.

**Message 3 — 20 heures après, seulement s'il a répondu** (offre douce)
> Je te partage l'outil que j'utilise pour {ce qu'il a dit}. C'est celui
> qui fait tourner mon labo depuis des semaines : {lien}
> (Publicité : c'est un lien partenaire, ça ne change rien pour toi et ça
> soutient le compte.) Si tu veux, je te dis comment je l'ai réglé.

**Message 4 — 23 heures après, s'il n'a jamais répondu** (relance
finale, dernière possibilité dans la fenêtre de 24 h)
> Je ne te relance plus après celui-là, promis 🙂 Si le kit t'a servi,
> la suite arrive chaque semaine sur le compte. Et si tu as une question
> sur ce que tu veux construire, réponds ici, je lis tout.

---

## Prompt n°7 — la feuille de route de 90 jours

> À partir de la niche [NICHE], construis une feuille de route complète de
> contenu et de croissance sur 90 jours pour une toute nouvelle page
> Instagram thématique faceless.
> Structure-la en trois phases : une phase d'établissement de l'autorité,
> une phase d'expansion du catalogue et une phase axée sur la viralité —
> avec, pour chacune, une fréquence hebdomadaire précise de publication,
> des proportions de formats de contenu et un objectif stratégique clair.
> Pour chaque phase, précise quels formats de contenu privilégier, quels
> sujets enchaîner pour maximiser la dynamique algorithmique et quelles
> publications utiliser comme tests d'engagement et de croissance.
> Présente le tout sous forme d'un plan d'exécution semaine par semaine,
> avec des indicateurs de performance clairs permettant de savoir quand
> passer à la phase suivante.

Les seuils ci-dessous sont des **objectifs de départ**, pas des
promesses : aucune donnée publique ne permet de prédire la croissance
d'un compte neuf (les estimations vont de 0,5 % à 8 % par mois).

**Phase 1 — l'autorité (semaines 1 à 4)**
- 5 posts/semaine : **3 carrousels, 2 Reels écran**.
- Objectif : qu'un visiteur comprenne en 10 s que le système est réel.
- Sujets enchaînés : vue d'ensemble → le labo → une erreur → un prompt →
  la publication auto (chaque post renvoie au précédent).
- Tests : deux couvertures différentes pour le même sujet, à une semaine
  d'écart.
- **Passer à la phase 2 quand** : taux de sauvegarde moyen ≥ 2 % de la
  portée **et** 100 personnes inscrites au kit.

**Phase 2 — le catalogue (semaines 5 à 8)**
- 6 posts/semaine : **3 Reels, 3 carrousels**, dont une série à rendez-vous
  « Construit en public, semaine N » (le dimanche soir).
- Objectif : que le profil devienne une bibliothèque qu'on parcourt.
- Sujets : un pilier par jour, en rotation (coulisses, tuto, prompt,
  erreur).
- Tests : test « commente GUIDE » à J45 ; Reels de 10 s contre 25 s.
- **Passer à la phase 3 quand** : un Reel dépasse 10 fois le nombre
  d'abonnés en vues **et** 300 inscrits au kit.

**Phase 3 — la viralité (semaines 9 à 13)**
- 7 posts/semaine : **4 Reels, 2 carrousels, 1 collaboration**.
- Objectif : toucher des gens qui ne suivent pas encore.
- Sujets : refaire en Reel les 5 carrousels les plus sauvegardés ; une
  collaboration par semaine avec un compte de taille proche.
- Tests : Reels « à l'essai » (montrés aux non-abonnés d'abord) pour les
  hooks ; deux versions du même Reel.
- **Bilan à J90** : garder ce qui a les meilleures sauvegardes et
  partages, couper le reste.

| semaine | à publier | indicateur à regarder |
|---|---|---|
| 1 | les 9 posts de lancement (grille), sur 5 jours | visites du profil → abonnés |
| 2 | 3 carrousels + 2 Reels (labo, publication auto) | sauvegardes par post |
| 3 | idem + 1er « ce que l'IA m'a fait casser » | commentaires KIT |
| 4 | idem + bilan du mois | **seuil phase 2** |
| 5 | lancement de la série « Construit en public » | retour des mêmes personnes |
| 6 | 3 Reels + 3 carrousels | vues des Reels |
| 7 | test GUIDE (J45) | nombre de commentaires GUIDE |
| 8 | idem | **seuil phase 3** |
| 9 | 1re collaboration ; 4 Reels | abonnés venus de la collaboration |
| 10 | Reels refaits depuis les meilleurs carrousels | partages |
| 11 | Reels à l'essai | taux de complétion |
| 12 | idem | portée hors abonnés |
| 13 | bilan à J90 | tout |

---

## Prompt n°8 — le système qui tourne sans toi

> Je gère une page Instagram thématique faceless dans la niche [NICHE] et
> je veux la systématiser afin qu'elle ne me demande pas plus de
> 30 minutes par jour.
> Construis-moi un système opérationnel complet : un processus
> hebdomadaire de création de contenu en lot, un protocole de
> planification et de publication, une procédure simple qu'un assistant
> virtuel peu coûteux pourrait suivre pour gérer 80 % des tâches
> quotidiennes, ainsi qu'une checklist de contrôle qualité pour garantir
> qu'aucun contenu ne soit publié s'il ne respecte pas mes standards.
> Indique également quels outils utiliser pour la planification, la
> rédaction des légendes et l'analyse des performances.
> L'objectif est de me retirer des opérations quotidiennes tout en
> permettant à la page de continuer à croître et à générer des revenus.

**La particularité ici : la plupart des briques existent déjà dans le
dépôt.**

**Le lot de la semaine (dimanche, 1 h 30)**
1. 15 min — noter en vrac ce qui s'est passé dans la semaine (le labo,
   l'appli, ce qui a cassé). C'est la matière première.
2. 30 min — une session Claude écrit les posts de la semaine dans
   `alluxe_ia/posts.json` à partir de ces notes.
3. 15 min — `python3 ops/alluxe_ia.py rendre`, relire les images.
4. 30 min — filmer les 2 à 3 écrans des Reels.

**Planification et publication**
- Carrousels : `systemd/alluxe-ia-publication.timer`, un post par jour à
  12 h 30 (prêt, à installer après la bascule du compte).
- Reels : `publier_reel` existe déjà dans `ops/instagram.py` ; TikTok :
  `ops/tiktok.py` (toujours déclaré « contenu IA »).
- Messages privés : ManyChat (séquence du prompt n°6).

**La procédure de l'assistant (20 min/jour, 80 % des tâches)**
1. Répondre aux commentaires qui ne sont pas « KIT » avec la banque de
   réponses (un fichier de 20 réponses types, à tenir à jour).
2. Lire les messages privés que ManyChat n'a pas traités ; ne jamais
   promettre un résultat, ne jamais parler de trading.
3. Noter chaque jour dans un tableau : abonnés, portée, sauvegardes du
   dernier post, inscrits au kit.
4. Signaler à l'opérateur : toute question technique, toute proposition
   de marque, tout message agressif.

**La checklist — un post ne part pas si une case n'est pas cochée**
- [ ] Chaque prompt a été testé pour de vrai.
- [ ] Aucune clé, aucun mot de passe, aucune donnée personnelle à l'écran.
- [ ] Aucun résultat de trading, gain, ni lien vers une plateforme crypto.
- [ ] « Publicité » si un lien rémunéré est cité ; « Image virtuelle » si
      une image générée sert un contenu commercial.
- [ ] La couverture se lit en vignette (12 mots maximum).
- [ ] Le mot-clé KIT est sur la slide 3 et sur la dernière.
- [ ] Orthographe relue.
- [ ] Ce qui est montré est vrai (pas de « résultat » inventé).

**Les outils**
- Planification : le minuteur du dépôt ; en secours, Meta Business Suite
  (gratuit).
- Légendes : Claude, à partir des notes de la semaine.
- Analyse : les statistiques Instagram lues par l'API (point 12 de
  `docs/ALLUXE_IA.md`, à construire), et les chiffres ManyChat.

## Sources

- https://www.reelry.app/best/best-faceless-instagram-niches
- https://sellfy.com/blog/instagram-niches/
- https://creatordb.app/creatorstats/build-in-public/
- https://www.bizkol.ai/blog/build-in-public-marketing
- https://foundertrace.fr/vibe-coding/
- https://www.jedha.co/formation-ia/les-10-influenceurs-ia-a-suivre-en-2025
- https://creatorflow.so/blog/viral-instagram-reels-using-ai/
- https://postiz.com/blog/instagram-viral-triggers-2026
- https://www.socialpilot.co/fr/insights/best-time-to-post-on-instagram
- https://adaptlypost.com/fr/blog/best-time-to-post-instagram
- https://oakgen.ai/blog/best-ai-affiliate-programs-2026
- https://www.way2earning.com/2026/01/elevenlabs-affiliate-program/
- https://smartreply.io/blog/instagram-comment-dm-automation-guide
- https://www.inro.social/tools/instagram-follower-growth-calculator
- https://www.lafinancepourtous.com/2026/01/22/finfluenceurs-recommandations-de-lamf-et-de-lesma-pour-une-promotion-responsable/
