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

NEGATIF = ("bright green eyes, vivid green eyes, glowing eyes, neon eyes, "
           "emerald eyes, saturated iris, colored contact lenses, "
           "child, teenager, underage, deformed hands, extra fingers, "
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
    #: COMMENT LA PHOTO A ETE PRISE, physiquement.
    #:
    #: Ajoute le 21 septembre, sur remarque de l'operateur : « elle fait
    #: des photos amateur avec son telephone, donc elle ne peut pas etre
    #: prise en photo dans son lit avec son telephone dans la main ».
    #:
    #: Il avait raison, et le defaut etait partout : une seule scene sur
    #: douze etait realisable par Luna elle-meme. Toutes les autres
    #: supposaient quelqu'un derriere l'appareil -- et le vocabulaire le
    #: demandait explicitement (« travel magazine photography », « high
    #: fashion editorial », « luxury lifestyle photography »).
    #:
    #: Une photo sans photographe plausible est ce qui fait reconnaitre un
    #: faux compte en trois secondes. Chaque scene nomme donc son
    #: appareil et la main qui le tient.
    cadrage: str = ""




# LA VILLE DE LUNA, EN UN SEUL ENDROIT.
#
# Demande de l'operateur le 21 septembre : « essaye de mettre des lieux
# reels ». Un decor nomme -- une vraie place, une vraie gare -- ancre le
# personnage bien plus surement qu'un « cafe etudiant » generique, et
# c'est ce que font les vrais comptes.
#
# Metz est retenue par defaut : c'est la ville affichee sur son profil
# Instagram, et elle colle a une etudiante en ecole de commerce dans le
# Grand Est. Si c'est une autre ville, TOUT se change ici : les scenes
# ci-dessous composent leurs decors a partir de ces trois valeurs, elles
# ne recopient jamais un nom de lieu.
VILLE = "Metz, France"
LIEUX = {
    "cafe": "a busy cafe terrace on Place Saint-Louis in Metz, the "
            "medieval arcades and stone columns behind them",
    "campus": "the courtyard of her business school in Metz, modern "
              "glass buildings and bike racks",
    "gare": "the platform of Metz-Ville railway station, its ornate "
            "sandstone canopy overhead",
    "rue": "rue Serpenoise in Metz, shop fronts and grey pavement",
    "parc": "the banks of the Moselle near the Temple Neuf in Metz",
    "bistro": "the staff corridor of a bistro in the Metz old town",
    "salle": "a municipal gym in Metz",
}

# LES QUATRE SEULES FACONS DONT LUNA PEUT PRENDRE UNE PHOTO.
#
# Elle n'a qu'un telephone et pas de photographe. Toute image qui ne
# rentre pas dans l'une de ces cases est impossible -- et une image
# impossible est exactement ce qui trahit un compte artificiel.
#
# L'ordre compte : le bras tendu et le miroir sont les plus courants
# chez une vraie personne ; le telephone pose et l'ami qui prend la
# photo restent l'exception, sinon l'ensemble redevient un shooting.
BRAS_TENDU = ("selfie taken by herself at arm's length, her own arm "
              "visible entering the frame, slightly high angle, front "
              "camera of a phone, minor lens distortion near the edges")
MIROIR = ("mirror selfie, she is holding her phone up in front of a "
          "mirror, the phone is visible in the reflection partly hiding "
          "her face, fingerprints and dust on the mirror")
POSE = ("phone propped up against an object and shot with the self "
        "timer, fixed slightly awkward angle, she is a little too far "
        "from the camera, nothing in her hands")
GROUPE = ("group selfie held at arm's length by Luna, two or three "
          "friends leaning into the frame around her, heads close "
          "together, everyone looking at the phone, she is the closest "
          "to the camera and clearly the main subject, the others partly "
          "cropped and softly out of focus")
AMIE = ("quick snapshot taken by a friend on a phone, slightly "
        "off-centre framing, she is caught mid-movement, not posing")

SCENES = (
    # REECRITES LE 21 SEPTEMBRE, sur trois remarques de l'operateur.
    #
    # 1. « Elle fait des photos amateur avec son telephone, donc elle ne
    #    peut pas etre prise en photo dans son lit avec son telephone
    #    dans la main. » Chaque scene nomme son CADRAGE : qui tient
    #    l'appareil, et comment. Une photo sans photographe plausible est
    #    ce qui fait reconnaitre un faux compte en trois secondes.
    #
    # 2. « Elle est etudiante, elle ne peut pas se payer des shootings
    #    photo. » Le train de vie non plus : le restaurant gastronomique,
    #    le resort a piscine a debordement, la robe du soir sur un
    #    rooftop et la cuisine de designer ont disparu. Sa biographie dit
    #    « une liste d'envie plus longue que son compte en banque » --
    #    elle DESIRE ces choses, elle ne les a pas.
    #
    # 3. « Elle est tres sociable, donc si elle est au cafe elle est avec
    #    ses amies. » Six scenes sur quatorze montrent quelqu'un d'autre.
    #    Ca corrige au passage un defaut que j'avais introduit : sept
    #    selfies miroir d'affilee, monotones et toujours seule.
    #
    # Le vocabulaire de studio est banni : « editorial », « magazine »,
    # « luxury lifestyle », « glamour photography » demandaient
    # litteralement un shooting professionnel au moteur.
    Scene("cafe", "Au cafe avec les copines", TENDRE,
          f"crammed around a small table on {LIEUX['cafe']}, two friends "
          "leaning in beside her, empty cups and a laptop pushed aside, "
          "coats over the chair backs, other customers blurred behind, "
          "plain afternoon daylight, all of them laughing at something "
          "off-camera",
          "Revisions... enfin, on avait dit revisions \u2615\ufe0f",
          GROUPE),
    Scene("matin", "Selfie du matin", TENDRE,
          "in her small student bedroom, unmade bed and a drying rack "
          "visible behind her, oversized band t-shirt, hair still messy "
          "from the night, grey morning light through a single window, "
          "no plunging neckline, laughing candidly with eyes crinkled",
          "Prete a sortir \U0001f604 Tu en penses quoi de cette tenue ?",
          MIROIR),
    Scene("bureau", "Avant les cours", TENDRE,
          f"standing in {LIEUX['campus']}, oversized cream knit sweater "
          "tucked loosely into baggy wide-leg light-wash jeans, scuffed "
          "white trainers, large ecru canvas tote bag with two small "
          "charms clipped to the strap, laptop under her arm, two "
          "classmates walking past behind her, plain overcast daylight, "
          "soft closed-mouth smile",
          "Cours de finance dans dix minutes \U0001f4da Souhaite-moi bon courage.",
          AMIE),
    Scene("restaurant", "Le bar ou elle bosse", TENDRE,
          f"in {LIEUX['bistro']} where she waits tables at the weekend, "
          "black work shirt with the apron untied around her hips, "
          "shelves of glasses and a service door behind her, harsh "
          "overhead strip light, tired but content half-smile",
          "Service fini. 52 couverts et un partiel mardi \U0001fae0",
          MIROIR),
    Scene("sport", "Seance de sport", TENDRE,
          f"in the changing room of {LIEUX['salle']}, oversized cropped "
          "t-shirt over a high-neck sports top and high-waisted leggings, "
          "modest neckline not deep cut, high ponytail, post-workout "
          "flush, a friend beside her also in gym clothes, flat "
          "fluorescent lighting, both slightly out of breath and laughing",
          "Seance finie \U0001f4aa J'ai pense a toi entre deux series \U0001f605",
          GROUPE),
    Scene("voyage", "Le train du dimanche", TENDRE,
          f"on a regional train leaving {LIEUX['gare']}, forehead near "
          "the window, simple hoodie, tote bag on the seat beside her, "
          "flat winter landscape blurred outside, dull overcast daylight, "
          "quiet thoughtful expression, not smiling at the camera",
          "Deux heures de train et un dossier a finir \U0001f686",
          BRAS_TENDU),
    Scene("cuisine", "Cuisine a la maison", TENDRE,
          "in a cramped shared student kitchen, chipped worktop, "
          "mismatched pans, an oversized shirt with sleeves rolled up, "
          "cheap ingredients laid out, a flatmate reaching past her for a "
          "glass, warm evening light from a bare bulb, playful smirk",
          "Je teste une nouvelle recette \U0001f373 Tu gouterais ?",
          POSE),
    Scene("soiree", "Soiree chez des amis", TENDRE,
          "in the bathroom of a friend's flat before going out, simple "
          "fitted black dress she has clearly worn before, small gold "
          "hoops, two friends getting ready behind her, coats piled on "
          "the floor, warm yellow bathroom light, confident half-smile",
          "Alors, cette robe ? Sois honnete \U0001f457",
          AMIE),
    Scene("shopping", "Leche-vitrine", TENDRE,
          f"standing outside a shop window on {LIEUX['rue']}, oversized "
          "tailored jacket over a simple top and wide-leg trousers, "
          "chunky loafers, no shopping bags, a friend beside her pointing "
          "at something in the window, her reflection in the glass next "
          "to the price tag, flat daylight, wistful half-smile",
          "J'ai craque \U0001f6cd\ufe0f ... enfin, presque.",
          AMIE),
    Scene("promenade", "Au bord de la Moselle", TENDRE,
          f"walking along {LIEUX['parc']}, long coat over a hoodie, hands "
          "in her pockets, bare trees and grey water behind, a friend "
          "half in frame beside her, flat winter daylight, easy natural "
          "smile",
          "Une heure dehors avant de m'y remettre \U0001f342",
          AMIE),
    Scene("romantique", "Selfie romantique", TENDRE,
          "sitting on a worn sofa at home wrapped in a cheap fleece "
          "blanket, oversized knit sweater, tousled hair, soft morning "
          "light, warm playful smile, natural makeup",
          "Un petit selfie pour te faire sourire \U0001f970",
          BRAS_TENDU),
    # --- Registre SENSUEL -------------------------------------------
    # Meme regle de cadrage, et elle est ici naturelle : personne d'autre
    # n'est dans la piece, c'est precisement ce que la scene raconte.
    # Donc miroir ou telephone pose, jamais un tiers.
    Scene("costume", "Costume et deguisement", SENSUEL,
          "in her bedroom before a party, playful character costume, "
          "fully covering outfit, cheap coloured fairy lights as the only "
          "light source, confident pose",
          "Devine ce que je porte ce soir \U0001f60f",
          MIROIR),
    Scene("boudoir", "Lingerie elegante", SENSUEL,
          "seated on the edge of her own bed, elegant black lace lingerie "
          "set fully covering, sheer stockings, a robe slipping off one "
          "shoulder, dim warm bedside lamp, modest framing, no nudity",
          "Juste pour toi \U0001f48b ... et personne d'autre.",
          POSE),
    Scene("fenetre", "Lumiere de fenetre", SENSUEL,
          "standing by her bedroom window with thin curtains, fitted lace "
          "bodysuit fully covering, backlit by soft morning light, "
          "looking over her shoulder, elegant and modest, no nudity",
          "La lumiere est belle ce matin... et je pense a toi \U0001f60f",
          POSE),
    Scene("talons", "Talons et bas", SENSUEL,
          "in the hallway of her flat, elegant lingerie set fully "
          "covering with sheer stockings, a long coat held open, black "
          "heels, single warm ceiling light, no nudity",
          "Je sors... ou je reste ? A toi de choisir \U0001f48b",
          MIROIR),
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
    # LE CADRAGE PASSE EN PREMIER, avec l'apparence.
    #
    # Ce n'est pas un detail de mise en forme : les moteurs d'images
    # pondèrent le debut du prompt plus lourdement que la fin. Mettre
    # « sa propre main tient le telephone » apres trois lignes de decor
    # revient a le suggerer ; le mettre au debut revient a l'imposer.
    #
    # Et un cadrage qui n'arrive pas au moteur ne cadre rien -- c'est le
    # piege recense dans le CLAUDE.md : verifier qu'un reglage est LU ne
    # prouve rien, il faut verifier qu'il S'EXECUTE. Un test garantit
    # desormais que chaque scene a un cadrage ET qu'il se retrouve dans
    # le prompt final.
    prompt = ", ".join(x for x in (
        persona.apparence.ancre,
        scene.cadrage,
        scene.decor,
        RENDU,
        SIGNATURE,
    ) if x)
    return {
        "scene": scene.cle,
        "titre": scene.titre,
        "prompt": prompt,
        "negatif": NEGATIF,
        "graine": persona.apparence.graine,
        "legende": scene.legende,
        "registre": scene.registre,
    }
