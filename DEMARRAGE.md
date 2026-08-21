# Démarrer — 3 étapes

## 1. Lancer

```bash
python3 demarrer.py
```

C'est tout. Le script installe ce qu'il faut, vérifie ta machine, puis produit
une première vidéo. **Rien n'est publié** : tu regardes le résultat, tu décides
ensuite.

Une seule chose peut manquer, et le script te le dira : **ffmpeg**, qui assemble
la vidéo.

| Ton système | Commande |
|---|---|
| Ubuntu / Debian | `sudo apt install ffmpeg` |
| macOS | `brew install ffmpeg` |
| Windows | `winget install Gyan.FFmpeg` |

## 2. Regarder

Tout arrive dans le dossier `output/` :

| Fichier | Ce que c'est |
|---|---|
| `output/videos/…/….mp4` | La vidéo verticale, sous-titrée, prête à publier |
| `output/videos/…/cover.jpg` | La miniature |
| `output/products/reset-4-semaines.html` | Le programme à vendre (ouvre-le, imprime en PDF) |
| `output/products/media-kit.md` | Le dossier pour démarcher les marques |

Pour en produire d'autres :

```bash
python3 -m eve.cli go --videos 3
```

## 3. Publier

**Les deux premières semaines, publie à la main.** Tu récupères les MP4 dans
`output/videos/` et tu les postes toi-même. Aucune clé d'API, aucune
configuration, et tu vois tout de suite ce qui accroche.

Deux choses à faire une seule fois, sur chaque compte :

- Mettre dans la bio : `🤖 AI-generated fitness coach · virtual creator`
- Activer le label IA (« AI info » sur Instagram, « contenu généré par IA » sur
  TikTok) au moment de publier.

Ce n'est pas optionnel : c'est ce qui garde les comptes en règle et
monétisables.

---

## Quand tu veux que ça tourne tout seul

Il faut connecter les API — compte Instagram Professionnel, app TikTok. La
marche à suivre est dans **[docs/SETUP.md](docs/SETUP.md)**. Ensuite :

```bash
# dans le fichier .env
DRY_RUN=0

python3 -m eve.cli loop --hours 12
```

## Les seules commandes utiles

```bash
python3 -m eve.cli go        # produire du contenu (celle-ci suffit)
python3 -m eve.cli doctor    # « qu'est-ce qui ne va pas ? »
python3 -m eve.cli preview   # lire un script sans rien produire
python3 -m eve.cli revenue --followers 5000 --views 200000   # projection
```

## Changer quelque chose sur Eve

Un seul fichier : **`eve/persona/eve.yaml`**. Son physique, ses tenues, ses
décors, son ton, ses sujets. Tu modifies, tu relances `go`, tout suit.

## Si ça coince

| Ce que tu vois | Quoi faire |
|---|---|
| Images marquées `[PLACEHOLDER]` | Le générateur d'images était injoignable — relance `go` |
| Vidéo sans voix | `pip install edge-tts` |
| Pas de fichier `.mp4` | Installer ffmpeg (tableau plus haut) |
| `Publication bloquée : …` | Le message nomme la règle : corrige et relance |

Le reste de la documentation ne sert que si tu veux aller plus loin :
[rendu réaliste](docs/RENDU-REALISTE.md) · [monétisation](docs/MONETISATION.md) ·
[conformité](docs/CONFORMITE.md)
