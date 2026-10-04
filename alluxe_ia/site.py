"""Les données du site alluxe.fr, tirées des publications (alluxe_ia/posts.json).

    python3 -m alluxe_ia.site   ->  docs/kit/prompts.json + docs/kit/apercus/*.jpg

La bibliothèque de prompts du site se met ainsi à jour toute seule quand un
post est ajouté : jamais de copie à la main (une copie finit par mentir).
"""
from __future__ import annotations

import json
import os

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(ICI)
SORTIE = os.path.join(RACINE, "docs", "kit")

CATEGORIES = {
    "Bien écrire un prompt": ["09", "23", "24", "31", "12", "14", "17", "11"],
    "Au quotidien": ["26", "27", "28", "29", "32"],
    "Construire un projet": ["04", "02", "05", "21", "06", "08"],
    "Trouver un bug": ["03", "07", "15", "16", "19", "20", "22"],
}
TITRES_GENERIQUES = {"Le prompt", "La phrase", "Le modèle à copier", "Après", "Le prompt à coller"}
EXCLUS = {"Avant"}                     # le mauvais exemple du post avant/après
APERCUS = ["01-tout-construit", "03-108-rejetees", "24-ia-qui-invente"]


def categorie(post_id: str) -> str:
    n = post_id.split("-")[0]
    for nom, ids in CATEGORIES.items():
        if n in ids:
            return nom
    return "Bien écrire un prompt"


def prompts() -> list[dict]:
    with open(os.path.join(ICI, "posts.json"), encoding="utf-8") as f:
        posts = json.load(f)
    sortie = []
    for p in posts:
        couverture = p["slides"][0]["titre"]
        for s in p["slides"]:
            if s["type"] != "prompt" or s["titre"] in EXCLUS:
                continue
            titre = s["titre"]
            if titre in TITRES_GENERIQUES:
                titre = couverture
            elif titre[:2].rstrip(".").isdigit():
                titre = titre.split(".", 1)[1].strip()
            sortie.append({"id": f"{p['id']}-{len(sortie)}", "titre": titre.rstrip("."),
                           "categorie": categorie(p["id"]), "sujet": couverture,
                           "prompt": s["prompt"]})
    return sortie


def construire() -> list[str]:
    os.makedirs(os.path.join(SORTIE, "apercus"), exist_ok=True)
    with open(os.path.join(SORTIE, "prompts.json"), "w", encoding="utf-8") as f:
        json.dump(prompts(), f, ensure_ascii=False, indent=1)
    from alluxe_ia.slides import Post
    from alluxe_ia.slides_pop import rendre
    with open(os.path.join(ICI, "posts.json"), encoding="utf-8") as f:
        posts = {x["id"]: Post.depuis(x) for x in json.load(f)}
    fichiers = ["prompts.json"]
    for i, pid in enumerate(APERCUS, 1):
        rendre(posts[pid])[0].convert("RGB").resize((540, 675)).save(
            os.path.join(SORTIE, "apercus", f"{i}.jpg"), quality=82, optimize=True)
        fichiers.append(f"apercus/{i}.jpg")
    return fichiers


if __name__ == "__main__":
    print(construire())
