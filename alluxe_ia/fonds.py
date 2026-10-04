"""Les photos de fond des couvertures alluxe.ia : une scène par post.

4 oct., demande de l'opérateur : « mettre des images au lieu d'un fond de
couleur, des beaux paysages, regarde ce qui se fait de mieux ». Ce qui
marche sur les couvertures en 2026 : une image nette et forte, un seul
titre en gros, fort contraste. On choisit donc pour chaque post une scène
qui RACONTE son sujet (un tas de papiers froissés pour « 108 rejetées »,
une fusée qui attend pour « écrit, jamais lancé ») plutôt qu'un paysage
au hasard : l'image intrigue, le titre explique.

Règles de la page : aucun visage (page sans visage), aucun texte dans
l'image (il serait illisible ou faux), aucune marque.

    python3 -m alluxe_ia.fonds                 # génère les fonds manquants
    python3 -m alluxe_ia.fonds 03-108-rejetees --refaire
    python3 -m alluxe_ia.fonds --brouillon     # moins cher, pour choisir
    python3 -m alluxe_ia.fonds --pixabay       # vraies photos de Pixabay
    python3 -m alluxe_ia.fonds --pexels        # vraies photos de Pexels

PIXABAY (pixabay.com) : photos ET vidéos gratuites, usage commercial
permis, sans attribution. La clé gratuite s'affiche sur
pixabay.com/api/docs une fois connecté (.env : PIXABAY_API_KEY). Pixabay
interdit de lier ses images à distance : on les TÉLÉCHARGE, c'est ce que
fait ce module. 4 oct. : Pexels a suspendu la délivrance de nouvelles
clés, Pixabay est donc la banque par défaut.

PEXELS (pexels.com) : banque gratuite de photos ET de vidéos, usage
commercial permis, sans attribution obligatoire, API gratuite (clé dans
.env : PEXELS_API_KEY, 200 requêtes/heure). Une vraie photo bat souvent
une image générée en réalisme. Le photographe est noté dans
fonds/credits.json (on le cite en légende si on veut, ce n'est pas exigé).

Les images vont dans alluxe_ia/fonds/<id>.jpg ; une couverture sans fond
garde sa couleur vive (slides.py), rien ne casse.

Utilise le générateur de Luna (luna/moteurs.py) SANS sa photo de
référence : sinon le visage de Luna apparaîtrait sur les fonds.
"""
from __future__ import annotations

import argparse
import io
import os
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
DOSSIER = os.path.join(ICI, "fonds")

STYLE = ("cinematic editorial photograph, dramatic moody lighting, rich deep colors, "
         "shallow depth of field, high detail, 35mm film look, vertical composition with "
         "calm empty lower half. No people, no faces, no hands, no text, no letters, "
         "no logos, no watermark.")

NEGATIF = "people, face, person, hands, text, letters, words, logo, watermark, blurry, lowres"

SCENES: dict[str, str] = {
    "01-tout-construit": "a single desk at night in a dark loft, an open laptop glowing, "
                         "city lights through a huge window behind",
    "02-le-labo": "a dark laboratory at night, rows of glass flasks glowing teal and amber",
    "03-108-rejetees": "a huge pile of crumpled paper balls on a dark wooden desk under a "
                       "single warm lamp",
    "04-cahier-des-charges": "an open notebook with blank pages and a fountain pen on an oak "
                             "table, soft morning window light, top-down",
    "05-publication-auto": "an old printing press running alone in a dark workshop, warm "
                           "light, paper sheets flying",
    "06-fichier-decisions": "old wooden library card catalog drawers, one drawer open, warm "
                            "light in a quiet library",
    "07-tests-verts": "rows of glowing green indicator lights in a dark server room, one "
                      "single red light among them",
    "08-agent-garde-fous": "an industrial robotic arm behind a glass safety barrier in a dark "
                           "factory, amber warning light",
    "09-methode-4-cases": "four square stone tiles on white sand seen from above, minimalist, "
                          "long soft shadows",
    "10-cinq-erreurs": "a chessboard with a fallen king piece, dramatic side light, black "
                       "background",
    "11-assistant-perso": "a cozy desk at golden hour, a small glowing desk lamp, a cup of "
                          "coffee, warm bokeh",
    "12-arrete-d-inventer": "a blank paper price tag hanging on a string under a spotlight, "
                            "dark background",
    "13-casse-cette-semaine": "shattered glass on a dark table catching colorful light",
    "14-avant-apres-prompt": "a window half fogged and half clear, through the clear half a "
                             "sharp mountain landscape at sunrise",
    "15-expliquer-un-bug": "a magnifying glass over a green circuit board, macro shot, "
                           "dramatic light",
    "16-ecrit-pas-lance": "a rocket waiting on its launch pad at dusk, mist, floodlights",
    "17-sur-de-lui-et-faux": "an empty desert highway in fog with a lone road sign, "
                             "early morning",
    "18-outils-garde-arrete": "a workshop pegboard wall with neatly hung tools and a few "
                              "empty painted outlines, warm light",
    "19-essai-different-du-vrai": "a miniature model city in the foreground and the real "
                                  "city skyline at dusk behind it, tilt-shift",
    "20-affichage-qui-mentait": "a glowing car dashboard gauge at night, needle frozen, "
                                "neon reflections on wet glass",
    "21-checklist-mise-en-ligne": "an airplane cockpit at night, glowing instruments, a "
                                  "paper checklist clipped on the side",
    "22-zero-resultat": "an empty fishing net on a wooden dock at dawn, calm misty sea",
}


# Mots-clés courts pour la recherche Pexels (en anglais : la banque l'est).
RECHERCHE: dict[str, str] = {
    "01-tout-construit": "desk at night laptop city",
    "02-le-labo": "laboratory glass night",
    "03-108-rejetees": "crumpled paper pile",
    "04-cahier-des-charges": "blank notebook pen",
    "05-publication-auto": "printing press",
    "06-fichier-decisions": "library card catalog",
    "07-tests-verts": "server room lights",
    "08-agent-garde-fous": "robotic arm factory",
    "09-methode-4-cases": "minimalist squares shadow",
    "10-cinq-erreurs": "chess king fallen",
    "11-assistant-perso": "cozy desk lamp evening",
    "12-arrete-d-inventer": "price tag dark",
    "13-casse-cette-semaine": "broken glass",
    "14-avant-apres-prompt": "foggy window mountains",
    "15-expliquer-un-bug": "magnifying glass circuit board",
    "16-ecrit-pas-lance": "rocket launch pad",
    "17-sur-de-lui-et-faux": "foggy desert road",
    "18-outils-garde-arrete": "tools wall workshop",
    "19-essai-different-du-vrai": "miniature city tilt shift",
    "20-affichage-qui-mentait": "car dashboard night",
    "21-checklist-mise-en-ligne": "cockpit night",
    "22-zero-resultat": "empty fishing net dock",
}


def chercher_pexels(post_id: str) -> str:
    """La première photo verticale de Pexels pour ce post, téléchargée."""
    import json
    import urllib.parse
    import urllib.request
    cle = os.environ.get("PEXELS_API_KEY", "").strip()
    if not cle:
        raise RuntimeError("PEXELS_API_KEY absent du .env (clé gratuite sur pexels.com/api)")
    q = urllib.parse.urlencode({"query": RECHERCHE[post_id], "orientation": "portrait",
                                "per_page": 5})
    r = urllib.request.Request(f"https://api.pexels.com/v1/search?{q}",
                               headers={"Authorization": cle, "User-Agent": "alluxe-ia"})
    with urllib.request.urlopen(r, timeout=30) as resp:
        photos = json.load(resp).get("photos", [])
    if not photos:
        raise RuntimeError(f"aucune photo pour « {RECHERCHE[post_id]} »")
    ph = photos[0]
    r = urllib.request.Request(ph["src"]["large2x"], headers={"User-Agent": "alluxe-ia"})
    with urllib.request.urlopen(r, timeout=60) as resp:
        brut = resp.read()
    os.makedirs(DOSSIER, exist_ok=True)
    from PIL import Image
    Image.open(io.BytesIO(brut)).convert("RGB").save(chemin(post_id), quality=90)
    credits = os.path.join(DOSSIER, "credits.json")
    try:
        with open(credits, encoding="utf-8") as f:
            tout = json.load(f)
    except (OSError, ValueError):
        tout = {}
    tout[post_id] = {"source": "pexels", "photographe": ph.get("photographer"),
                     "page": ph.get("url")}
    with open(credits, "w", encoding="utf-8") as f:
        json.dump(tout, f, indent=2, ensure_ascii=False)
    return chemin(post_id)


def _lire(url: str, entetes: dict | None = None, essais: int = 5) -> bytes:
    """GET avec patience : Pixabay répond 429 quand on enchaîne trop vite
    (4 oct. : 15 posts sur 22 refusés d'affilée). On attend ce qu'il
    demande (Retry-After, sinon 5, 10, 20… s) et on réessaie."""
    import time
    import urllib.error
    import urllib.request
    h = {"User-Agent": "Mozilla/5.0 (alluxe-ia)", **(entetes or {})}
    for k in range(essais):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code != 429 or k == essais - 1:
                raise
            # Pixabay renvoie parfois « Retry-After: 0 » : réessayer tout
            # de suite échoue à coup sûr (4 oct., 9 posts perdus ainsi).
            attente = max(float(e.headers.get("Retry-After") or 0), 6 * 2 ** k)
            print(f"  Pixabay demande d'attendre {attente:.0f} s…")
            time.sleep(min(attente, 90))
    raise RuntimeError("inatteignable")


def chercher_pixabay(post_id: str) -> str:
    """La première photo verticale de Pixabay pour ce post, téléchargée."""
    import json
    import urllib.parse
    cle = os.environ.get("PIXABAY_API_KEY", "").strip()
    if not cle:
        raise RuntimeError("PIXABAY_API_KEY absent du .env (clé gratuite sur pixabay.com/api/docs)")
    q = urllib.parse.urlencode({"key": cle, "q": RECHERCHE[post_id], "image_type": "photo",
                                "orientation": "vertical", "safesearch": "true",
                                "per_page": 5, "order": "popular"})
    hits = json.loads(_lire(f"https://pixabay.com/api/?{q}")).get("hits", [])
    if not hits:
        raise RuntimeError(f"aucune photo pour « {RECHERCHE[post_id]} »")
    # La grande image d'abord ; si elle reste refusée, la moyenne (1280 px,
    # suffisante pour 1080), puis la photo suivante de la recherche.
    derniere = None
    for h in hits:
        for cle_url in ("largeImageURL", "webformatURL"):
            url = h.get(cle_url)
            if not url:
                continue
            if cle_url == "webformatURL":
                url = url.replace("_640.", "_1280.")
            try:
                brut = _lire(url, essais=3)
                break
            except Exception as exc:  # noqa: BLE001
                derniere = exc
        else:
            continue
        break
    else:
        raise derniere or RuntimeError("aucune image téléchargeable")
    _garder(post_id, brut, {"source": "pixabay", "photographe": h.get("user"),
                            "page": h.get("pageURL")})
    return chemin(post_id)


def _garder(post_id: str, brut: bytes, credit: dict) -> None:
    import json
    from PIL import Image
    os.makedirs(DOSSIER, exist_ok=True)
    Image.open(io.BytesIO(brut)).convert("RGB").save(chemin(post_id), quality=90)
    credits = os.path.join(DOSSIER, "credits.json")
    try:
        with open(credits, encoding="utf-8") as f:
            tout = json.load(f)
    except (OSError, ValueError):
        tout = {}
    tout[post_id] = credit
    with open(credits, "w", encoding="utf-8") as f:
        json.dump(tout, f, indent=2, ensure_ascii=False)


def chemin(post_id: str) -> str:
    return os.path.join(DOSSIER, f"{post_id}.jpg")


def prompt(post_id: str) -> str:
    return f"{SCENES[post_id]}. {STYLE}"


def generer(post_id: str, brouillon: bool = False) -> str:
    # Pas de photo de référence : c'est celle du visage de Luna.
    os.environ["LUNA_IMAGE_REFERENCE"] = os.path.join(DOSSIER, "-aucune-reference-")
    from PIL import Image
    from luna.moteurs import GenerateurImages
    brut = GenerateurImages().generer(prompt(post_id), negatif=NEGATIF, format="portrait",
                                      qualite="brouillon" if brouillon else "finale")
    os.makedirs(DOSSIER, exist_ok=True)
    img = Image.open(io.BytesIO(brut)).convert("RGB")
    img.save(chemin(post_id), quality=90)
    return chemin(post_id)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("ids", nargs="*")
    p.add_argument("--refaire", action="store_true")
    p.add_argument("--brouillon", action="store_true")
    p.add_argument("--pexels", action="store_true")
    p.add_argument("--pixabay", action="store_true")
    a = p.parse_args()
    sys.path.insert(0, os.path.dirname(ICI))
    try:
        from gold_bot.env import charger_env
        charger_env()
    except Exception:  # noqa: BLE001
        pass
    try:
        import PIL  # noqa: F401
    except ImportError:
        print("Pillow absent : lancer avec le Python du robot, "
              "~/Eve-AI-Influencer/.venv/bin/python -m alluxe_ia.fonds …")
        return 2
    import time
    code = 0
    for pid in a.ids or list(SCENES):
        if os.path.exists(chemin(pid)) and not a.refaire:
            continue
        try:
            fait = (chercher_pixabay(pid) if a.pixabay else
                    chercher_pexels(pid) if a.pexels else generer(pid, a.brouillon))
            print(f"{pid} -> {fait}")
            if a.pixabay or a.pexels:
                time.sleep(2)   # une banque gratuite n'aime pas les rafales
        except Exception as exc:  # noqa: BLE001 -- un fond raté n'arrête pas les autres
            print(f"{pid} : échec ({str(exc)[:200]})")
            code = 1
    return code


if __name__ == "__main__":
    raise SystemExit(main())
