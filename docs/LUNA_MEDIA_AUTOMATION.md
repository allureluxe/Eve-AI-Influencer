# Luna — pipeline média automatisé (plan de reprise)

> Document de reprise préparé le 26 septembre 2026.
>
> Objectif : permettre à Claude de rester l'orchestrateur, tout en déléguant la génération réelle des photos et vidéos à des services/API dédiés, puis de remettre automatiquement les médias à la chaîne de publication.

## Architecture cible

```
Claude
  │
  │ 1. choisit le sujet + écrit le prompt
  ▼
Supabase / table luna_publications
  │
  │ 2. job en_attente
  ▼
Media Worker sur le VPS
  │
  ├── photo ──► API image
  │              │
  │              └── référence permanente de Luna
  │
  └── vidéo ─► API image→vidéo
                 │
                 └── photo de départ / référence Luna
  │
  │ 3. stockage du résultat
  ▼
Supabase Storage
  │
  │ 4. statut = terminee
  ▼
Claude / orchestrateur
  │
  │ 5. récupère média + légende + métadonnées
  ▼
Publication officielle
```

## Ce qui existe déjà dans le dépôt

Le dépôt possède déjà une file `luna_publications`. L'application insère une demande avec le statut `en_attente`, puis `ops/executer_luna.py` réclame la plus ancienne demande et la traite.

Les champs existants sont notamment :
- `demande`
- `statut`
- `legende`
- `scene_prompt`
- `chemin_photo`
- `chemin_voix`
- `chemin_video`
- `erreurs`

Le stockage du bucket privé `luna` et les URL signées existent déjà.

Références :
- `supabase/migrations/20260916070000_luna.sql`
- `ops/executer_luna.py`
- `app-alluxe-bot/src/services/luna.ts`

## Limite actuelle à corriger

Le pipeline `luna/alluxe_v2.py` produit actuellement la vidéo avec FFmpeg à partir de la photo et de la voix (effet Ken Burns / repli statique). Ce n'est pas une vraie génération image→vidéo.

Le futur worker doit donc remplacer cette étape par un fournisseur vidéo dédié.

## Contrat de travail conseillé

Claude doit déposer une demande structurée, idéalement sous forme JSON sérialisée dans `demande` ou dans de nouvelles colonnes dédiées.

Exemple photo :

```json
{
  "type": "photo",
  "prompt": "A candid phone photo of Luna walking near the Porte des Allemands in Metz...",
  "reference": "luna/reference.jpg",
  "aspect_ratio": "4:5",
  "quality": "high",
  "publish": true
}
```

Exemple vidéo :

```json
{
  "type": "video",
  "prompt": "She turns gently, resumes walking away on the paved quay...",
  "reference": "photo_generated_for_this_job",
  "aspect_ratio": "9:16",
  "duration_seconds": 10,
  "publish": true
}
```

## Colonnes possibles à ajouter

Ne pas les ajouter tant que l'implémentation n'a pas commencé. Le besoin identifié est :

- `media_type`
- `reference_path`
- `aspect_ratio`
- `duration_seconds`
- `provider`
- `provider_task_id`
- `generation_status`
- `output_url`
- `publish_requested`
- `published_at`

On peut aussi conserver les champs actuels pour rétrocompatibilité.

## Référence du personnage

La constance du visage est la priorité.

Le pipeline doit toujours pouvoir utiliser une référence permanente de Luna, actuellement ancrée dans :

`docs/luna/reference.jpg`

et décrite/codée dans :

`luna/persona.py`

La référence doit être envoyée au moteur image quand le fournisseur le permet. Pour une vidéo, la photo finale peut devenir le premier frame exact quand on veut animer cette photo telle quelle.

## Règle de sélection du fournisseur

### Photos
Le worker choisit un moteur image selon :
1. disponibilité de la clé / quota ;
2. support des images de référence ;
3. ratio demandé ;
4. qualité demandée.

L'API OpenAI est une option cible pour la génération/édition d'images.

### Vidéos
Le worker choisit un moteur image→vidéo selon :
1. disponibilité du compte ;
2. coût/crédits ;
3. durée demandée ;
4. résolution ;
5. présence d'une image de départ.

Runway et OpenArt sont les connecteurs/services actuellement disponibles dans ChatGPT, mais le worker du VPS doit utiliser une intégration API/service réellement accessible depuis le serveur.

## Gestion asynchrone

Une génération vidéo peut durer plus longtemps que le cycle cron actuel.

Le worker doit donc :
1. réclamer le job ;
2. soumettre la génération ;
3. enregistrer `provider_task_id` ;
4. laisser le job en `en_cours` ;
5. sonder l'état au passage suivant ;
6. enregistrer le média dès que la tâche est terminée ;
7. passer à `terminee` ou `echec`.

Ne pas lancer une nouvelle génération à chaque passage tant que `provider_task_id` est encore actif.

## Publication

Le module `ops/instagram.py` existe déjà et utilise l'API officielle Instagram pour créer puis publier un média.

La chaîne cible est donc :

`generation terminee` → contrôle minimum → `publish_requested` → publication officielle → `published_at`

La publication ne doit jamais être déclenchée simplement parce qu'un fichier existe : le job doit porter une intention explicite de publication.

## Sécurité

Ne jamais mettre :
- clé API ;
- token Instagram ;
- clé Supabase service-role ;
- secret Runway/OpenArt/OpenAI ;

dans Git.

Les secrets restent dans `.env` ou dans le gestionnaire de secrets du serveur.

## Migration progressive

Ne pas supprimer immédiatement le pipeline actuel.

Étape 1 : ajouter un adaptateur de fournisseur image.

Étape 2 : ajouter un adaptateur vidéo asynchrone.

Étape 3 : garder FFmpeg comme repli si aucune vidéo générative n'est disponible.

Étape 4 : brancher la récupération du résultat dans `ops/executer_luna.py`.

Étape 5 : brancher la publication automatique une fois le média marqué comme prêt.

Étape 6 : ajouter des tests de reprise après crash, quota épuisé, tâche distante encore en cours et échec fournisseur.

## État au 26 septembre

- La file Supabase existe.
- Le worker cron existe.
- La génération texte existe.
- La génération image existe sous une abstraction fournisseur.
- La génération vidéo actuelle est locale/FFmpeg.
- La publication Instagram officielle existe.
- Il faut maintenant construire le vrai pont **Claude → Media Worker → API image/vidéo → Supabase → publication**.

## Première tâche de la prochaine session

Avant toute modification fonctionnelle :
1. relire `ops/executer_luna.py`, `luna/alluxe_v2.py`, `luna/moteurs.py`, `luna/persona.py`, `luna/photos.py`;
2. choisir le contrat exact de `luna_publications`;
3. implémenter l'adaptateur image;
4. implémenter l'adaptateur vidéo asynchrone;
5. tester en mode brouillon/non-publication;
6. seulement ensuite activer la publication automatique.


## Implémentation livrée le 26 septembre 2026

Le contrat décrit ci-dessus est maintenant branché dans le dépôt :

- migration Supabase : `supabase/migrations/20260926033000_luna_media_jobs.sql` ;
- adaptateurs : `luna/media.py` ;
- worker : `ops/executer_luna.py` accepte désormais les jobs structurés photo/video et sonde les vidéos asynchrones ;
- vidéo : adaptateur Runway image→video avec task id persistant ;
- publication : `ops/instagram.py` sait publier une vidéo comme Reel ;
- agent Alluxe : outils `creer_media_luna` et `etat_media_luna` ;
- CLI Claude Code : `ops/claude_media.py` ;
- photos Claude : nouveau format natif 3:4 ; vidéos : 9:16 par défaut ;
- les workers cron sont verrouillés pour ne pas se chevaucher.

### Contrat à utiliser

Claude appelle `creer_media_luna` avec un prompt complet et une légende. Pour une photo :

```json
{"type":"photo","prompt":"...","caption":"...","aspect_ratio":"3:4","publish":true}
```

Pour une vidéo :

```json
{"type":"video","prompt":"...","caption":"...","aspect_ratio":"9:16","duration_seconds":10,"publish":true}
```

`publish=true` est l'autorisation explicite ; le worker ne publie pas un job qui ne la porte pas.

### À faire sur le VPS

Ajouter la vraie clé du fournisseur vidéo dans `.env` :

```
RUNWAYML_API_SECRET=...
LUNA_VIDEO_MODEL=gen4.5
LUNA_VIDEO_RESOLUTION=720p
```

Puis appliquer la migration Supabase. Tant que la migration et la clé vidéo ne sont pas installées, les nouveaux jobs ne doivent pas être considérés comme opérationnels.
