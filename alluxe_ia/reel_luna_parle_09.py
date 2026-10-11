"""Reel 09 : Luna PARLE — « 3 AUTRES prompts pour transformer ta photo » (11 oct. 2026).

La suite promise par la légende du Reel 08 (« Abonne-toi : demain, 3 autres »).
Même chaîne que le 08 (alluxe_ia/reel_luna_parle.py) : on ne remplace que ce
qui change d'un épisode à l'autre — textes, scènes, transformations, dossier.

    python3 alluxe_ia/reel_luna_parle_09.py voix images video levres montage

Rien n'est publié par ce script.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from alluxe_ia import reel_luna_parle as r  # noqa: E402

r.ID_REEL = "09-luna-3-autres-prompts"
r.DOSSIER = r.RACINE / "data/alluxe_ia/reel_luna_parle_09"

r.SCENE_PARLE = (
    " She holds the phone at arm's length, framed from mid-chest up, looking straight "
    "into the lens with an excited, playful smile, mouth slightly open as if about to "
    "speak. Bright Parisian apartment behind her, white walls, a bookshelf and a big "
    "window, soft natural light. Both hands are out of the frame."
)

r.SCENE_AVANT = (
    " Ordinary unedited casual phone photo taken by a friend: she sits on a bench in "
    "a Paris park in autumn, slightly flat overcast light, people passing in the "
    "background, average framing. Natural, not professional."
)

r.TRANSFOS = [
    ("1_linkedin", "PHOTO PRO LINKEDIN",
     "Transforme cette photo en photo de profil LinkedIn professionnelle : tenue "
     "élégante, fond de bureau flou, lumière naturelle. Garde mon visage identique.",
     "Transform this photo into a professional LinkedIn headshot of the same woman: "
     "elegant blazer, softly blurred modern office background, natural window light, "
     "head and shoulders, confident friendly smile, same face exactly. Photorealistic."),
    ("2_figurine", "TA FIGURINE",
     "Fais de moi une figurine de collection dans sa boîte, avec mon prénom dessus et "
     "mes accessoires préférés. Garde mon visage identique.",
     "Turn the same woman into a realistic collectible action figure inside a premium "
     "blister toy box, the figure has her exact face and hair, fully clothed in a "
     "cosy outfit. The box label reads LUNA in bold letters. Small accessories in "
     "their own slots: a laptop, a coffee cup, a smartphone. Studio product photo."),
    ("3_noel", "CARTE DE NOËL",
     "Mets-moi dans la même pose sous la neige, à Paris, avec des lumières de Noël, "
     "comme une carte de vœux. Garde mon visage identique.",
     "Show the same woman in the same pose sitting on the same park bench, now in "
     "Paris at night in winter: falling snow, warm Christmas lights in the trees, "
     "cosy winter coat and scarf, magical festive greeting-card atmosphere, same "
     "face exactly. Photorealistic."),
]

r.VOIX = {
    "accroche": "Hier, trois prompts. Aujourd'hui, trois autres encore plus fous !",
    "1_linkedin": "Un : ta photo LinkedIn pro, sans photographe.",
    "2_figurine": "Deux : ta propre figurine, dans sa boîte.",
    "3_noel": "Trois : ta carte de Noël… sous la neige.",
    "fin": "Les prompts sont dans la légende. Abonne-toi !",
}

r.LEGENDE = (
    "3 AUTRES prompts pour transformer ta photo avec ChatGPT 📸👇\n\n"
    + "\n\n".join(f"{i}. {titre.capitalize()} :\n« {prompt} »"
                  for i, (_, titre, prompt, _) in enumerate(r.TRANSFOS, 1))
    + "\n\nComment faire : ouvre ChatGPT, ajoute ta photo, colle le prompt.\n\n"
    "💾 Enregistre ce Reel pour garder les 3 prompts.\n"
    "👉 Abonne-toi pour la suite.\n"
    "📎 Les 12 prompts du kit, gratuits : lien dans ma bio\n\n"
    "Luna est un personnage créé avec l'IA.\n"
    "#chatgpt #ia #intelligenceartificielle #astuceia #photo #prompt #iafrance #noel"
)

if __name__ == "__main__":
    etapes = {"voix": r.voix, "images": r.images, "video": r.video,
              "levres": r.levres, "montage": r.montage}
    for nom in (sys.argv[1:] or list(etapes)):
        etapes[nom]()
