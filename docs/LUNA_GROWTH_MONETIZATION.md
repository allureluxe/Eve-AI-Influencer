# Luna — plan croissance + monetisation

## Objectif

Presence multi-formats : Instagram Feed photo, Stories, Highlights, Reels ;
TikTok videos courtes et videos originales longues ; partenariats restaurants,
bars, cafes, hotels, mode, lieux et tourisme.

Il n'y a aucune garantie de nombre d'abonnes ou de revenus. Le systeme mesure
les resultats et adapte ensuite les formats.

## Ligne editoriale

Luna est une influenceuse IA fictive adulte.

1. lieux instagrammables
2. restaurants / bars / cafes
3. vie etudiante + finance
4. mode du quotidien
5. sorties et voyages
6. coulisses de creation IA

Le lieu reste un sujet, pas seulement un decor : le contenu doit avoir une
raison d'etre sauvegarde, partage ou commente.

## Cadence initiale

Le planificateur ops/planifier_luna.py maintient une fenetre de 36 heures :
Stories quotidiennes, Feed photo plusieurs fois par semaine, Reels plusieurs
fois par semaine, TikTok courts pour la decouverte, et TikTok 60-90 secondes
pour les formats compatibles avec Creator Rewards.

Les horaires sont des points de depart. Ils ne promettent pas de meilleures
performances qu'un autre horaire.

## Monétisation

### Instagram

L'eligibilite aux outils comme Gifts ou Subscriptions est verifiee dans le
tableau de bord du compte.

Les Stories portent un highlight_name pour les collections Metz, Restaurants,
Bars, Cafes, Voyages, Looks et Luna. La publication Story est automatisee ;
l'ajout a un Highlight est suivi comme pending_manual car aucune API officielle
utilisee par ce depot ne garantit cette operation.

### TikTok

Le compte cible doit rester personnel pour viser Creator Rewards. Le programme
demande actuellement notamment 10 000 followers, 100 000 vues video sur 30 jours,
des videos originales de haute qualite d'au moins une minute et une region
participante.

Le format tiktok_rewards est donc separe des contenus sponsorises.

TikTok One et TikTok Series sont suivis comme voies supplementaires de
partenariats et de contenu premium lorsque le compte est eligible.

## Transparence IA

Le pipeline conserve ai_disclosure=true. TikTok recoit is_aigc=true pour les
publications video directes. Meta peut etiqueter les contenus IA et exige la
divulgation pour les contenus organiques photorealistes generes ou modifies
numeriquement.

## Regles anti-spam

- pas de repost avec watermark
- pas de copie d'un autre createur
- variation des lieux, tenues, poses, hooks et CTA
- un objectif de monetisation par job
- publication uniquement avec publish=true
- contenus sponsorises distincts des contenus visant Creator Rewards

## Boucle d'apprentissage

Le prochain niveau doit ingester vues, likes, commentaires, partages,
sauvegardes, duree de visionnage, taux de completion, nouveaux followers et
revenu estime par job, puis recalculer les proportions des piliers, les horaires,
la longueur et les hooks a partir des donnees.