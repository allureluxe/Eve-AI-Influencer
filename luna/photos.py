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
           "duplicate person, different face, 3d render, cgi, video game "
           "character, anime, cartoon, illustration, painting, doll, plastic "
           "skin, waxy skin, airbrushed, overly smooth skin, fake looking, "
           "excessively large breasts, exaggerated bust, deep plunging "
           "neckline, cutout cleavage design, crossed eyes, lazy eye, "
           "misaligned eyes, wall-eyed, asymmetrical eyes, strabismus, "
           "eyes looking in different directions, cgi rendered look, "
           "video game skin, beauty pageant look, overly perfect model "
           "face, instagram filter, glossy skin")

SIGNATURE = "fictional AI-generated character, not a real person"

# Le rendu, identique partout. Change le 15 sept. : le style "magazine
# editorial retouche" precedent produisait exactement ce que l'operateur a
# signale -- un rendu IA generique, trop lisse, avec des proportions
# artificielles. Vise desormais une vraie photo de tous les jours (celle
# qu'une etudiante poste ou s'envoie), pas un shooting de studio : moins de
# retouche, plus de grain et d'imperfections naturelles.
RENDU = ("shot on iPhone, candid realistic photography, natural everyday "
         "lighting, soft realistic exposure, not overexposed, not too bright, "
         "warm natural skin tones, authentic amateur photo aesthetic, looks "
         "like a real unedited phone photo of an actual person, not a "
         "professional model or beauty pageant photo, not a generated "
         "looking face, no studio lighting, no airbrushing, no "
         "over-retouching, no makeup filter, visible natural skin texture "
         "with pores, fine lines and slight imperfections up close, "
         "realistic proportions, slight natural film grain, photorealistic, "
         "high detail")


@dataclass(frozen=True)
class Scene:
    cle: str
    titre: str
    registre: str
    decor: str
    legende: str


SCENES = (
    # 15 sept., 2e passage : le sourire fige et identique d'une photo a
    # l'autre venait de l'ancre commune (retire de persona.py). Chaque scene
    # porte maintenant sa propre expression, volontairement differente.
    Scene("matin", "Selfie miroir", TENDRE,
          "candid mirror selfie, one hand in her hair, casual tied knot crop "
          "top, denim shorts, phone visible in shot, natural indoor "
          "daylight, casual lifestyle snapshot, no plunging neckline, "
          "laughing candidly with eyes crinkled, genuine spontaneous laugh",
          "Prete a sortir 😄 Tu en penses quoi de cette tenue ?"),
    Scene("bureau", "Avant les cours", TENDRE,
          "casual outfit, simple crew-neck crop top and high-waisted jeans, "
          "no plunging neckline, white sneakers, standing in a campus "
          "courtyard, backpack on one shoulder, notebook in hand, natural "
          "daylight, candid student lifestyle photography, soft "
          "closed-mouth smile, relaxed and calm expression",
          "Cours de finance dans dix minutes 📚 Souhaite-moi bon courage."),
    Scene("restaurant", "Sortie au restaurant", TENDRE,
          "seated at a fine dining table, fitted black cocktail dress, "
          "candlelight and warm bokeh, glass of red wine, delicate jewellery, "
          "smoky eye makeup, luxury lifestyle photography, warm gentle "
          "smile looking directly at the camera",
          "Cette table est trop grande sans toi en face 🍷"),
    Scene("sport", "Seance de sport", TENDRE,
          "modern gym, wearing a t-shirt or high-neck tank top and "
          "high-waisted leggings, modest scoop neckline not deep cut, "
          "natural figure, high ponytail, post-workout glow, natural gym "
          "lighting, candid fitness lifestyle photography, big genuine "
          "laughing smile, slightly out of breath",
          "Seance finie 💪 J'ai pense a toi entre deux series 😅"),
    Scene("voyage", "Voyage de luxe", TENDRE,
          "luxury resort terrace over a turquoise sea, flowing summer dress "
          "moving in the breeze, wide-brim hat, infinity pool, golden hour "
          "backlight, travel magazine photography, soft dreamy smile "
          "looking off to the side at the horizon",
          "Ce coucher de soleil serait parfait avec toi ✈️"),
    Scene("cuisine", "Cuisine a la maison", TENDRE,
          "cozy designer kitchen, oversized white shirt over bare legs, "
          "sleeves rolled up, fresh ingredients on a marble counter, warm "
          "afternoon light, relaxed candid lifestyle photography, playful "
          "smirk, concentrating on cooking, one eyebrow slightly raised",
          "Je teste une nouvelle recette 🍳 Tu gouterais ?"),
    Scene("soiree", "Tenue de soiree", TENDRE,
          "long fitted evening gown, rooftop terrace in the evening, city "
          "lights bokeh, statement earrings, elegant makeup, heels, high "
          "fashion editorial photography, confident subtle half-smile, "
          "direct eye contact",
          "Alors, cette robe ? Sois honnete 👗"),
    Scene("shopping", "Shopping", TENDRE,
          "high-end fashion boutique, chic casual outfit with a blazer and "
          "heels, shopping bags, mirror reflection, polished lifestyle "
          "editorial photography, excited open-mouth smile, holding up a "
          "shopping bag",
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
          "candid photo sitting on a sofa at home, wrapped in a soft "
          "blanket, oversized knit sweater, tousled hair, soft morning "
          "light, warm playful smile, natural makeup",
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
