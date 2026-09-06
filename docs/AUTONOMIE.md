# Faire tourner Eve sans personne derrière

Trois obstacles séparent « ça marche quand je lance la commande » de « ça
tourne tout seul ». Ils sont traités.

## 1. Instagram exige une URL publique

Instagram ne reçoit pas de fichier : il **télécharge** la vidéo depuis une
URL. Sans hébergement, aucune publication n'est possible.

L'agent dépose donc le MP4 comme **asset d'une release GitHub** et donne ce
lien à Instagram. Gratuit, stable, aucun serveur à louer. Dans un workflow
Actions, `GITHUB_TOKEN` est fourni automatiquement — il n'y a rien à
configurer.

> **Condition** : le dépôt doit être **public**. Sur un dépôt privé, les URLs
> de release ne sont pas accessibles et Instagram reçoit un 404.
> `check_public_access()` le détecte et le signale au lieu de laisser la
> publication échouer sans explication.

Un autre hébergement (Cloudflare R2, S3, un VPS) reste possible : renseigner
`PUBLIC_MEDIA_BASE_URL`, il est prioritaire.

## 2. Les jetons expirent — et l'arrêt est silencieux

| Jeton | Durée de vie |
|---|---|
| Instagram (longue durée) | 60 jours |
| TikTok (accès) | 24 heures |
| TikTok (rafraîchissement) | 1 an |

Sans renouvellement, l'agent continue de tourner, les publications échouent,
et rien n'indique pourquoi. `eve/publishing/tokens.py` renouvelle avant
l'échéance (10 jours de marge côté Instagram, 2 heures côté TikTok) et
conserve le résultat dans l'état SQLite.

Secrets nécessaires au renouvellement :

```
META_APP_ID           META_APP_SECRET          # Instagram
TIKTOK_CLIENT_KEY     TIKTOK_CLIENT_SECRET     # TikTok
TIKTOK_REFRESH_TOKEN
```

Sans eux, rien ne casse : le jeton existant est conservé et le rapport
d'exécution prévient — *« le jeton expire dans 3 jours et n'a pas pu être
renouvelé »*. Un échec réseau ne fait jamais perdre le jeton en place.

Les jetons ne sont **pas** réécrits dans les secrets du dépôt : cela
demanderait un jeton personnel aux droits étendus, soit un risque plus grand
que le problème résolu.

## 3. TikTok bride les applications non auditées

Avant l'audit TikTok, l'API ne peut publier qu'en `SELF_ONLY` — visible de
toi seule. Inutilisable pour un compte public.

Le contournement est le **mode brouillon** (`TIKTOK_DRAFT_MODE=1`, actif par
défaut) : l'API dépose la vidéo dans ton application TikTok, tu valides d'un
geste. Une seconde par vidéo au lieu d'un montage manuel.

Une fois l'audit obtenu, passer `TIKTOK_DRAFT_MODE=0` pour une publication
entièrement automatique.

## Le résultat

| | Aujourd'hui |
|---|---|
| Écriture, images, voix, montage | automatique |
| Contrôle de conformité | automatique |
| **Instagram** | **automatique de bout en bout** |
| **TikTok** | **un geste de validation par vidéo** |
| Statistiques et ajustement du calendrier | automatique |
| Réponses aux commentaires | manuel, et c'est délibéré |

## Mise en route

Dépôt GitHub → **Settings → Secrets and variables → Actions** :

```
IG_USER_ID              IG_ACCESS_TOKEN
META_APP_ID             META_APP_SECRET
TIKTOK_ACCESS_TOKEN     TIKTOK_CLIENT_KEY
TIKTOK_CLIENT_SECRET    TIKTOK_REFRESH_TOKEN
GEMINI_API_KEY
```

Puis, dans `.github/workflows/eve-daily.yml`, décommenter le bloc
`schedule`. L'agent publie alors deux fois par jour, sans intervention.

Tant que `DRY_RUN` vaut `1`, rien n'est publié : le workflow produit les
vidéos et les met en téléchargement. C'est le bon réglage pour les premières
semaines.
