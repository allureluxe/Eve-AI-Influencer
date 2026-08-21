# Eve — influenceuse fitness IA, autonome et monétisable

Agent complet qui crée, produit, contrôle, publie et optimise le contenu d'une
créatrice virtuelle sur **TikTok** et **Instagram**. Conçu pour démarrer à
**coût zéro** : les providers par défaut (images, voix, montage, rédaction)
sont tous gratuits.

```
                planifier ──► produire ──► contrôler ──► publier
                    ▲                                       │
                    └────────── optimiser ◄── mesurer ◄──────┘
```

## Le personnage

**Eve Carter**, 26 ans, Miami (Floride). Blonde, 1 m 60, yeux noisette,
silhouette athlétique. Coach sportive : séances courtes, technique de
mouvement, nutrition simple, mindset. Public visé : femmes 18-34 débutantes à
intermédiaires.

Tout le personnage tient dans un seul fichier — [`eve/persona/eve.yaml`](eve/persona/eve.yaml) —
qui pilote la génération d'images, le ton des textes et les garde-fous. Modifie
ce fichier, tout le reste suit.

## Démarrage en 5 minutes

```bash
pip install -r requirements.txt
sudo apt install ffmpeg          # macOS : brew install ffmpeg
cp .env.example .env

python -m eve.cli doctor         # diagnostic de l'installation
python -m eve.cli preview        # un script de vidéo, sans rien générer
python -m eve.cli plan --days 7  # calendrier éditorial de la semaine
python -m eve.cli produce --limit 1   # images + voix + sous-titres + MP4
python -m eve.cli run            # cycle complet (en dry-run, rien n'est publié)
```

Aucune clé d'API n'est nécessaire pour ces commandes. La vidéo produite arrive
dans `output/videos/<id>/`.

## Ce que fait l'agent

| Étape | Module | Détail |
|---|---|---|
| Planifier | `content/planner.py` | Calendrier pondéré par pilier, sans répétition |
| Écrire | `content/scripts.py` | Hook, plans minutés, textes à l'écran, appel à l'action |
| Illustrer | `media/images.py` | Un prompt par plan, verrou d'identité + seed fixe |
| Sonoriser | `media/voice.py` | Voix off neuronale gratuite (`edge-tts`) |
| Monter | `media/video.py` | ffmpeg : Ken Burns, sous-titres incrustés, 9:16 |
| Contrôler | `safety/policy.py` | Divulgation IA, allégations santé, contenu démonétisant |
| Publier | `publishing/` | API officielles Instagram Graph et TikTok Content Posting |
| Mesurer | `analytics/collector.py` | Vues, engagement, normalisés entre plateformes |
| Optimiser | `analytics/optimizer.py` | Ré-pondère les piliers selon les résultats réels |
| Monétiser | `monetization/` | Affiliation, programme PDF, media kit, suivi des revenus |

## Deux verrous de sécurité, actifs par défaut

```bash
DRY_RUN=1                # rien n'est publié : tout est produit et rapporté
REQUIRE_HUMAN_REVIEW=1   # chaque contenu attend `eve approve` avant publication
```

Passe-les à `0` seulement quand tu as vérifié plusieurs vidéos de bout en bout.

## Le rendu ultra-réaliste

Trois leviers cumulés, détaillés dans [docs/RENDU-REALISTE.md](docs/RENDU-REALISTE.md) :

1. **Verrou d'identité** — `appearance.identity_lock` est injecté en tête de
   *chaque* prompt : c'est ce qui garde le même visage d'un post à l'autre.
2. **Seed fixe** — `PERSONA_SEED=774921`, dérivé par plan pour varier la pose
   sans changer la personne.
3. **Style photographique + anti-prompt** — objectif, lumière, grain, texture
   de peau d'un côté ; « 3d render, plastic skin, airbrushed » interdits de
   l'autre. C'est l'anti-prompt qui casse le rendu « IA ».

Pour le niveau supérieur (visage strictement identique), passe à ComfyUI en
local avec une LoRA de visage : `IMAGE_PROVIDER=comfyui`.

## Monétisation

Détail complet et chiffré dans [docs/MONETISATION.md](docs/MONETISATION.md).
Résumé de l'ordre à suivre :

1. **Produit numérique** (jour 1) — `python -m eve.cli product` génère un
   programme 4 semaines vendable et un media kit. Aucun seuil d'abonnés requis.
2. **Affiliation** (dès les premiers abonnés) — matériel de sport, liens
   suivis en UTM, mention `#ad` ajoutée automatiquement.
3. **Programmes plateformes** — TikTok Creator Rewards à 10 000 abonnés et
   100 000 vues sur 30 jours, vidéos de plus d'une minute.
4. **Partenariats de marque** — le vrai revenu ; le media kit annonce
   explicitement la nature IA du compte, c'est ce que les marques exigent.

```bash
python -m eve.cli revenue --followers 12000 --views 400000
```

## Conformité — non négociable

Une créatrice virtuelle **doit** être déclarée comme telle : FTC aux
États-Unis, article 50 de l'AI Act en Europe, règles AIGC de Meta et de TikTok.
Le module `safety/policy.py` refuse de publier une légende sans mention IA,
avec une allégation santé, une promesse de résultat chiffrée ou un visuel
suggestif. Ce n'est pas décoratif : c'est ce qui garde le compte monétisable.
Voir [docs/CONFORMITE.md](docs/CONFORMITE.md).

Les publications passent par les **API officielles**. Les bibliothèques
d'automatisation non officielles (`instagrapi`, `TikTokApi`) violent les CGU et
font bannir le compte — elles ont été retirées du projet.

## Automatisation

- En local : `python -m eve.cli loop --hours 12`
- Sur serveur : `0 6,18 * * * cd /chemin/eve && python -m eve.cli run`
- Sur GitHub Actions : [`.github/workflows/eve-daily.yml`](.github/workflows/eve-daily.yml)
  (gratuit sur dépôt public)

## Tests

```bash
python -m pytest tests -q      # 38 tests, dont toute la politique de conformité
```

## Documentation

- [docs/SETUP.md](docs/SETUP.md) — créer les comptes et obtenir les jetons API
- [docs/RENDU-REALISTE.md](docs/RENDU-REALISTE.md) — qualité d'image et cohérence du visage
- [docs/MONETISATION.md](docs/MONETISATION.md) — sources de revenus, seuils, chiffres
- [docs/CONFORMITE.md](docs/CONFORMITE.md) — obligations légales et règles plateformes
