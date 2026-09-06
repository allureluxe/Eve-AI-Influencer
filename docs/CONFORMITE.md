# Conformité — ce qui rend le compte viable

Un compte virtuel non déclaré finit supprimé, démonétisé, ou les deux. Les
règles ci-dessous sont appliquées **par le code**, dans `eve/safety/policy.py`,
et testées dans `tests/test_safety.py`.

## Divulgation IA — obligatoire

| Cadre | Exigence |
|---|---|
| FTC (États-Unis) | Divulgation claire et visible de tout contenu ou partenariat sponsorisé |
| AI Act, article 50 (UE) | Le contenu généré par IA doit être identifiable comme tel |
| Meta | Label « AI info » ; détection automatique et étiquetage d'office |
| TikTok | Label AIGC obligatoire ; champ `is_aigc` dans l'API |

Ce que fait l'agent :

- ajoute la mention `Contenu généré par IA · AI-generated content` et les
  hashtags de divulgation à **chaque** légende ;
- **refuse de publier** une légende sans mention (`review_post` bloque) ;
- envoie `is_aigc: true` à l'API TikTok ;
- inscrit la mention dans la bio (`disclosure.bio_line`) et dans le media kit.

À faire manuellement une fois : activer le label « AI info » sur le compte
Instagram et le commutateur AIGC dans l'application TikTok.

## Intégrité financière — le cœur du dispositif

Eve parle d'un système de trading. Elle n'existe pas, elle n'a aucun revenu,
et rien n'est vendu autour de ce système. Trois règles sont appliquées par le
code, pas par la bonne volonté du rédacteur.

### 1. Le train de vie ne prouve rien

`LIFESTYLE_ATTRIBUTION_PATTERNS` bloque toute légende reliant le décor d'Eve à
un gain : « grâce à mon robot », « mon système m'a payé », « je gagne 8000 »,
« ma vie a changé grâce à ». C'est exactement la construction qui transforme
un compte lifestyle en faux témoignage financier.

### 2. Aucun chiffre inventé

Les performances viennent uniquement de `data/trading/results.json`. Le
générateur n'écrit aucun nombre lui-même. Sans fichier, le pilier `work`
produit du contenu de méthode, sans aucun chiffre. Voir
[RESULTATS-TRADING.md](RESULTATS-TRADING.md).

### 3. Un chiffre ne sort jamais seul

Toute légende contenant un pourcentage de performance doit citer le drawdown
**et** rappeler « résultats passés / pas un conseil ». Sinon la publication est
bloquée. Le drawdown maximal est également obligatoire dans le fichier de
données : un rendement sans son risque est trompeur même quand il est exact.

### Sollicitation financière — interdite

`FINANCIAL_SOLICITATION_PATTERNS` bloque « rejoins mon canal », « DM pour
recevoir le robot », « places limitées », « capital garanti », « copie mes
trades ». Rien n'est vendu, loué, copié ni recruté autour du système.

Un avertissement de risque est ajouté à tout contenu du pilier `work` :
*rien de ceci n'est un conseil en investissement, le trading comporte un
risque de perte en capital.*

## Contenu démonétisant — bloqué en amont

Les prompts visuels contenant `lingerie`, `suggestive`, `nsfw` et assimilés
sont refusés avant même la génération d'image. Deux raisons :

1. Instagram et TikTok restreignent la portée du contenu suggestif et
   l'excluent de la monétisation — un compte « borderline » ne touche ni les
   programmes créateurs ni les deals de marque.
2. Les partenariats sportifs sérieux ne signent pas avec ce type de compte.

La garde-robe du character bible ne contient que des tenues couvrantes et
élégantes, ce qui est aussi la norme des partenariats mode.

## Personnage adulte — verrouillé

`identity.age` doit être ≥ 18 et `identity.is_ai` doit rester `true` :
`check_persona()` bloque le démarrage sinon. Les termes visuels évoquant un
mineur sont dans la liste d'interdits durs.

## Ressemblance à une personne réelle — interdite

Aucun prompt ne doit viser la ressemblance à une personne existante
(`celebrity`, `lookalike of`, `deepfake` sont bloqués). Un visage généré doit
rester un visage synthétique : le droit à l'image d'une personne réelle
s'applique même à une imitation générée.

## Publication par API officielle uniquement

`instagrapi`, `TikTokApi` et les automatisations de navigateur violent les CGU
des deux plateformes et entraînent la suspension du compte. Elles ont été
retirées de ce projet au profit de l'API Graph et de la Content Posting API.

## Ce que l'agent ne fait pas, volontairement

- Il ne répond pas aux commentaires ni aux messages privés (interaction humaine).
- Il n'achète pas d'abonnés ni d'engagement.
- Il ne publie aucun conseil en investissement, ni personnalisé ni général.
- Il ne prétend jamais qu'Eve est une personne réelle, en aucun contexte.
