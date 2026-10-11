"""Les images d'exemple de la boutique de Noël (alluxe.fr/noel).

    python3 -m boutique.visuels            # génère ce qui manque
    python3 -m boutique.visuels --refaire hero

Ce ne sont PAS des commandes de clients : ce sont les vitrines (portraits
inventés, posés sur leurs supports). Chaque image coûte ~0,07 EUR chez
OpenAI ; un compteur à part (data/boutique_depenses.json, plafond 2 EUR par
jour) refuse avant l'appel quand la journée est pleine. Le moteur de Luna
n'est pas réutilisé : il joint le visage de Luna en référence.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import urllib.request
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
SORTIE = RACINE / "docs" / "kit" / "noel"

STYLE = ("Photographie produit réaliste, lumière chaude de Noël, profondeur de champ, "
         "rendu haut de gamme pour une boutique en ligne. Aucun texte, aucun logo, aucune marque.")

VISUELS = {
    "hero": ("paysage", "Salon chaleureux le soir de Noël, sapin illuminé flou à l'arrière-plan. "
             "Au mur, une grande affiche encadrée de bois clair : le portrait peint d'un golden "
             "retriever portant un pull de Noël rouge et blanc, style peinture à l'huile classique. "
             "Sous l'affiche, un paquet cadeau ouvert avec du papier kraft et un ruban rouge."),
    # La photo « client » : volontairement banale, SANS le style produit (le 11 oct. le
    # suffixe « lumière de Noël » a donné une bougie en pomme de pin au lieu du chien).
    "avant-chien": ("carre", "Photo amateur prise au smartphone : un golden retriever assis sur "
                    "la pelouse d'un jardin, regarde l'objectif, lumière de jour ordinaire, "
                    "cadrage banal, aucune décoration.", None),
    # Le portrait est fait D'APRÈS la photo (endpoint edits) : c'est exactement la
    # chaîne d'une vraie commande, et la comparaison avant/après est honnête.
    "apres-chien": ("carre", "Transforme ce chien en portrait peint à l'huile de style XVIIIe : "
                    "garde exactement sa tête, son pelage, sa couleur et son expression. Il porte "
                    "un pull de Noël tricoté rouge et blanc, fond vert sapin profond avec bokeh "
                    "doré. Aucun texte.", "avant-chien.jpg"),
    "chat-mug": ("carre", "Un mug en céramique blanche posé sur une table en bois près d'une "
                 "fenêtre enneigée, à côté de biscuits de Noël. Sur le mug, illustration aquarelle "
                 "d'un chat tigré roux coiffé d'un bonnet de Père Noël."),
    "famille-poster": ("portrait", "Affiche encadrée posée contre un mur blanc, à côté d'une "
                       "branche de sapin et de bougies. L'affiche montre une illustration douce, "
                       "style livre pour enfants, d'une famille (deux parents, deux enfants et un "
                       "chien) en pyjamas de Noël assortis devant une cheminée."),
    "plaid": ("carre", "Un plaid polaire doux plié sur un canapé beige, ambiance cosy de Noël. Sur "
              "le plaid est imprimé le portrait illustré d'un bouledogue français en écharpe "
              "rouge, fond étoilé bleu nuit."),
    "boule": ("carre", "Gros plan d'une boule de Noël blanche en céramique accrochée à un sapin "
              "illuminé. Sur la boule, petit portrait peint d'un chat noir aux yeux verts avec "
              "un nœud doré."),
    "toile": ("portrait", "Une toile sur châssis accrochée dans une entrée élégante décorée pour "
              "Noël. Sur la toile, portrait style aquarelle d'un couple de chiens (un beagle et un "
              "border collie) côte à côte avec une couronne de houx."),
}

TAILLES = {"carre": "1024x1024", "paysage": "1536x1024", "portrait": "1024x1536"}


def generer(nom: str) -> Path:
    from luna.budget import Depenses
    fmt, scene, *reste = VISUELS[nom]
    reference = reste[0] if reste else ""
    Depenses(plafond_eur=2.0, fichier=RACINE / "data" / "boutique_depenses.json") \
        .reserver(float(os.getenv("LUNA_COUT_IMAGE_EUR", "0.07")), f"boutique {nom}")
    modele = os.getenv("LUNA_IMAGE_MODELE_OPENAI", "gpt-image-2")
    prompt = scene if len(reste) else f"{scene} {STYLE}"
    entetes = {"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"}
    if reference:
        from luna.moteurs import GenerateurImages
        brut = GenerateurImages._requeter_multipart(
            "https://api.openai.com/v1/images/edits", os.environ["OPENAI_API_KEY"],
            champs={"model": modele, "prompt": prompt, "size": TAILLES[fmt], "n": "1"},
            fichiers={"image[]": (reference, (SORTIE / reference).read_bytes(), "image/jpeg")})
    else:
        req = urllib.request.Request("https://api.openai.com/v1/images/generations",
                                     data=json.dumps({"model": modele, "prompt": prompt,
                                                      "size": TAILLES[fmt], "n": 1}).encode(),
                                     headers={**entetes, "Content-Type": "application/json"})
        brut = urllib.request.urlopen(req, timeout=300).read()
    donnees = json.loads(brut)["data"][0]
    brut = base64.b64decode(donnees["b64_json"]) if donnees.get("b64_json") \
        else urllib.request.urlopen(donnees["url"], timeout=120).read()
    png = SORTIE / f"{nom}.png"
    png.write_bytes(brut)
    # JPEG compressé pour le site (les PNG font 2-3 Mo).
    from PIL import Image
    jpg = SORTIE / f"{nom}.jpg"
    Image.open(png).convert("RGB").save(jpg, quality=82, optimize=True, progressive=True)
    png.unlink()
    return jpg


def main() -> int:
    sys.path.insert(0, str(RACINE))
    from gold_bot.env import charger_env
    charger_env()
    SORTIE.mkdir(parents=True, exist_ok=True)
    refaire = set(sys.argv[sys.argv.index("--refaire") + 1:]) if "--refaire" in sys.argv else set()
    for nom in VISUELS:
        if (SORTIE / f"{nom}.jpg").exists() and nom not in refaire:
            continue
        print("génère", nom, "->", generer(nom))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
