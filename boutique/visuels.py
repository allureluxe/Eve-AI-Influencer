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
    # 12 oct. : l'opérateur recentre sur famille, couple, enfants, amour (moins d'animaux).
    "hero": ("paysage", "Salon chaleureux le soir de Noël, sapin illuminé flou à l'arrière-plan. "
             "Au mur, une grande affiche encadrée de bois clair : le portrait peint à l'huile "
             "d'une jeune famille (un père, une mère, une petite fille et un bébé) en pulls de "
             "Noël rouges, regards tendres. Sous l'affiche, des cadeaux emballés de rouge."),
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
                 "d'un jeune couple amoureux qui s'embrasse sous le gui, bonnets rouges."),
    "famille-poster": ("portrait", "Affiche encadrée posée contre un mur blanc, à côté d'une "
                       "branche de sapin et de bougies. L'affiche montre une illustration douce, "
                       "style livre pour enfants, d'une famille (deux parents, deux enfants et un "
                       "chien) en pyjamas de Noël assortis devant une cheminée."),
    "plaid": ("carre", "Un plaid polaire doux plié sur un canapé beige, ambiance cosy de Noël. Sur "
              "le plaid est imprimé le portrait illustré d'un couple enlacé sous la neige, "
              "écharpes rouges, ciel étoilé."),
    "boule": ("carre", "Gros plan d'une décoration de sapin ronde en bois clair accrochée par "
              "un ruban rouge à un sapin illuminé. Dessus, petit portrait peint d'un chat noir aux yeux verts avec "
              "un nœud doré."),
    "toile": ("portrait", "Une toile sur châssis accrochée dans une entrée élégante décorée pour "
              "Noël. Sur la toile, portrait style aquarelle d'un frère et d'une sœur (6 et 4 ans) "
              "qui rient ensemble, couronne de houx et flocons."),
    "cartes": ("carre", "Un paquet de cartes de vœux pliées posées sur une table en bois avec "
               "des enveloppes kraft, une branche de sapin et un ruban rouge. Sur la carte du "
               "dessus, portrait aquarelle d'une famille de quatre en bonnets de Noël."),
    "acrylique": ("portrait", "Un tableau en verre acrylique brillant posé sur une commode près "
                  "d'un sapin illuminé, reflets lumineux sur le verre. Dans le tableau, portrait "
                  "peint à l'huile d'une maman qui tient son bébé, couronne de houx, fond rouge."),
    "calendrier": ("portrait", "Un calendrier mural 2027 à spirale accroché dans une cuisine "
                   "décorée pour Noël. La page montre le portrait illustré d'un labrador chocolat "
                   "en écharpe de laine verte, style conte de Noël."),
    "coussin": ("carre", "Un coussin carré sur un fauteuil en velours rouge, plaid et guirlande "
                "lumineuse autour. Sur le coussin, portrait peint d'un bébé en bonnet de lutin."),
    "body-bebe": ("carre", "Un body bébé blanc posé à plat sur une couverture en laine crème avec "
                  "une petite branche de sapin. Sur le body, illustration aquarelle tendre d'un bébé "
                  "souriant avec un bonnet de lutin vert."),
    "sweat-enfant": ("carre", "Une petite fille de 6 ans souriante devant un sapin illuminé, elle porte "
                     "un sweat rouge sur lequel est imprimé son propre portrait illustré en costume "
                     "de super-héroïne inventée, cape dorée, sans logo."),
    "pull-famille": ("paysage", "Une famille (deux parents, un garçon, une fille) assise sur un canapé "
                     "devant la cheminée, tous en sweats de Noël rouges assortis, imprimés du portrait "
                     "illustré de la famille en lutins. Ambiance chaleureuse et joyeuse."),
    "bonnet": ("carre", "Un bonnet à pompon tricoté rouge posé sur une écharpe, neige légère, "
               "petit écusson rond brodé avec le portrait d'un garçon souriant."),
    "chaussettes": ("carre", "Une paire de chaussettes de Noël colorées posées près d'une tasse de "
                    "chocolat chaud, motif répété de petits visages illustrés d'une famille en "
                    "bonnets de Père Noël, flocons et sapins."),
    "tablier": ("carre", "Un tablier en coton écru porté par une femme qui décore des biscuits de Noël "
                "dans une cuisine chaleureuse ; sur le tablier, illustration de la famille en lutins."),
    "papier-cadeau": ("carre", "Des cadeaux emballés dans un papier cadeau rouge et doré au motif "
                      "répété : petits portraits illustrés d'un couple et de leur chien en bonnets "
                      "de Noël, entre des flocons et des étoiles. Rubans dorés, sapin flou derrière."),
    "housse-couette": ("paysage", "Une chambre d'enfant décorée pour Noël, lit avec une housse de "
                       "couette imprimée d'une grande illustration du garçon de la famille en "
                       "pilote de traîneau inventé, ciel étoilé et rennes."),
    "chaussons": ("carre", "Une paire de chaussons moelleux rouges près d'une cheminée, sur chacun "
                  "le visage illustré d'une petite fille en bonnet de Père Noël."),
    "pyjama": ("paysage", "Une famille en pyjamas de Noël assortis rouges et verts, imprimés de leurs "
               "propres petits portraits illustrés, assise par terre devant le sapin le matin de Noël."),
    "sapin": ("portrait", "Un grand sapin de Noël artificiel très fourni, décoré de boules rouges et "
              "dorées et d'une guirlande lumineuse chaude, dans un salon élégant."),
    "guirlande": ("paysage", "Une guirlande lumineuse LED blanc chaud accrochée en festons le long "
                  "d'un escalier en bois, branches de sapin, ambiance du soir."),
    "boules": ("carre", "Un lot de boules de Noël rouges, dorées et blanches, mates et brillantes, "
               "disposées dans une coupe en verre, fond chaleureux flou."),
    "fenetre": ("paysage", "Une fenêtre décorée pour Noël vue de l'intérieur : silhouettes lumineuses "
                "de flocons et d'étoiles, rideau lumineux LED, neige dehors, la nuit."),
    "creche": ("paysage", "Une crèche de Noël traditionnelle en bois et figurines peintes, étable "
               "éclairée d'une petite lumière, mousse et branches de sapin autour."),
    "couronne": ("carre", "Une couronne de porte de Noël en branches de sapin, pommes de pin, baies "
                 "rouges et ruban de velours rouge, sur une porte d'entrée verte."),
    "avant-famille": ("carre", "Photo amateur prise au smartphone : un jeune couple et leur fille de "
                      "5 ans assis sur un canapé, ils sourient à l'objectif, lumière de salon "
                      "ordinaire, cadrage banal, aucune décoration.", None),
    "apres-famille": ("carre", "Transforme cette photo en portrait de Noël peint à l'huile : garde "
                      "exactement les visages, coiffures et expressions des trois personnes. Ils "
                      "portent des pulls de Noël rouges assortis, fond rouge profond avec sapin "
                      "illuminé et bokeh doré. Aucun texte.", "avant-famille.jpg"),
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
