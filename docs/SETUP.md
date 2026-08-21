# Installation et mise en service

## 1. Environnement local

```bash
git clone <ce-dépôt> && cd Eve-AI-Influencer
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m eve.cli doctor
```

**ffmpeg** est le seul outil non-Python indispensable (montage vidéo) :

| Système | Commande |
|---|---|
| Ubuntu / Debian | `sudo apt install ffmpeg` |
| macOS | `brew install ffmpeg` |
| Windows | `winget install Gyan.FFmpeg` |

Sans ffmpeg, l'agent produit quand même les images, la voix et les
sous-titres — seul le MP4 final manque.

## 2. Voix off gratuite

`pip install edge-tts` suffit (voix neuronales Microsoft, sans compte).
Vérifier : `edge-tts --list-voices | grep en-US`.

Voix conseillées : `en-US-AvaNeural` (anglais), `fr-FR-DeniseNeural` (français).

## 3. Comptes sociaux

### Instagram

L'API Graph exige un compte **Professionnel** :

1. Créer le compte Instagram, le passer en *Professionnel* (Créateur ou Entreprise).
2. Le relier à une **Page Facebook** (Paramètres → Comptes liés).
3. Sur [developers.facebook.com](https://developers.facebook.com) : créer une app,
   ajouter le produit *Instagram Graph API*.
4. Demander les permissions `instagram_basic`, `instagram_content_publish`,
   `pages_read_engagement`, `instagram_manage_insights`.
5. Générer un **jeton longue durée** (60 jours, à renouveler) et récupérer
   l'`IG_USER_ID` via `/me/accounts` puis `?fields=instagram_business_account`.

```bash
IG_USER_ID=17841400000000000
IG_ACCESS_TOKEN=EAAG...
```

**Contrainte importante** : Instagram télécharge la vidéo depuis une **URL
publique**. Il faut donc héberger le MP4 quelque part (Cloudflare R2, un bucket
S3 public, un VPS, GitHub Releases) et renseigner `PUBLIC_MEDIA_BASE_URL`.
Sans cela, seule la publication TikTok fonctionne.

### TikTok

1. Créer le compte TikTok.
2. Sur [developers.tiktok.com](https://developers.tiktok.com) : créer une app,
   activer **Content Posting API**, scopes `video.publish` et `video.list`.
3. Passer le flux OAuth pour obtenir un `TIKTOK_ACCESS_TOKEN`
   (durée de vie 24 h, `refresh_token` valable 365 jours).

```bash
TIKTOK_CLIENT_KEY=aw...
TIKTOK_CLIENT_SECRET=...
TIKTOK_ACCESS_TOKEN=act...
```

**Avant l'audit de l'app**, TikTok impose `SELF_ONLY` : les vidéos publiées par
l'API ne sont visibles que par toi. C'est normal — l'agent détecte la
restriction et s'y adapte automatiquement. Pour publier en public sans audit,
utilise le mode *inbox* (l'API dépose le brouillon, tu valides dans
l'application) ou publie manuellement les MP4 produits par l'agent.

## 4. Premier cycle

```bash
python -m eve.cli plan --days 7
python -m eve.cli produce --limit 2      # regarde les vidéos avant d'aller plus loin
python -m eve.cli approve --all
python -m eve.cli publish                # encore en DRY_RUN : aucun envoi
```

Quand tout te convient :

```bash
# .env
DRY_RUN=0
REQUIRE_HUMAN_REVIEW=1   # garde la validation humaine encore quelques semaines
```

## 5. Mode autonome

```bash
python -m eve.cli loop --hours 12
```

Ou via cron :

```cron
0 6,18 * * * cd /chemin/Eve-AI-Influencer && .venv/bin/python -m eve.cli run >> logs/eve.log 2>&1
```

Ou via GitHub Actions (gratuit sur dépôt public) — voir
`.github/workflows/eve-daily.yml`. Les jetons vont dans
*Settings → Secrets and variables → Actions*.

## 6. Dépannage

| Symptôme | Cause probable | Correctif |
|---|---|---|
| Images `[PLACEHOLDER]` | Provider injoignable | Vérifier le réseau, ou `IMAGE_PROVIDER=comfyui` |
| Vidéo muette | `edge-tts` absent | `pip install edge-tts` |
| Pas de MP4 | ffmpeg absent | Installer ffmpeg |
| `Publication bloquée` | Règle de conformité | Lire le message : il nomme la règle enfreinte |
| Instagram : URL publique requise | `PUBLIC_MEDIA_BASE_URL` vide | Héberger les MP4 |
| TikTok `privacy_level` refusé | App non auditée | Rester en `SELF_ONLY` ou demander l'audit |
