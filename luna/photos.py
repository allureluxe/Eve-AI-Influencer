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


@dataclass(frozen=True)
class Scene:
    cle: str
    titre: str
    registre: str
    decor: str
    legende: str


SCENES = (
    Scene("matin", "Selfie avant le bureau", TENDRE,
          "morning selfie in a bright Parisian apartment, soft daylight, "
          "business blouse, coffee cup, phone mirror selfie framing",
          "Prete pour la journee ☕ Tu me souhaites bonne chance ?"),
    Scene("bureau", "Tenue professionnelle", TENDRE,
          "elegant tailored suit in a modern glass office, city skyline "
          "behind, confident posture, editorial corporate photography",
          "Reunion dans dix minutes 💼 Souhaite-moi bon courage."),
    Scene("restaurant", "Sortie au restaurant", TENDRE,
          "fine dining restaurant, warm candlelight, elegant dress, glass "
          "of wine, bokeh background, luxury lifestyle photography",
          "Cette table est trop grande sans toi en face 🍷"),
    Scene("sport", "Seance de sport", TENDRE,
          "modern gym, sportswear, ponytail, post-workout glow, natural "
          "light through large windows",
          "Seance finie 💪 J'ai pense a toi entre deux series 😅"),
    Scene("voyage", "Voyage de luxe", TENDRE,
          "luxury resort terrace overlooking the sea, summer dress, sun "
          "hat, infinity pool, golden hour, travel magazine style",
          "Ce coucher de soleil serait parfait avec toi ✈️"),
    Scene("cuisine", "Cuisine a la maison", TENDRE,
          "cozy home kitchen, apron over a shirt, fresh ingredients on the "
          "counter, warm afternoon light, candid lifestyle photography",
          "Je teste une nouvelle recette 🍳 Tu gouterais ?"),
    Scene("soiree", "Tenue de soiree", TENDRE,
          "evening gown, rooftop party at night, city lights, elegant "
          "jewelry, glamorous fashion photography",
          "Alors, cette robe ? Sois honnete 👗"),
    Scene("shopping", "Shopping", TENDRE,
          "high-end fashion boutique, shopping bags, chic casual outfit, "
          "mirror reflection, lifestyle editorial",
          "J'ai craque 🛍️ ... enfin, presque."),
    Scene("costume", "Costume et deguisement", SENSUEL,
          "playful costume portrait, theatrical outfit, stage-style "
          "lighting, tasteful glamour photography, fully covered outfit",
          "Devine ce que je porte ce soir 😏"),
    Scene("boudoir", "Lingerie elegante", SENSUEL,
          "tasteful boudoir portrait, elegant lace lingerie set, silk robe "
          "over the shoulders, dim warm bedroom light, artistic fashion "
          "editorial, modest and covered, no nudity",
          "Juste pour toi 💋 ... et personne d'autre."),
    Scene("romantique", "Selfie romantique", TENDRE,
          "close-up cozy selfie in bed under a blanket, oversized sweater, "
          "soft morning light, affectionate expression",
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
        "photorealistic, 85mm portrait lens, shallow depth of field, "
        "natural skin texture, high detail",
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
