#!/usr/bin/env python3
"""alluxe.ia : rendre et publier les carrousels du compte.

    python3 ops/alluxe_ia.py profil              # la photo de profil (data/alluxe_ia/profil.jpg)
    python3 ops/alluxe_ia.py rendre              # toutes les slides, en local
    python3 ops/alluxe_ia.py rendre 03-methode-4-cases
    python3 ops/alluxe_ia.py suivant             # dit ce qui partirait, sans rien envoyer
    python3 ops/alluxe_ia.py suivant --confirmer # publie le prochain post non publie
    python3 ops/alluxe_ia.py publier 02-pdf-80-pages --confirmer

RIEN NE PART SANS --confirmer. Sans lui, la commande rend les slides
dans data/alluxe_ia/<post>/ et dit ce qu'elle publierait : c'est ce qu'on
relit avant la mise en ligne (etape « controle qualite » du concept).

Les slides sont deposees dans le seau prive `luna`, sous alluxe-ia/, et
Instagram les recupere par un lien signe d'une heure (meme principe que
pour Luna, voir ops/instagram.py::url_temporaire).

Un post publie est note dans data/alluxe_ia/publies.json : `suivant`
ne le reprend jamais, et `publier` refuse de le reposter.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.request

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from alluxe_ia.slides import Post, photo_profil, rendre, utiliser_theme  # noqa: E402

# 4 oct. : style « vif » (couverture pleine couleur, étiquette, chiffre
# géant, fenêtre de conversation). Les posts déjà publiés ne bougent pas.
STYLE = os.environ.get("ALLUXE_IA_STYLE", "vif")

POSTS = os.path.join(RACINE, "alluxe_ia", "posts.json")
SORTIE = os.path.join(RACINE, "data", "alluxe_ia")
JOURNAL = os.path.join(SORTIE, "publies.json")
SEAU = "luna"


def charger_posts() -> list[Post]:
    with open(POSTS, encoding="utf-8") as f:
        return [Post.depuis(p) for p in json.load(f)]


def deja_publies() -> dict:
    try:
        with open(JOURNAL, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def noter_publication(post_id: str, media_id: str) -> None:
    journal = deja_publies()
    journal[post_id] = {"media_id": media_id,
                        "le": dt.datetime.now(dt.timezone.utc).isoformat()}
    os.makedirs(SORTIE, exist_ok=True)
    with open(JOURNAL, "w", encoding="utf-8") as f:
        json.dump(journal, f, indent=2, ensure_ascii=False)


def rendre_post(post: Post) -> list[str]:
    dossier = os.path.join(SORTIE, post.id)
    os.makedirs(dossier, exist_ok=True)
    chemins = []
    utiliser_theme(STYLE)
    for i, img in enumerate(rendre(post), start=1):
        chemin = os.path.join(dossier, f"{i:02d}.jpg")
        img.save(chemin, quality=92)
        chemins.append(chemin)
    return chemins


def televerser(fichier: str, chemin_seau: str) -> None:
    url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    cle = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not url or not cle:
        raise SystemExit("SUPABASE_URL ou SUPABASE_SERVICE_KEY absent")
    with open(fichier, "rb") as f:
        octets = f.read()
    req = urllib.request.Request(
        f"{url}/storage/v1/object/{SEAU}/{chemin_seau}", method="POST",
        data=octets, headers={"apikey": cle, "Authorization": f"Bearer {cle}",
                              "Content-Type": "image/jpeg", "x-upsert": "true"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            r.read()
    except urllib.error.HTTPError as e:
        raise SystemExit(f"televersement refuse ({e.code}) : {e.read()[:200]!r}")


def publier_post(post: Post, confirmer: bool) -> None:
    if post.id in deja_publies():
        raise SystemExit(f"{post.id} est deja publie : rien a faire")
    chemins = rendre_post(post)
    print(f"{post.id} : {len(chemins)} slides rendues dans {os.path.dirname(chemins[0])}")
    if not confirmer:
        print("ESSAI A BLANC : rien n'est envoye. Relire les slides, puis relancer avec --confirmer.")
        print("--- legende ---\n" + post.legende)
        return

    from ops.instagram import publier_carrousel, url_temporaire
    urls = []
    for i, ch in enumerate(chemins, start=1):
        dest = f"alluxe-ia/{post.id}/{i:02d}.jpg"
        televerser(ch, dest)
        urls.append(url_temporaire(dest, seau=SEAU))
    media_id = publier_carrousel(urls, post.legende)
    noter_publication(post.id, media_id)
    print(f"PUBLIE : {post.id} -> {media_id}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sous = ap.add_subparsers(dest="action", required=True)
    sous.add_parser("profil")
    r = sous.add_parser("rendre")
    r.add_argument("post", nargs="?")
    s = sous.add_parser("suivant")
    s.add_argument("--confirmer", action="store_true")
    p = sous.add_parser("publier")
    p.add_argument("post")
    p.add_argument("--confirmer", action="store_true")
    a = ap.parse_args()

    try:
        from gold_bot.env import charger_env
        charger_env()
    except Exception:  # noqa: BLE001 -- le rendu local n'a besoin de rien
        pass

    posts = charger_posts()
    par_id = {p.id: p for p in posts}

    if a.action == "profil":
        os.makedirs(SORTIE, exist_ok=True)
        chemin = os.path.join(SORTIE, "profil.jpg")
        photo_profil().save(chemin, quality=95)
        print(f"photo de profil -> {chemin}")
        return 0

    if a.action == "rendre":
        cibles = [par_id[a.post]] if a.post else posts
        for post in cibles:
            ch = rendre_post(post)
            print(f"{post.id} : {len(ch)} slides -> {os.path.dirname(ch[0])}")
        return 0

    if a.action == "suivant":
        publies = deja_publies()
        restants = [p for p in posts if p.id not in publies]
        if not restants:
            print("tous les posts sont publies : en ecrire de nouveaux dans alluxe_ia/posts.json")
            return 0
        publier_post(restants[0], a.confirmer)
        return 0

    if a.post not in par_id:
        raise SystemExit(f"post inconnu : {a.post} (connus : {', '.join(par_id)})")
    publier_post(par_id[a.post], a.confirmer)
    return 0


if __name__ == "__main__":
    sys.exit(main())
