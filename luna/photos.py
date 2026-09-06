"""Les photos de Luna, avec un visage qui ne change pas.

Deux choses garantissent la coherence d'une image a l'autre :

- l'ancre d'apparence (`persona.apparence.ancre`), recopiee dans chaque
  prompt ;
- la graine fixe, qui donne au generateur le meme point de depart.

Change la scene, la tenue, la lumiere : c'est toujours la meme femme.
Chaque prompt porte aussi la mention « adult woman, 30 years old » et
« fictional AI-generated character » — ce n'est pas decoratif, c'est ce
qui evite les derives et ce qui doit accompagner la publication.
"""
from __future__ import annotations

from dataclasses import dataclass

from .limites import SENSUEL, TENDRE, rang
from .persona import LUNA, Persona

NEGATIF = ("child, teenager, underage, deformed hands, extra fingers, "
           "distorted face, watermark, text, logo, low quality, blurry, "
           "duplicate person, different face")

SIGNATURE = "fictional AI-generated character, not a real person"

# Le rendu, identique partout : c'est lui qui fait la difference entre une
# image plate et une photo de studio. Objectif court, lumiere travaillee,
# peau texturee — les trois choses qui trahissent le plus une image generee
# quand elles manquent.
RENDU = ("hyperrealistic glamour photography, professional fashion shoot, "
         "85mm f/1.4 portrait lens, shallow depth of field, softbox key light "
         "with warm rim light, detailed natural skin texture with visible "
         "pores, sharp focus on the eyes, subtle film grain, high dynamic "
         "range, magazine editorial retouching, 8k")


@dataclass(frozen=True)
class Scene:
    cle: str
    titre: str
    registre: str
    decor: str
    legende: str


SCENES = (
    Scene("matin", "Selfie avant le bureau", TENDRE,
          "morning mirror selfie in a bright modern apartment, silk blouse "
          "and pencil skirt, coffee cup in hand, soft daylight through large "
          "windows, glossy hair, phone held up, candid lifestyle framing",
          "Prete pour la journee ☕ Tu me souhaites bonne chance ?"),
    Scene("bureau", "Tenue professionnelle", TENDRE,
          "elegant fitted trouser suit over a silk camisole, standing in a "
          "modern glass office at golden hour, city skyline behind, stiletto "
          "heels, confident posture, corporate editorial photography",
          "Reunion dans dix minutes 💼 Souhaite-moi bon courage."),
    Scene("restaurant", "Sortie au restaurant", TENDRE,
          "seated at a fine dining table, fitted black cocktail dress, "
          "candlelight and warm bokeh, glass of red wine, delicate jewellery, "
          "smoky eye makeup, luxury lifestyle photography",
          "Cette table est trop grande sans toi en face 🍷"),
    Scene("sport", "Seance de sport", TENDRE,
          "modern gym at blue hour, matching sports bra and high-waisted "
          "leggings, toned figure, high ponytail, post-workout glow, backlit "
          "by floor-to-ceiling windows, fitness editorial photography",
          "Seance finie 💪 J'ai pense a toi entre deux series 😅"),
    Scene("voyage", "Voyage de luxe", TENDRE,
          "luxury resort terrace over a turquoise sea, flowing summer dress "
          "moving in the breeze, wide-brim hat, infinity pool, golden hour "
          "backlight, travel magazine photography",
          "Ce coucher de soleil serait parfait avec toi ✈️"),
    Scene("cuisine", "Cuisine a la maison", TENDRE,
          "cozy designer kitchen, oversized white shirt over bare legs, "
          "sleeves rolled up, fresh ingredients on a marble counter, warm "
          "afternoon light, relaxed candid lifestyle photography",
          "Je teste une nouvelle recette 🍳 Tu gouterais ?"),
    Scene("soiree", "Tenue de soiree", TENDRE,
          "long fitted evening gown with a slit, rooftop terrace at night, "
          "city lights bokeh, statement earrings, glamorous makeup, stiletto "
          "heels, high fashion editorial photography",
          "Alors, cette robe ? Sois honnete 👗"),
    Scene("shopping", "Shopping", TENDRE,
          "high-end fashion boutique, chic casual outfit with a blazer and "
          "heels, shopping bags, mirror reflection, polished lifestyle "
          "editorial photography",
          "J'ai craque 🛍️ ... enfin, presque."),
    Scene("costume", "Costume et deguisement", SENSUEL,
          "playful character costume portrait, theatrical fully covering "
          "outfit, stage lighting with coloured gels, confident pose, "
          "tasteful glamour photography",
          "Devine ce que je porte ce soir 😏"),
    Scene("boudoir", "Lingerie elegante", SENSUEL,
          "tasteful boudoir portrait seated on a velvet armchair, elegant "
          "black lace lingerie set fully covering, sheer stockings and high "
          "heels, silk robe slipping off one shoulder, dim warm bedroom "
          "light, artistic glamour editorial, modest framing, no nudity",
          "Juste pour toi 💋 ... et personne d'autre."),
    Scene("fenetre", "Lumiere de fenetre", SENSUEL,
          "standing by a tall window with sheer curtains, fitted lace "
          "bodysuit fully covering, backlit by soft morning light, looking "
          "over her shoulder, hair catching the light, fine art boudoir "
          "photography, elegant and modest, no nudity",
          "La lumiere est belle ce matin... et je pense a toi 😏"),
    Scene("talons", "Talons et bas", SENSUEL,
          "full length editorial portrait in a hotel corridor, elegant "
          "lingerie set fully covering with sheer stockings, long fur coat "
          "held open, black stiletto heels, moody directional lighting, "
          "high fashion glamour photography, no nudity",
          "Je sors... ou je reste ? A toi de choisir 💋"),
    Scene("romantique", "Selfie romantique", TENDRE,
          "close-up cozy selfie in bed under a soft duvet, oversized knit "
          "sweater, tousled hair, soft morning light, affectionate playful "
          "expression, natural makeup",
          "Un petit selfie pour te faire sourire 🥰"),
)

SCENES_PAR_CLE = {s.cle: s for s in SCENES}


def scenes_autorisees(registre: str) -> tuple[Scene, ...]:
    return tuple(s for s in SCENES if rang(s.registre) <= rang(registre))


def prompt_photo(cle: str, registre: str = TENDRE,
                 persona: Persona = LUNA) -> dict:
    """Le prompt complet d'une photo, pret pour le generateur."""
    scene = SCENES_PAR_CLE.get(cle)
    if scene is None:
        raise KeyError(f"scene inconnue : {cle}")
    if rang(scene.registre) > rang(registre):
        raise PermissionError(
            f"la scene « {scene.titre} » demande le registre {scene.registre}")
    prompt = ", ".join((
        persona.apparence.ancre,
        scene.decor,
        RENDU,
        SIGNATURE,
    ))
    return {
        "scene": scene.cle,
        "titre": scene.titre,
        "prompt": prompt,
        "negatif": NEGATIF,
        "graine": persona.apparence.graine,
        "legende": scene.legende,
        "registre": scene.registre,
    }
