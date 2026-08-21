# Obtenir un rendu ultra-réaliste et un visage constant

Deux problèmes distincts, deux solutions distinctes.

## Problème 1 — « ça fait IA »

Le rendu plastique vient presque toujours de l'absence d'anti-prompt et d'un
style photographique trop vague. Le projet applique automatiquement, dans
`eve/persona/persona.py` :

**Style positif** — `photorealistic candid photograph, shot on Sony A7 IV with
35mm f/1.8 lens, natural daylight, shallow depth of field, realistic skin
texture with visible pores, subtle skin imperfections, natural film grain…`

**Anti-prompt** — `3d render, cgi, plastic skin, airbrushed, waxy, doll-like,
over-smoothed skin, oversaturated, deformed hands…`

Ce qui aide le plus, dans l'ordre :

1. **La texture de peau** — « visible pores », « subtle skin imperfections ».
   Une peau parfaite est le signal n°1 d'une image générée.
2. **Un objectif nommé** — 35 mm ou 50 mm, ouverture réelle. Le modèle applique
   la profondeur de champ correspondante.
3. **Une lumière imparfaite** — « natural daylight », « golden hour »,
   « window light » plutôt que « studio lighting perfect ».
4. **Le grain** — « natural film grain » casse le lissé numérique.
5. **Le cadrage** — « candid », « mid-movement » : une pose figée face caméra
   trahit la génération.

## Problème 2 — le visage change d'un post à l'autre

C'est le vrai obstacle d'une influenceuse virtuelle. Trois niveaux, du plus
simple au plus fiable.

### Niveau 1 — verrou d'identité + seed (fourni, gratuit)

`appearance.identity_lock` décrit le visage en une phrase dense, injectée en
tête de **chaque** prompt, et `PERSONA_SEED` fixe la graine. La variation par
plan (`shot_seed`) reste faible pour changer la pose sans changer la personne.

Résultat : cohérent à ~70-80 %. Suffisant pour démarrer, pas pour un compte
qui grossit.

### Niveau 2 — ComfyUI local + IP-Adapter FaceID (gratuit, GPU requis)

1. Installer [ComfyUI](https://github.com/comfyanonymous/ComfyUI).
2. Générer 20 à 30 images d'Eve au niveau 1, garder les 8 meilleures où le
   visage est le plus proche.
3. Ajouter un nœud **IP-Adapter FaceID** alimenté par ces images de référence
   (à déposer dans `assets/reference/`).
4. Exporter le workflow au format API dans `assets/workflows/portrait.json`,
   avec les jetons `%PROMPT%`, `%NEGATIVE%`, `%SEED%`, `%WIDTH%`, `%HEIGHT%`.
5. `IMAGE_PROVIDER=comfyui`

Cohérence : ~90 %.

### Niveau 3 — LoRA de visage entraînée (gratuit, quelques heures de GPU)

Entraîner une LoRA sur 25-40 images validées d'Eve (Kohya_ss ou l'entraîneur
LoRA de ComfyUI), puis la charger dans le workflow. C'est ce qu'utilisent les
comptes virtuels professionnels.

Cohérence : ~98 %, y compris de profil et en mouvement.

## De l'image fixe à la vidéo

Le projet anime des images fixes (Ken Burns + sous-titres) : c'est gratuit,
rapide, et parfaitement adapté au format « conseil face caméra » où le texte
porte le message.

Pour de la vraie vidéo, deux options à brancher sur `media/video.py` :

- **AnimateDiff / LTX-Video** dans ComfyUI — gratuit, local, GPU requis.
- **Kling, Runway, Hailuo** — payants, meilleurs mouvements humains.

Pour des démonstrations d'exercices, l'image animée reste souvent plus lisible
qu'une vidéo générée : un mouvement mal rendu se voit immédiatement sur un
contenu sportif.

## Format et cadrage

| Réglage | Valeur | Pourquoi |
|---|---|---|
| Ratio | 9:16 (1080×1920) | Plein écran TikTok et Reels |
| Durée | 20 à 60 s | > 60 s requis pour TikTok Creator Rewards |
| Sous-titres | incrustés | La majorité des vues sont sans le son |
| Zone sûre | 15 % en haut, 20 % en bas | L'interface recouvre les bords |

Les sous-titres générés respectent déjà ces marges (`media/subtitles.py`).
