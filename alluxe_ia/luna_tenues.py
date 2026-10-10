"""La tenue de Luna, différente d'un Reel à l'autre (10 oct. 2026).

L'opérateur : « change les vêtements de Luna, pas qu'elle soit habillée pareil
sur tous les posts ». Le sweat noir était écrit en dur dans le texte commun des
images (`reel_luna_ecrans.COMMUN`) : même tenue à chaque Reel.

Deux règles, et elles ne se contredisent pas :
  - UNE tenue par Reel, la même sur toutes ses scènes (image et vidéo d'un même
    moment portent les mêmes vêtements, décision du 26 sept.) ;
  - jamais une tenue portée dans les DERNIERS_A_EVITER Reels précédents.

Registre de vêtements simples, budget d'étudiante, couvrants et amples : le
modèle d'image exagère poitrine et décolleté dès qu'une tenue est moulante ou
échancrée (constaté le 15 sept.). Rien de suggestif.

    from alluxe_ia.luna_tenues import avec_tenue
    texte = avec_tenue(COMMUN, "06-site-en-1-journee-luna")
"""
from __future__ import annotations

import json
import random
from pathlib import Path

REGISTRE = Path(__file__).resolve().parent.parent / "data/alluxe_ia/luna_tenues.json"
DERNIERS_A_EVITER = 5
#: la tenue écrite en dur dans `reel_luna_ecrans.COMMUN`, remplacée ici
PAR_DEFAUT = "black sweatshirt"

TENUES = {
    "sweat_noir": "black sweatshirt",
    "pull_creme": "loose cream cable-knit sweater",
    "chemise_jean": "oversized light-blue denim shirt over a plain white t-shirt",
    "hoodie_gris": "heather grey zip hoodie, half open over a white t-shirt",
    "cardigan_vert": "sage green loose cardigan over a plain black t-shirt",
    "tshirt_blanc": "plain loose white crew-neck t-shirt",
    "col_roule": "loose chocolate brown turtleneck sweater",
    "surchemise": "beige corduroy overshirt over a grey t-shirt",
    "sweat_bordeaux": "burgundy crew-neck sweatshirt",
    "pull_marine": "navy blue loose knit sweater",
    "chemise_rayee": "loose blue and white striped cotton shirt, sleeves rolled up",
}

#: déjà portées avant ce registre (8 et 10 oct.)
HISTORIQUE_INITIAL = [
    {"reel": "07-luna-ecrans", "tenue": "sweat_noir"},
    {"reel": "06-site-en-1-journee-luna", "tenue": "sweat_noir"},
]


def _lire() -> list[dict]:
    if REGISTRE.exists():
        return json.loads(REGISTRE.read_text())
    return list(HISTORIQUE_INITIAL)


def choisir(reel: str) -> str:
    """Clé de la tenue du Reel ; la même à chaque appel pour un même Reel."""
    histo = _lire()
    for ligne in histo:
        if ligne["reel"] == reel:
            return ligne["tenue"]
    recentes = {l["tenue"] for l in histo[-DERNIERS_A_EVITER:]}
    possibles = [k for k in TENUES if k not in recentes] or list(TENUES)
    cle = random.Random(reel).choice(possibles)
    histo.append({"reel": reel, "tenue": cle})
    REGISTRE.parent.mkdir(parents=True, exist_ok=True)
    REGISTRE.write_text(json.dumps(histo, ensure_ascii=False, indent=1))
    return cle


def avec_tenue(texte_commun: str, reel: str) -> str:
    """Le texte commun des images, avec la tenue de CE Reel à la place du sweat noir."""
    if PAR_DEFAUT not in texte_commun:
        raise ValueError("tenue par défaut introuvable dans le texte : rien ne serait changé")
    return texte_commun.replace(PAR_DEFAUT, TENUES[choisir(reel)])
