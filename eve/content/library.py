"""Bibliothèque éditoriale : la matière première du contenu.

Tout est écrit **en langage parlé** — hésitations, contractions, phrases
reprises. C'est ce registre, plus que le choix de la voix, qui fait qu'une
vidéo sonne « filmée au téléphone » plutôt que publicitaire.

Chaque entrée : (sujet, phrase d'ouverture, points développés).
"""
from __future__ import annotations

# ------------------------------------------------------- la construction
BUILD_TOPICS = [
    ("Comment j'ai commencé à coder ce truc",
     "Alors, j'ai pas fait d'école d'info. J'ai commencé avec des tutos et beaucoup de nuits.",
     ["le premier mois j'ai rien produit qui marche",
      "j'ai recommencé de zéro trois fois",
      "en vrai, apprendre à débugger m'a plus servi qu'apprendre à écrire du code"]),
    ("Le bug qui m'a coûté une semaine",
     "Mon programme ouvrait deux fois la même position. Une semaine à chercher pourquoi.",
     ["c'était une condition mal écrite, deux caractères",
      "j'ai trouvé en relisant à voix haute, pas en fixant l'écran",
      "depuis, je teste chaque règle séparément avant de tout brancher"]),
    ("Ce que fait mon programme, en simple",
     "Il lit le prix, il compare à des règles que j'ai écrites, il passe l'ordre ou pas. C'est tout.",
     ["pas de magie, pas de boule de cristal",
      "les règles, c'est moi qui les décide, à froid",
      "le programme, lui, il les applique sans discuter — c'est tout son intérêt"]),
    ("Pourquoi j'ai tout réécrit",
     "Ma première version marchait, mais je comprenais plus ce que je lisais.",
     ["du code que tu comprends pas, tu peux pas le corriger",
      "j'ai coupé de moitié et enlevé trois règles sur cinq",
      "en vrai, moins de règles = moins de choses qui cassent"]),
    ("Mes outils, rien de compliqué",
     "Un vieux portable, Python, et un carnet papier. Franchement c'est tout.",
     ["le carnet sert plus que l'ordinateur, au début",
      "j'écris la règle en français avant de la coder",
      "si je sais pas l'écrire en une phrase, c'est que c'est pas clair"]),
    ("Le moment où j'ai voulu tout arrêter",
     "Bon. Y a eu une semaine où j'ai vraiment failli tout supprimer.",
     ["rien ne marchait et je voyais pas pourquoi",
      "j'ai arrêté trois jours, j'ai pas touché à l'ordinateur",
      "quand je suis revenue, j'ai trouvé le problème en deux heures"]),
]

# ---------------------------------------------------------- apprentissage
APPRENDRE_TOPICS = [
    ("Le drawdown, c'est quoi en vrai",
     "C'est la plus grosse baisse que t'as encaissée avant de remonter. Et c'est le chiffre qui compte.",
     ["tout le monde montre le gain, personne montre la baisse",
      "si tu tiens pas psychologiquement la baisse, le reste sert à rien",
      "moi je regarde toujours le pire mois avant le meilleur"]),
    ("Pourquoi je me méfie des courbes trop belles",
     "Une courbe parfaite, c'est pas un bon signe. C'est souvent qu'on a trop bidouillé.",
     ["tu peux toujours faire coller un programme au passé",
      "le vrai test, c'est sur des données qu'il a jamais vues",
      "en vrai, une courbe qui monte tout droit devrait t'inquiéter"]),
    ("Combien de temps avant de savoir si ça marche",
     "Des mois. Une bonne semaine ça prouve rien, une mauvaise non plus.",
     ["il faut assez d'opérations pour que le hasard s'efface",
      "je compte en centaines de trades, pas en jours",
      "c'est la partie la plus chiante, et la plus importante"]),
    ("Ce que je note à chaque fois",
     "La raison avant, le résultat après. Dans cet ordre, jamais l'inverse.",
     ["j'écris pourquoi avant de savoir si ça marche",
      "je relis trois mois plus tard, c'est là que t'apprends",
      "un bon résultat pour une mauvaise raison, c'est le pire des cas"]),
    ("Le risque, avant tout le reste",
     "La première règle que j'ai codée, c'est combien je peux perdre. Pas combien je peux gagner.",
     ["une limite par position, une limite par jour",
      "le programme s'arrête tout seul si ça dépasse",
      "franchement, c'est la seule règle que je changerai jamais"]),
]

# ------------------------------------------------------------- quotidien
QUOTIDIEN_TOPICS = [
    ("Ma journée type, sans filtre",
     "Je me lève, café, deux heures de code avant que le cerveau se réveille vraiment.",
     ["les meilleures heures c'est le matin, pour moi",
      "l'après-midi je relis, je code plus",
      "et le soir j'y touche pas — sinon je casse ce que j'ai fait"]),
    ("Pourquoi Montpellier",
     "J'y ai grandi, et franchement pour bosser sur un projet perso c'est parfait.",
     ["la mer à vingt minutes quand tu bloques",
      "des cafés où tu peux rester trois heures",
      "et surtout, moins cher que Paris pour vivre sur pas grand-chose"]),
    ("Ce que ça coûte, ce projet",
     "Pour l'instant : rien, à part du temps. Et le compte de 100 €.",
     ["les outils que j'utilise sont gratuits",
      "j'ai pas payé de formation, y a tout en ligne",
      "le seul vrai coût c'est les soirées où je fais rien d'autre"]),
    ("Quand les gens me demandent ce que je fais",
     "J'ai jamais su répondre en une phrase. Du coup je dis « de l'informatique ».",
     ["expliquer que tu codes un truc qui achète et vend tout seul, ça sonne bizarre",
      "la moitié pense que c'est une arnaque, je les comprends",
      "l'autre moitié me demande si ça rapporte — pas encore"]),
    ("Les week-ends où j'y touche pas",
     "J'ai appris à couper. Sinon je deviens dingue.",
     ["le samedi je ferme l'ordinateur",
      "je note les idées sur papier, je les code pas tout de suite",
      "les meilleures idées arrivent quand tu bosses pas dessus"]),
]

# --------------------------------------------------------------- mindset
MINDSET_TOPICS = [
    ("Partir de 100 €, pourquoi si peu",
     "Parce que c'est ce que je peux perdre sans que ça change ma vie. C'est le seul critère.",
     ["si tu mets de l'argent dont t'as besoin, tu prends de mauvaises décisions",
      "100 € c'est assez pour que ce soit réel",
      "et assez peu pour que je dorme la nuit"]),
    ("Les mauvaises semaines",
     "Y en aura. La question c'est pas si, c'est comment tu réagis quand ça arrive.",
     ["je touche à rien pendant une mauvaise semaine",
      "changer une règle après une perte, c'est la pire erreur",
      "je note ce que je ressens, je décide plus tard"]),
    ("Ce que j'aurais aimé qu'on me dise",
     "Que la partie difficile, c'est pas le code. C'est d'attendre sans rien toucher.",
     ["tout le monde parle de stratégie, personne parle de patience",
      "le programme fait son travail, moi je dois faire le mien : rien",
      "en vrai c'est beaucoup plus dur que ça en a l'air"]),
    ("Je vends rien, et je vendrai rien",
     "On me demande souvent si je vends le programme. Non. Et c'est pas prévu.",
     ["ce que je montre, c'est le chemin, pas un produit",
      "si un jour ça change je le dirai clairement",
      "méfie-toi de tous ceux qui te vendent une méthode"]),
]

# ---------------------------------------------------------------- réponses
QA_TOPICS = [
    ("Est-ce que je gagne de l'argent",
     "Franchement, non. Pas encore, et peut-être jamais. Je teste.",
     ["100 € c'est pas de quoi vivre, c'est de quoi apprendre",
      "je publierai les chiffres, bons ou mauvais",
      "si ça marche pas, je le dirai aussi"]),
    ("Je peux copier ton programme",
     "Non, et surtout : ça t'apporterait rien.",
     ["un programme que tu comprends pas, tu le tiens pas quand ça baisse",
      "le code c'est vingt pour cent, le reste c'est comprendre pourquoi",
      "commence par une règle simple, à toi"]),
    ("Par où commencer quand on connaît rien",
     "Python, et un seul tuto que tu finis en entier. Pas quinze commencés.",
     ["une source, jusqu'au bout",
      "tu codes un truc qui marche pas, tu le répares — c'est ça apprendre",
      "et tu écris ce que t'as compris, sinon t'as rien compris"]),
    ("Pourquoi tu montres tout",
     "Parce que c'est le seul truc que je peux offrir : le chemin réel, sans filtre.",
     ["y a assez de comptes qui montrent que les réussites",
      "moi je montrerai aussi les semaines pourries",
      "et si je me plante complètement, ça restera en ligne"]),
]

TOPIC_BANK = {
    "build": BUILD_TOPICS,
    "apprendre": APPRENDRE_TOPICS,
    "quotidien": QUOTIDIEN_TOPICS,
    "mindset": MINDSET_TOPICS,
    "qa": QA_TOPICS,
}

# Décors par pilier, pour les prompts image.
PILLAR_SCENES = {
    "journal": [
        "sitting at a desk at night, only the screen lighting her face, thoughtful",
        "writing numbers in a paper notebook next to a laptop, morning light",
        "looking at a laptop screen with a serious expression, hand on chin",
    ],
    "build": [
        "typing on a laptop at a wooden desk by a window, two screens, focused",
        "leaning back in a chair rubbing her eyes, laptop open, late evening",
        "writing on a paper notebook covered in handwritten notes, coffee cup",
        "sitting cross-legged on the floor with a laptop, cables around",
    ],
    "apprendre": [
        "explaining something to the camera at a kitchen table, laptop closed",
        "drawing a simple diagram in a notebook, close-up of the hand and pen",
        "sitting on a sofa with a notebook, talking to the camera casually",
    ],
    "quotidien": [
        "making coffee in a small kitchen in the morning, unposed",
        "walking through old narrow streets with pale stone buildings, late afternoon",
        "sitting on a rooftop terrace at sunset, tiled roofs behind her",
        "walking on an empty off-season beach, low sunlight, wind in her hair",
    ],
    "mindset": [
        "sitting at a desk looking away from the screen, tired but calm",
        "walking alone at dawn, empty street, hands in pockets",
        "closing a laptop and standing up, end of the day",
    ],
    "qa": [
        "talking directly to the camera in a small flat, relaxed, natural light",
        "sitting on the floor against a wall, phone propped up, casual",
    ],
}
