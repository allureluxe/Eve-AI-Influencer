# Eve — créatrice lifestyle IA, autonome

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
silhouette élégante. Créatrice lifestyle : style et matières, art de vivre,
voyages, et les coulisses d'un travail sur les systèmes de trading
automatisés — présenté comme un métier technique, jamais comme une promesse
d'argent.

Le pilier **mode** est le deuxième en volume, délibérément : c'est lui qui
construit l'audience du futur site de vêtements.

Tout le personnage tient dans un seul fichier — [`eve/persona/eve.yaml`](eve/persona/eve.yaml) —
qui pilote la génération d'images, le ton des textes et les garde-fous. Modifie
ce fichier, tout le reste suit.

## Démarrer

```bash
python3 demarrer.py
```

Une seule commande : elle installe, vérifie, et produit une première vidéo.
Rien n'est publié. Le guide pas-à-pas tient sur une page :
**[DEMARRAGE.md](DEMARRAGE.md)**.

Ensuite, une seule commande à retenir :

```bash
python3 -m eve.cli go --videos 3     # produire le contenu suivant
```

## Sous le capot

<details>
<summary>Les dix modules que <code>go</code> enchaîne</summary>

| Étape | Module | Détail |
|---|---|---|
| Planifier | `content/planner.py` | Calendrier pondéré par pilier, sans répétition |
| Chiffrer | `content/trading.py` | Résultats réels uniquement, jamais générés |
| Écrire | `content/scripts.py` | Hook, plans minutés, textes à l'écran, appel à l'action |
| Illustrer | `media/images.py` | Un prompt par plan, verrou d'identité + seed fixe |
| Sonoriser | `media/voice.py` | Voix off neuronale gratuite (`edge-tts`) |
| Monter | `media/video.py` | ffmpeg : Ken Burns, sous-titres incrustés, 9:16 |
| Contrôler | `safety/policy.py` | Divulgation IA, allégations santé, contenu démonétisant |
| Publier | `publishing/` | API officielles Instagram Graph et TikTok Content Posting |
| Mesurer | `analytics/collector.py` | Vues, engagement, normalisés entre plateformes |
| Optimiser | `analytics/optimizer.py` | Ré-pondère les piliers selon les résultats réels |
| Monétiser | `monetization/` | Affiliation, programme PDF, media kit, suivi des revenus |

</details>

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

## Trois règles inscrites dans le code

Ce ne sont pas des consignes de rédaction : le contrôle de conformité refuse
de publier ce qui les enfreint, et les tests le vérifient.

1. **Le train de vie ne prouve rien.** Aucune légende ne peut relier le décor
   d'Eve à un gain financier. Elle est générée, elle n'a aucun revenu.
2. **Aucun chiffre inventé.** Les performances viennent exclusivement de
   `data/trading/results.json`. Pas de fichier, pas de chiffre — voir
   [docs/RESULTATS-TRADING.md](docs/RESULTATS-TRADING.md).
3. **Rien n'est vendu autour du système.** Pas de formation, pas de signaux,
   pas de « DM pour recevoir », pas de groupe privé.

```bash
python3 -m eve.cli preview --pillar work    # voir ce que ça donne
```

## Monétisation

Le compte ne vend rien pour l'instant. La séquence prévue :

1. **Audience** — publication régulière, piliers mode et art de vivre en tête.
2. **Guide de style gratuit** — `python3 -m eve.cli product` génère « La
   garde-robe de 30 pièces ». C'est un aimant : il construit la liste et
   l'habitude avant l'ouverture de la boutique.
3. **Partenariats de marque** — media kit généré, nature IA annoncée d'emblée.
   Tarif usuel : 1 à 2 % du nombre d'abonnés par publication.
4. **Le site de vêtements** — la vraie destination. Tout le contenu mode qui
   précède sert à ça.

```bash
python3 -m eve.cli revenue --followers 12000 --views 400000
```

## Conformité — non négociable

Une créatrice virtuelle **doit** être déclarée comme telle : FTC aux
États-Unis, article 50 de l'AI Act en Europe, règles AIGC de Meta et de TikTok.
Le module `safety/policy.py` refuse de publier une légende sans mention IA,
avec une promesse de gain, un chiffre de performance sans son risque, une
sollicitation financière ou un visuel suggestif. Ce n'est pas décoratif : c'est ce qui garde le compte monétisable.
Voir [docs/CONFORMITE.md](docs/CONFORMITE.md).

Les publications passent par les **API officielles**. Les bibliothèques
d'automatisation non officielles (`instagrapi`, `TikTokApi`) violent les CGU et
font bannir le compte — elles ont été retirées du projet.

## Automatisation

Trois pièces rendent le fonctionnement autonome — détail dans
[docs/AUTONOMIE.md](docs/AUTONOMIE.md) :

1. **Hébergement des vidéos** — le MP4 est déposé en asset de release GitHub,
   seule URL publique dont Instagram a besoin. Gratuit, aucun serveur.
2. **Renouvellement des jetons** — Instagram expire à 60 jours, TikTok à 24 h.
   Sans renouvellement, l'agent s'arrête sans rien dire.
3. **Mode brouillon TikTok** — publication publique possible avant l'audit de
   l'app : l'API dépose, tu valides d'un geste.

Résultat : Instagram entièrement automatique, TikTok un geste par vidéo.

- En local : `python3 -m eve.cli loop --hours 12`
- Sur serveur : `0 6,18 * * * cd /chemin/eve && python3 -m eve.cli run`
- Sur GitHub Actions : [`.github/workflows/eve-daily.yml`](.github/workflows/eve-daily.yml)
  (gratuit sur dépôt public)

## Tests

```bash
python3 -m pytest tests -q     # 86 tests, dont toute la politique de conformité
```

## Documentation

- [DEMARRAGE.md](DEMARRAGE.md) — **commence par là** : 3 étapes, une page
- [docs/SETUP.md](docs/SETUP.md) — créer les comptes et obtenir les jetons API
- [docs/RENDU-REALISTE.md](docs/RENDU-REALISTE.md) — qualité d'image et cohérence du visage
- [docs/AUTONOMIE.md](docs/AUTONOMIE.md) — faire tourner l'agent sans personne derrière
- [docs/RESULTATS-TRADING.md](docs/RESULTATS-TRADING.md) — publier des chiffres réels, et rien d'autre
- [docs/MONETISATION.md](docs/MONETISATION.md) — sources de revenus, seuils, chiffres
- [docs/CONFORMITE.md](docs/CONFORMITE.md) — obligations légales et règles plateformes
