"""Bibliothèque éditoriale : la matière première du contenu.

Chaque entrée est un triplet (sujet, réponse courte, points développés).
Le générateur s'en sert directement quand aucun LLM n'est configuré, et
comme trame quand il y en a un.

Le pilier `fashion` est volontairement le plus fourni : c'est lui qui
construit l'audience du futur site de vêtements.
"""
from __future__ import annotations

# --------------------------------------------------------------- lifestyle
LIFESTYLE_TOPICS = [
    ("Ma vraie routine du matin",
     "Cinq heures quarante-cinq, sans réveil agressif et sans téléphone pendant une heure.",
     ["lumière naturelle avant l'écran",
      "un café, un carnet, trois lignes sur la journée",
      "la première heure décide des douze suivantes"]),
    ("Le restaurant que je recommande à Miami",
     "Une petite table italienne à Sunset Harbour, quinze couverts, pas de réservation en ligne.",
     ["la carte tient sur une page, c'est bon signe",
      "on y va avant vingt heures pour avoir la terrasse",
      "les meilleures adresses n'ont presque jamais de compte Instagram"]),
    ("Ce que je ne montre pas",
     "Les journées où je ne fais rien de photogénique. Elles sont la majorité.",
     ["trois heures d'écran sur des tableaux",
      "des semaines sans sortir un seul contenu",
      "le beau est le résumé, pas la moyenne"]),
    ("Dimanche sans rien prévoir",
     "Une journée par semaine sans agenda, c'est ce qui rend les six autres tenables.",
     ["pas de réveil, pas de rendez-vous",
      "marcher sans destination",
      "on ne récupère pas de la fatigue avec du divertissement"]),
    ("Ma table basse en ce moment",
     "Trois livres, une bougie, rien d'autre. Une surface vide est un luxe.",
     ["moins d'objets, mieux choisis",
      "un seul objet qui a une histoire",
      "le vide se remarque plus qu'un bibelot"]),
    ("La soirée d'hier",
     "Un vernissage dans le Design District, deux heures, rentrée à vingt-deux heures.",
     ["y aller pour deux conversations, pas pour la photo",
      "partir avant la fin, toujours",
      "on retient les gens, jamais le buffet"]),
]

# ------------------------------------------------------------------ mode
FASHION_TOPICS = [
    ("Comment reconnaître un bon vêtement en trente secondes",
     "Coutures, doublure, tombé. Le prix ne dit presque rien, la matière dit tout.",
     ["regarder l'envers avant l'endroit",
      "une couture droite et dense tient dix ans",
      "un tissu qui se froisse dans la main se froissera sur toi"]),
    ("Les matières qui vieillissent bien",
     "Laine, lin, coton dense, cuir pleine fleur. Le reste devient triste en deux saisons.",
     ["fuir les mélanges à plus de trente pour cent de polyester",
      "le cachemire deux fils dure, le un fil bouloche",
      "le lin se froisse : c'est le prix de la respirabilité"]),
    ("La garde-robe de trente pièces",
     "Trente pièces bien choisies couvrent une année entière. Je te montre la répartition.",
     ["une palette de trois couleurs maximum",
      "deux paires de chaussures qui vont avec tout",
      "acheter en fin de saison, jamais en pleine collection"]),
    ("Le blazer, la pièce qui change tout",
     "Un blazer bien coupé transforme un jean et un t-shirt en tenue.",
     ["l'épaule doit tomber pile sur l'os",
      "la manche s'arrête au poignet, un centimètre de chemise dépasse",
      "un blazer se retouche, il ne s'achète jamais parfait"]),
    ("Pourquoi je n'achète presque plus de nouveautés",
     "Les pièces intemporelles se revendent, les pièces tendance se donnent.",
     ["regarder la cote de revente avant d'acheter",
      "une pièce portée cinquante fois coûte moins cher qu'une portée trois fois",
      "la seconde main de qualité existe pour presque toutes les maisons"]),
    ("Les accessoires, dans l'ordre d'importance",
     "Chaussures, sac, montre. Trois objets qui portent quatre-vingts pour cent de l'allure.",
     ["des chaussures entretenues valent mieux que des neuves",
      "un sac structuré tient mieux dans le temps",
      "l'or fin se remarque plus que le clinquant"]),
    ("Ce que je regarde sur une étiquette",
     "Composition, pays de fabrication, entretien. Dans cet ordre.",
     ["« made in » n'est pas une garantie, mais c'est une information",
      "un vêtement lavable à trente durera plus longtemps",
      "le nettoyage à sec obligatoire est un coût caché"]),
    ("Une couleur, trois tenues",
     "Le camel fonctionne du matin au soir. Démonstration.",
     ["le matin avec du blanc",
      "l'après-midi avec du denim brut",
      "le soir avec du noir mat"]),
]

# ---------------------------------------------------------------- voyages
TRAVEL_TOPICS = [
    ("Comment je choisis un hôtel",
     "Je regarde les photos des clients, jamais celles de l'établissement.",
     ["chercher les avis de la basse saison",
      "un bon hôtel répond aux avis négatifs sans se justifier",
      "l'emplacement bat la piscine, toujours"]),
    ("Ma valise pour cinq jours",
     "Un bagage cabine, sept pièces, une seule palette de couleurs.",
     ["tout doit s'associer avec tout",
      "une paire de chaussures portée, une transportée",
      "les affaires de toilette en format solide"]),
    ("Une ville hors saison",
     "La même ville en novembre n'est pas la même ville en juillet. Souvent en mieux.",
     ["moitié moins de monde, moitié moins cher",
      "les restaurants prennent le temps de parler",
      "la lumière d'hiver est plus belle en photo"]),
    ("Le voyage que je referais demain",
     "Trois jours sur la côte amalfitaine, en septembre, sans voiture.",
     ["les bateaux plutôt que les routes",
      "dormir à Atrani plutôt qu'à Positano",
      "partir tôt le matin, tout est vide"]),
]

# -------------------------------------------------------------- discipline
MINDSET_TOPICS = [
    ("Apprendre un métier technique seule",
     "Deux heures par jour pendant deux ans battent un cours intensif de trois mois.",
     ["choisir une seule source et la finir",
      "écrire ce qu'on a compris, sinon on n'a rien compris",
      "le plateau de six mois est normal, il n'annonce rien"]),
    ("Ce que j'ai appris en me trompant",
     "Les erreurs coûteuses sont toujours des erreurs de méthode, jamais de chance.",
     ["noter chaque décision avant de connaître le résultat",
      "relire ses notes trois mois plus tard",
      "un bon résultat sur une mauvaise méthode est le pire des cas"]),
    ("Comment je structure ma semaine",
     "Trois jours de travail profond, deux jours de contenu, deux jours sans rien.",
     ["ne jamais mélanger création et exécution le même jour",
      "les blocs de trois heures, pas de quinze minutes",
      "protéger un jour vraiment vide"]),
    ("La discipline n'est pas de la motivation",
     "La motivation décide du premier jour. La structure décide des trois cents suivants.",
     ["réduire la décision à zéro : même heure, même endroit",
      "baisser la barre jusqu'à ce que l'échec soit ridicule",
      "compter les semaines, pas les jours"]),
]

# ----------------------------------------------------------------- réponses
QA_TOPICS = [
    ("Pourquoi je précise que je suis générée par IA",
     "Parce que c'est vrai, et parce que le cacher finirait par se voir.",
     ["c'est une obligation légale des deux côtés de l'Atlantique",
      "un compte qui le cache perd tout le jour où c'est découvert",
      "autant en faire une caractéristique"]),
    ("Est-ce que tu vends quelque chose ?",
     "Non. Pas de formation, pas de système, pas de groupe privé.",
     ["si un jour je vends, ce sera un produit, pas une promesse",
      "aucun lien affilié sans mention claire",
      "les comptes qui vendent un secret vendent le secret, pas le résultat"]),
    ("Comment tu choisis ce que tu montres",
     "Ce qui m'a coûté du temps à comprendre, et qui tient en une minute.",
     ["si je ne peux pas l'expliquer simplement, je ne l'ai pas compris",
      "je ne montre pas ce que je n'utilise pas",
      "les questions de la communauté font la moitié du planning"]),
]

TOPIC_BANK = {
    "lifestyle": LIFESTYLE_TOPICS,
    "fashion": FASHION_TOPICS,
    "travel": TRAVEL_TOPICS,
    "mindset": MINDSET_TOPICS,
    "qa": QA_TOPICS,
}

# Décors adaptés à chaque pilier, pour les prompts image.
PILLAR_SCENES = {
    "lifestyle": [
        "having morning coffee on a sunlit terrace, looking out at the city",
        "walking through a quiet street in the morning, tote bag over the shoulder",
        "reading at a marble table with a single flower arrangement",
        "arriving at a restaurant at golden hour, warm ambient light",
    ],
    "fashion": [
        "adjusting the cuff of a tailored blazer in front of a large mirror",
        "standing in soft directional light, full outfit visible head to toe",
        "close-up of hands holding a folded knit sweater, showing the fabric",
        "browsing a rail of clothes in a quiet boutique, thoughtful expression",
    ],
    "travel": [
        "standing on a hotel balcony overlooking the sea at sunrise",
        "walking along a coastal street with a straw hat and linen dress",
        "sitting by a hotel pool in the late afternoon, book on the table",
        "packing a small suitcase open on a bed, folded clothes visible",
    ],
    "work": [
        "sitting at a wide desk with a notebook and a closed laptop, focused",
        "writing by hand at a desk near a window, early morning light",
        "standing at a window with a coffee, thinking, office behind her",
    ],
    "mindset": [
        "writing in a notebook at a quiet table, warm lamp light",
        "sitting on a sofa with a book, calm and unposed",
        "walking alone on a boardwalk at dawn, no one else around",
    ],
    "qa": [
        "talking directly to the camera in a bright living room, relaxed",
        "sitting cross-legged on a chair, speaking candidly to camera",
    ],
}
