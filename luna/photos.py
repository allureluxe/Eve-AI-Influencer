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

# ------------------------------------------------------------------
# CE QUI FAIT QU'UNE PHOTO A L'AIR VRAIE — 26 septembre.
#
# Verdict de l'operateur devant les quatre premieres images du
# pipeline, toutes reussies techniquement : « c'est pas reel du tout ».
# Il avait raison, et le defaut n'etait pas dans le moteur.
#
# TOUTES NOS PHOTOS ETAIENT DES PHOTOS DE MAGAZINE. Lumiere doree de
# fin de journee, Fourviere cadree derriere, peau parfaite, corps de
# sportive, sourire impeccable, cadrage centre. Chacune est une belle
# image — et c'est exactement ce qui trahit une generation : personne
# n'a quarante photos parfaitement eclairees sur son telephone.
#
# `RENDU` ci-dessus disait deja « pas de studio, pas de retouche ». Ca
# ne suffisait pas, parce que la SCENE continuait de demander un
# coucher de soleil devant un monument. On ne rattrape pas un decor de
# carte postale avec une mention de grain de peau.
#
# Mesure, une image contre une : meme moteur, meme ancre, meme visage —
# le registre « flash direct dans un couloir blanc, front qui brille,
# cheveux pas brosses » passe pour vrai la ou « quai de Saone a l'heure
# doree » passe pour une publicite.
#
# Ces trois listes servent a tirer un contexte INGRAT, et c'est
# volontaire. Les belles lumieres restent disponibles — une vraie
# personne en a quelques-unes — mais elles doivent etre l'exception.

#: La lumiere, et elle est rarement flatteuse dans la vraie vie.
LUMIERES = (
    "harsh direct camera flash at night, slightly overexposed face, hard "
    "shadow on the wall behind her, shiny forehead",
    "dull flat grey daylight from an overcast sky, no shadows, slightly "
    "underexposed",
    "yellow indoor ceiling light in the evening, warm and unflattering, "
    "slightly grainy",
    "backlit against a bright window so her face is too dark",
    "cold white supermarket or corridor lighting",
    "late afternoon light through a car window, half her face in shadow",
    # LES DEUX SEULES BELLES LUMIERES, en minorite assumee.
    "soft late afternoon sunlight, pleasant but ordinary",
    "bright midday sun, squinting slightly",
)

#: Les endroits sans interet, ou se prend la majorite des vraies photos.
LIEUX_BANALS = (
    "a plain apartment hallway with white walls and a door behind her",
    "her small student bedroom, an unmade bed and clothes on a chair "
    "behind her",
    "the passenger seat of a parked car",
    "a supermarket aisle",
    "a bus shelter on an ordinary street",
    "a cramped bathroom with a mirror and toiletries on the sink",
    "a tiny kitchen with dishes in the sink behind her",
    "a train seat, the window grey and blurred behind her",
    "a bland office-like classroom with rows of empty chairs",
    "a stairwell with painted concrete walls",
)

#: Les defauts d'une vraie photo de telephone. Sans eux, l'image reste
#: trop propre meme dans un decor banal.
DEFAUTS = (
    "framing is crooked and off-centre, she is not posing, caught "
    "mid-sentence with an awkward half expression, slight motion blur, "
    "low-quality phone camera, visible digital noise and JPEG "
    "compression artefacts, this is a boring photo nobody would post",
    "slightly out of focus, she moved when the photo was taken, thumb "
    "partly over the corner of the lens, nothing is centred",
    "taken too quickly, her eyes half closed, unflattering angle from "
    "slightly below, ordinary body, not athletic, not a model",
)

#: La peau, en detail. C'est le premier endroit ou l'oeil detecte une
#: generation : trop lisse, trop egale, trop symetrique.
PEAU_REELLE = (
    "visible skin texture with enlarged pores, slight redness around the "
    "nose and chin, a small blemish, uneven skin tone, no makeup at all, "
    "hair flat and unbrushed"
)


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
    #: LA COIFFURE DU JOUR. Portee par la scene, pas par l'identite --
    #: voir `COIFFURES` plus haut et le commentaire de `persona.ancre`.
    coiffure: str = ""




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
    # LA PORTE DES ALLEMANDS -- reelle, gratuite, et photogenique.
    # C'est le premier episode de la serie « Metz gratuit » : les
    # endroits qu'une etudiante fauchee peut vraiment s'offrir.
    "porte": "the Porte des Allemands in Metz at golden hour, the "
             "medieval stone gatehouse and its towers reflected in "
             "the Seille below, a few locals walking on the bridge, "
             "warm low sunlight on the old stone",
    # LA PISCINE EST CELLE D'UNE AMIE, UN JOUR D'ANNIVERSAIRE.
    #
    # Precision de l'operateur le 25 septembre : « elle est sur une
    # piscine a une fete d'anniversaire d'une de ses amies ». C'est plus
    # juste que la piscine municipale que j'avais ecrite, et sur deux
    # plans a la fois.
    #
    # Une etudiante n'a pas de piscine -- mais elle est INVITEE, et ca
    # ne coute rien. Le decor cesse d'etre hors de ses moyens sans
    # cesser d'etre joli, ce qui etait tout le probleme.
    #
    # Et ca sert la deuxieme consigne : « elle est tres sociable, donc
    # si elle est au cafe elle est avec ses amies ». Une piscine vide
    # un jour de semaine n'allait pas avec ce personnage. Une fete, si.
    "piscine": "the small garden pool of a friend's family house, a "
               "birthday party going on around it -- paper garlands "
               "strung between two trees, a folding table with plastic "
               "cups and a half-eaten cake, towels and a speaker on the "
               "grass, three or four friends in swimwear talking and "
               "laughing nearby",
}

# LES COIFFURES, UNE PAR SCENE.
#
# « De nos jours on ne va pas au coiffeur tous les jours. » Une vraie
# personne se coiffe en trente secondes avec ce qu'elle a sous la main,
# et sa tete change d'un jour a l'autre. Aucune de ces coiffures ne
# demande un salon ; plusieurs sont franchement negligees, et c'est
# voulu.
#
# La longueur et la couleur restent dans l'ancre (persona.py) : ce sont
# elles qui font reconnaitre Luna. La coiffure, elle, doit varier --
# sinon chaque photo ressemble a la precedente.
CHIGNON = ("hair scraped up into a messy bun with a claw clip, loose "
           "strands falling around her face")
QUEUE = "hair pulled back into a simple high ponytail, a few flyaways"
LACHES = "hair loose and a little flat, second-day hair, not styled"
MOUILLES = "hair still damp from the shower, pushed back, darker at the roots"
TRESSE = "hair in a quick loose plait over one shoulder, already coming undone"
BONNET = "hair tucked under a knitted beanie, ends sticking out"
SOIGNES = ("hair brushed out and loosely waved, the one evening she "
           "made an effort")

# LA GARDE-ROBE — ajoutee le 26 septembre, sur une remarque de l'operateur.
#
# « Ce sont les memes vetements aussi, il faut que ce soit des vetements
# differents a chaque fois. » Il avait raison : la tenue etait ecrite en
# dur dans chaque scene, donc Luna portait le meme sweat noir, le meme
# jean clair et le meme tote bag sur toutes les photos. Une femme qui ne
# se change jamais, ca se voit a la deuxieme publication.
#
# CE QUI VARIE ET CE QUI NE VARIE PAS. Le visage, la couleur et la
# longueur des cheveux vivent dans l'ancre (`persona.py`) : ce sont eux
# qui font reconnaitre Luna, ils ne bougent jamais. La coiffure, le
# cadrage et maintenant la tenue tournent : ce sont eux qui font qu'une
# photo n'est pas la precedente.
#
# UNE VRAIE PERSONNE REMET SES VETEMENTS. Le piege serait de generer une
# tenue neuve a chaque fois : quarante tenues differentes en quarante
# photos, c'est une garde-robe de mannequin, pas d'etudiante qui paie
# ses etudes en servant le week-end. Douze tenues qui reviennent, c'est
# une vraie armoire — et reconnaitre un vetement d'une photo a l'autre
# rend le personnage plus credible, pas moins.
#
# ELLES SONT CLASSEES PAR CONTEXTE, et c'est le point important : une
# tenue de cours au Luxembourg n'est pas une tenue de quai de Saone un
# dimanche. Piocher au hasard dans un seul sac produirait des photos ou
# elle est en tailleur pour aller chercher le pain.
# LE REGISTRE — pose le 26 septembre, apres un premier jet trop sage.
#
# L'operateur, devant la premiere garde-robe : « les vetements font trop
# serieux, elle est jeune et sexy, oublie pas ». Il avait raison :
# j'avais habille une femme de trente-cinq ans qui va au bureau — gros
# pull, chemisier, blazer. Luna a 25 ans, elle est etudiante, et
# l'accroche du compte passe par la.
#
# LA LIMITE EST CELLE DE L'OPERATEUR, ecrite par lui le 25 septembre :
# « aucun contenu erotique ou pornographique, la seule chose qu'elle
# pourra faire sera d'etre sexy pour attirer l'oeil, ca plus son
# histoire, ca marche. »
#
# Ce que ca autorise : des coupes ajustees, des hauts courts, des jupes,
# des robes, des epaules et des jambes — ce que porte n'importe quelle
# fille de 25 ans un samedi. Ce que ca exclut, et qui a deja ete refuse
# plusieurs fois dans ce projet : la lingerie, la transparence, les
# poses suggestives.
#
# ET LE BUDGET RESTE CELUI D'UNE ETUDIANTE qui sert le week-end pour
# payer ses cours. Des pieces courantes et bon marche, pas du createur :
# c'est aussi ce qui la rend credible.
QUOTIDIEN = (
    "a fitted cropped white top and high-waisted straight jeans, white "
    "trainers, a small shoulder bag",
    "a tight ribbed tank top tucked into low-rise cargo trousers, a thin "
    "gold chain, trainers",
    "an oversized denim jacket worn open over a fitted cropped top, high-"
    "waisted jeans, small hoop earrings",
    "a short black tennis skirt with a simple fitted t-shirt and trainers, "
    "bare legs",
    "a soft fitted bodysuit in a neutral colour with wide-leg jeans, hair "
    "down, minimal jewellery",
    "an oversized grey hoodie worn over tiny denim shorts, long bare legs, "
    "white socks and trainers",
)
ECOLE = (
    "a cropped black blazer over a fitted white top, high-waisted straight "
    "trousers, a laptop bag, dressed up but still young",
    "a short fitted knitted top with tailored trousers and small heeled "
    "boots, one delicate necklace",
    "a pale blue shirt knotted at the waist over a fitted top, high-"
    "waisted jeans, sleeves rolled up",
)
SORTIE = (
    "a short black slip dress with thin straps, simple heeled boots, one "
    "delicate necklace, hair down",
    "a fitted corset-style top with black leather-look trousers and "
    "heeled boots, small hoop earrings",
    "a short fitted dress in a deep colour with bare shoulders, simple "
    "heels, the one evening she made an effort",
    "a satin cami top under a cropped leather-look jacket, tight black "
    "jeans, hair loose",
)
DETENTE = (
    "a cropped sports top and high-waisted gym leggings, a gym bag, "
    "slightly flushed from training, hair up",
    "an oversized faded t-shirt worn as a nightshirt over shorts, bare "
    "legs, no makeup at all, at home",
)
ETE = (
    "a short floaty summer dress with thin straps and flat sandals, tanned "
    "shoulders",
    "a fitted cropped top and denim shorts, sunglasses pushed up into her "
    "hair, sandals",
)
#: Toutes les tenues, pour les scenes ou le contexte ne tranche pas.
#: Le quotidien pese le plus lourd : c'est 90 % de la vie d'une
#: etudiante, et un compte ou chaque photo est une sortie du samedi soir
#: ne ressemble a la vie de personne.
GARDE_ROBE = QUOTIDIEN + QUOTIDIEN + ECOLE + SORTIE + DETENTE + ETE

#: Les coiffures, reunies pour pouvoir en tirer une. Elles existaient
#: depuis le 21 septembre mais chacune dans son coin : rien ne permettait
#: d'en choisir une au hasard, donc en pratique on reecrivait toujours la
#: meme dans le prompt.
COIFFURES = (CHIGNON, QUEUE, LACHES, MOUILLES, TRESSE, BONNET, SOIGNES)

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

# DEHORS ET DEDANS NE PERMETTENT PAS LES MEMES CADRAGES — 26 septembre.
#
# Le miroir demande un miroir : il n'existe pas sur un quai de Saone.
# Tirer au hasard dans les cinq produirait une selfie-miroir en pleine
# rue, c'est-a-dire precisement l'image impossible que ce bloc interdit.
#
# LES POIDS SUIVENT LA VIE REELLE, et l'ordre du commentaire ci-dessus :
# le bras tendu domine largement, l'ami qui prend la photo est frequent,
# le telephone pose et la photo de groupe restent l'exception. Un compte
# ou chaque image est cadree par quelqu'un d'autre redevient un shooting.
CADRAGES_DEHORS = (BRAS_TENDU, BRAS_TENDU, BRAS_TENDU,
                   AMIE, AMIE, POSE, GROUPE)
CADRAGES_DEDANS = (BRAS_TENDU, BRAS_TENDU, MIROIR, MIROIR, POSE, GROUPE)

# CE QU'AUCUNE PHOTO DE LUNA NE DOIT ETRE.
#
# Ajoute le 26 septembre, sur une remarque de l'operateur devant les deux
# premieres images produites par le pipeline : « la photo ne fait pas
# reel, personne ne se prend en photo de cette position ». Il avait
# raison, et le defaut ne venait pas du moteur : mon prompt demandait
# « elle se retourne vers l'objectif par-dessus son epaule », qui EXIGE
# quelqu'un derriere elle avec un appareil.
#
# La regle des quatre cadrages existait depuis le 21 septembre. Elle
# etait ecrite, elle etait juste, et rien ne l'executait — le meme piege
# que ce depot raconte sept fois. Ces interdictions sont la pour qu'un
# prompt ecrit a la main ne puisse plus la contourner sans le vouloir.
POSES_INTERDITES = (
    "not looking back over her shoulder at the camera, "
    "not a posed portrait, not a fashion shoot, "
    "no professional photographer, no studio lighting, "
    "not perfectly centred, not perfectly composed"
)

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
    # LES TROIS PREMIERES PUBLICATIONS -- demandees le 25 septembre.
    #
    # LE DECALAGE EST DANS LA LEGENDE, PAS DANS LA PHOTO.
    #
    # Choix de l'operateur le 25 septembre, parmi trois pistes. Une belle
    # photo fait un « j'aime » ; une histoire fait un abonne. Luna en a
    # deja une, et c'est la meilleure qu'elle puisse avoir : etudiante en
    # FINANCE et fauchee -- quelqu'un qui etudie l'argent et qui n'en a
    # pas.
    #
    # La piscine, le gateau, les guirlandes : tout ca fait joli et ne
    # raconte rien. C'est la legende qui casse le glamour et installe le
    # personnage des le premier post. « La piscine est a Mai. Moi j'ai un
    # Velux et un ventilo a 12 euros. » On suit quelqu'un pour ce qu'il
    # assume, pas pour ce qu'il montre.
    #
    # « Attention, les premieres sont tres importantes. » Elles le sont
    # doublement : ce sont elles qui decident si quelqu'un s'abonne, et
    # ce sont elles qu'on verra encore dans un an en haut du profil.
    #
    # Trois roles distincts, et c'est voulu :
    #   - PROFIL  : le visage, reconnaissable, aucune ambiguite
    #   - STORY   : l'instant, imparfait, qui prouve qu'elle est reelle
    #   - PREMIER : celle qui donne envie de s'abonner
    # LA SERIE « METZ GRATUIT » -- les deux idees combinees, sur sa
    # demande du 25 septembre : « l'idee de Metz est pas mal aussi,
    # compile la 1 et la 3 ».
    #
    # Elles se renforcent au lieu de se diluer. Le decalage (« je suis
    # fauchee ») donne la VOIX ; Metz donne le SUJET et, surtout, une
    # raison de revenir -- un episode numerote se suit, une jolie photo
    # se regarde une fois.
    #
    # Et ca amene de vraies personnes de la region, qui reconnaissent
    # l'endroit et commentent. Un abonne local vaut dix curieux.
    #
    # La contrainte qui tient toute la serie : chaque lieu doit etre
    # GRATUIT. C'est elle qui rend le personnage credible -- une
    # etudiante qui dit « entree 0 euro » et qui filme un rooftop a
    # 15 euros le verre ne trompe personne.
    Scene("metz_gratuit", "Metz gratuit #1 -- la Porte des Allemands", TENDRE,
          f"standing on the bridge in front of {LIEUX['porte']}, in a "
          "plain oversized sweatshirt and jeans, canvas tote over one "
          "shoulder, turning back towards the camera mid-step, not "
          "posing, the monument filling the background behind her",
          "Metz gratuit #1 \u2014 la Porte des Allemands au coucher du soleil. "
          "Entr\u00e9e : 0\u20ac. Mon budget sorties du mois : 0\u20ac aussi \u2600\ufe0f",
          AMIE, LACHES),
    Scene("piscine_profil", "Photo de profil -- anniversaire au bord de la piscine", TENDRE,
          f"sitting on the tiled edge of {LIEUX['piscine']}, feet in the "
          "water, wearing a simple colourful patterned bikini, a plain "
          "towel bunched beside her, shoulders relaxed, looking straight "
          "at the camera with an easy unforced smile, late afternoon "
          "summer light, no posing, no pout",
          "Rappel : la piscine est \u00e0 Ma\u00ef. Moi j'ai un Velux et un ventilo \u00e0 12\u20ac \u2600\ufe0f",
          AMIE, QUEUE),
    # LA MEME SCENE A DEUX -- demandee le 25 septembre : « tu mets une
    # amie a cote d'elle, genre on les prend toutes les deux en photo au
    # bord de la piscine ».
    #
    # Elle existe SEPAREMENT de la version seule, et ce n'est pas une
    # redondance : ce sont deux photos differentes d'une meme journee,
    # et c'est exactement ce qu'un vrai compte publie. Une personne
    # seule a tous ses posts se reconnait tout de suite.
    #
    # L'amie n'est pas un figurant flou du decor : elle est DANS le
    # cadre, a la meme distance, en train de faire quelque chose. Une
    # « amie » qu'on devine derriere n'a jamais fait croire a personne
    # qu'une photo etait vraie.
    Scene("piscine_duo", "Anniversaire -- a deux au bord de la piscine", TENDRE,
          f"sitting side by side on the edge of {LIEUX['piscine']}, both "
          "of them with their feet in the water, Luna in a simple "
          "colourful patterned bikini and her friend in a plain one-piece "
          "swimsuit, shoulders touching, both turned towards the camera "
          "mid-laugh, the friend's arm slung around her, wet hair, late "
          "afternoon summer light",
          "24 ans, et elle nous a tous pouss\u00e9s dans l'eau. La prochaine fois c'est moi qui tiens le t\u00e9l\u00e9phone \U0001f4f1\U0001f480",
          AMIE, MOUILLES),
    Scene("piscine_story", "Story -- pieds dans l'eau", TENDRE,
          f"at {LIEUX['piscine']}, phone held low and pointed down at "
          "her own feet dangling in the blue water, her legs and the "
          "ripples filling most of the frame, her face not visible or "
          "only partly at the very top, slightly crooked framing, "
          "harsh midday sun, grainy",
          "Elles chantent encore. Moi je bouge plus \U0001f60c",
          BRAS_TENDU, QUEUE),
    Scene("cafe", "Au cafe avec les copines", TENDRE,
          f"crammed around a small table on {LIEUX['cafe']}, two friends "
          "leaning in beside her, empty cups and a laptop pushed aside, "
          "coats over the chair backs, other customers blurred behind, "
          "plain afternoon daylight, all of them laughing at something "
          "off-camera",
          "Revisions... enfin, on avait dit revisions \u2615\ufe0f",
          GROUPE, QUEUE),
    Scene("matin", "Selfie du matin", TENDRE,
          "in her small student bedroom, unmade bed and a drying rack "
          "visible behind her, oversized band t-shirt, hair still messy "
          "from the night, grey morning light through a single window, "
          "no plunging neckline, laughing candidly with eyes crinkled",
          "Prete a sortir \U0001f604 Tu en penses quoi de cette tenue ?",
          MIROIR, MOUILLES),
    Scene("bureau", "Avant les cours", TENDRE,
          f"standing in {LIEUX['campus']}, oversized cream knit sweater "
          "tucked loosely into baggy wide-leg light-wash jeans, scuffed "
          "white trainers, large ecru canvas tote bag with two small "
          "charms clipped to the strap, laptop under her arm, two "
          "classmates walking past behind her, plain overcast daylight, "
          "soft closed-mouth smile",
          "Cours de finance dans dix minutes \U0001f4da Souhaite-moi bon courage.",
          AMIE, CHIGNON),
    Scene("restaurant", "Le bar ou elle bosse", TENDRE,
          f"in {LIEUX['bistro']} where she waits tables at the weekend, "
          "black work shirt with the apron untied around her hips, "
          "shelves of glasses and a service door behind her, harsh "
          "overhead strip light, tired but content half-smile",
          "Service fini. 52 couverts et un partiel mardi \U0001fae0",
          MIROIR, CHIGNON),
    Scene("sport", "Seance de sport", TENDRE,
          f"in the changing room of {LIEUX['salle']}, oversized cropped "
          "t-shirt over a high-neck sports top and high-waisted leggings, "
          "modest neckline not deep cut, high ponytail, post-workout "
          "flush, a friend beside her also in gym clothes, flat "
          "fluorescent lighting, both slightly out of breath and laughing",
          "Seance finie \U0001f4aa J'ai pense a toi entre deux series \U0001f605",
          GROUPE, QUEUE),
    Scene("voyage", "Le train du dimanche", TENDRE,
          f"on a regional train leaving {LIEUX['gare']}, forehead near "
          "the window, simple hoodie, tote bag on the seat beside her, "
          "flat winter landscape blurred outside, dull overcast daylight, "
          "quiet thoughtful expression, not smiling at the camera",
          "Deux heures de train et un dossier a finir \U0001f686",
          BRAS_TENDU, BONNET),
    Scene("cuisine", "Cuisine a la maison", TENDRE,
          "in a cramped shared student kitchen, chipped worktop, "
          "mismatched pans, an oversized shirt with sleeves rolled up, "
          "cheap ingredients laid out, a flatmate reaching past her for a "
          "glass, warm evening light from a bare bulb, playful smirk",
          "Je teste une nouvelle recette \U0001f373 Tu gouterais ?",
          POSE, TRESSE),
    Scene("soiree", "Soiree chez des amis", TENDRE,
          "in the bathroom of a friend's flat before going out, simple "
          "fitted black dress she has clearly worn before, small gold "
          "hoops, two friends getting ready behind her, coats piled on "
          "the floor, warm yellow bathroom light, confident half-smile",
          "Alors, cette robe ? Sois honnete \U0001f457",
          AMIE, SOIGNES),
    Scene("shopping", "Leche-vitrine", TENDRE,
          f"standing outside a shop window on {LIEUX['rue']}, oversized "
          "tailored jacket over a simple top and wide-leg trousers, "
          "chunky loafers, no shopping bags, a friend beside her pointing "
          "at something in the window, her reflection in the glass next "
          "to the price tag, flat daylight, wistful half-smile",
          "J'ai craque \U0001f6cd\ufe0f ... enfin, presque.",
          AMIE, LACHES),
    Scene("promenade", "Au bord de la Moselle", TENDRE,
          f"walking along {LIEUX['parc']}, long coat over a hoodie, hands "
          "in her pockets, bare trees and grey water behind, a friend "
          "half in frame beside her, flat winter daylight, easy natural "
          "smile",
          "Une heure dehors avant de m'y remettre \U0001f342",
          AMIE, BONNET),
    Scene("romantique", "Selfie romantique", TENDRE,
          "sitting on a worn sofa at home wrapped in a cheap fleece "
          "blanket, oversized knit sweater, tousled hair, soft morning "
          "light, warm playful smile, natural makeup",
          "Un petit selfie pour te faire sourire \U0001f970",
          BRAS_TENDU, LACHES),
    # --- Registre SENSUEL -------------------------------------------
    # Meme regle de cadrage, et elle est ici naturelle : personne d'autre
    # n'est dans la piece, c'est precisement ce que la scene raconte.
    # Donc miroir ou telephone pose, jamais un tiers.
    Scene("costume", "Costume et deguisement", SENSUEL,
          "in her bedroom before a party, playful character costume, "
          "fully covering outfit, cheap coloured fairy lights as the only "
          "light source, confident pose",
          "Devine ce que je porte ce soir \U0001f60f",
          MIROIR, SOIGNES),
    Scene("boudoir", "Lingerie elegante", SENSUEL,
          "seated on the edge of her own bed, elegant black lace lingerie "
          "set fully covering, sheer stockings, a robe slipping off one "
          "shoulder, dim warm bedside lamp, modest framing, no nudity",
          "Juste pour toi \U0001f48b ... et personne d'autre.",
          POSE, LACHES),
    Scene("fenetre", "Lumiere de fenetre", SENSUEL,
          "standing by her bedroom window with thin curtains, fitted lace "
          "bodysuit fully covering, backlit by soft morning light, "
          "looking over her shoulder, elegant and modest, no nudity",
          "La lumiere est belle ce matin... et je pense a toi \U0001f60f",
          POSE, MOUILLES),
    Scene("talons", "Talons et bas", SENSUEL,
          "in the hallway of her flat, elegant lingerie set fully "
          "covering with sheer stockings, a long coat held open, black "
          "heels, single warm ceiling light, no nudity",
          "Je sors... ou je reste ? A toi de choisir \U0001f48b",
          MIROIR, SOIGNES),
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
        scene.coiffure,
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
