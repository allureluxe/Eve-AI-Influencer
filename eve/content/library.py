"""Bibliothèque d'entraînement : la matière première du contenu.

Contenu volontairement générique et prudent (aucun matériel lourd, aucune
prescription individuelle). C'est ce qui alimente scripts, légendes et PDF.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Exercise:
    key: str
    name_fr: str
    name_en: str
    target: str
    level: str                      # debutant | intermediaire
    equipment: str                  # aucun | halteres | elastique | machine
    cues: list[str] = field(default_factory=list)     # points techniques
    mistakes: list[str] = field(default_factory=list)  # erreurs fréquentes
    scene: str = ""                 # description visuelle pour le prompt image


EXERCISES: list[Exercise] = [
    Exercise(
        key="squat",
        name_fr="Squat au poids du corps",
        name_en="Bodyweight squat",
        target="quadriceps, fessiers",
        level="debutant",
        equipment="aucun",
        cues=["pieds largeur d'épaules, orteils légèrement ouverts",
              "on pousse les hanches vers l'arrière avant de descendre",
              "genoux dans l'axe des orteils",
              "poitrine haute, regard devant"],
        mistakes=["talons qui décollent", "dos qui s'arrondit en bas",
                  "genoux qui rentrent vers l'intérieur"],
        scene="demonstrating a bodyweight squat, mid-rep at parallel depth, side angle, full body in frame",
    ),
    Exercise(
        key="hip_thrust",
        name_fr="Hip thrust",
        name_en="Hip thrust",
        target="fessiers",
        level="intermediaire",
        equipment="machine",
        cues=["haut du dos calé sur le banc", "menton rentré vers la poitrine",
              "on serre les fessiers 1 seconde en haut", "côtes basses, pas de cambrure"],
        mistakes=["hyperextension lombaire en haut", "amplitude trop courte",
                  "poussée sur la pointe des pieds"],
        scene="performing a hip thrust at the gym, controlled lockout position, side angle",
    ),
    Exercise(
        key="romanian_deadlift",
        name_fr="Soulevé de terre roumain",
        name_en="Romanian deadlift",
        target="ischio-jambiers, fessiers",
        level="intermediaire",
        equipment="halteres",
        cues=["légère flexion des genoux, puis on recule les hanches",
              "haltères qui frôlent les cuisses", "dos neutre du début à la fin",
              "on s'arrête quand l'étirement arrive, pas plus bas"],
        mistakes=["dos rond", "descente uniquement en pliant les genoux",
                  "charge trop lourde qui casse la technique"],
        scene="demonstrating a dumbbell Romanian deadlift, neutral spine, side profile",
    ),
    Exercise(
        key="push_up",
        name_fr="Pompes (au sol ou sur genoux)",
        name_en="Push-up",
        target="pectoraux, triceps, gainage",
        level="debutant",
        equipment="aucun",
        cues=["mains sous les épaules", "corps aligné tête-bassin-talons",
              "coudes à 45°, pas en T", "on descend jusqu'à la poitrine près du sol"],
        mistakes=["bassin qui s'affaisse", "coudes trop écartés",
                  "amplitude partielle"],
        scene="demonstrating a push-up on a mat, strong plank alignment, side angle",
    ),
    Exercise(
        key="plank",
        name_fr="Gainage planche",
        name_en="Forearm plank",
        target="sangle abdominale",
        level="debutant",
        equipment="aucun",
        cues=["coudes sous les épaules", "on rentre le bassin, on serre les fessiers",
              "respiration continue", "qualité > durée"],
        mistakes=["fesses trop hautes", "lombaires creusées", "apnée"],
        scene="holding a forearm plank on a yoga mat, perfect alignment, side angle",
    ),
    Exercise(
        key="glute_bridge",
        name_fr="Pont fessier au sol",
        name_en="Glute bridge",
        target="fessiers, ischio-jambiers",
        level="debutant",
        equipment="aucun",
        cues=["talons proches des fesses", "on pousse dans les talons",
              "pause 2 secondes en haut", "côtes basses"],
        mistakes=["poussée dans les orteils", "cambrure excessive en haut"],
        scene="performing a glute bridge on a mat at home, top position, side angle",
    ),
    Exercise(
        key="lat_pulldown",
        name_fr="Tirage vertical",
        name_en="Lat pulldown",
        target="dos, biceps",
        level="debutant",
        equipment="machine",
        cues=["poitrine ouverte, léger recul du buste",
              "on tire avec les coudes, pas avec les mains",
              "barre vers le haut de la poitrine", "retour contrôlé"],
        mistakes=["élan avec tout le corps", "barre derrière la nuque",
                  "épaules qui montent aux oreilles"],
        scene="using a lat pulldown machine at the gym, controlled pull, three-quarter angle",
    ),
    Exercise(
        key="dumbbell_row",
        name_fr="Rowing haltère",
        name_en="Single-arm dumbbell row",
        target="dos",
        level="debutant",
        equipment="halteres",
        cues=["dos plat, bassin stable", "on tire le coude vers la hanche",
              "on serre l'omoplate en haut", "cou dans l'alignement"],
        mistakes=["rotation du buste", "tirage avec l'avant-bras seul"],
        scene="doing a single-arm dumbbell row with a knee on a bench, flat back, side angle",
    ),
    Exercise(
        key="lunge",
        name_fr="Fente avant",
        name_en="Forward lunge",
        target="quadriceps, fessiers, équilibre",
        level="debutant",
        equipment="aucun",
        cues=["grand pas, buste droit", "genou arrière vers le sol",
              "poids sur le talon avant pour remonter"],
        mistakes=["pas trop court", "buste penché", "genou avant qui dépasse loin devant"],
        scene="performing a forward lunge outdoors, bottom position, full body in frame",
    ),
    Exercise(
        key="dead_bug",
        name_fr="Dead bug",
        name_en="Dead bug",
        target="abdominaux profonds",
        level="debutant",
        equipment="aucun",
        cues=["bas du dos collé au sol", "mouvement lent, croisé bras/jambe",
              "on expire en tendant"],
        mistakes=["décollement lombaire", "mouvement trop rapide"],
        scene="doing a dead bug core exercise on a mat, controlled position, top-down angle",
    ),
]

EXERCISES_BY_KEY = {e.key: e for e in EXERCISES}


@dataclass(frozen=True)
class Workout:
    key: str
    title_fr: str
    duration_min: int
    level: str
    equipment: str
    blocks: list[tuple[str, str]]   # (exercice_key, format)
    focus: str


WORKOUTS: list[Workout] = [
    Workout("full_body_10", "Full body express 10 minutes", 10, "debutant", "aucun",
            [("squat", "40s travail / 20s repos"), ("push_up", "40s / 20s"),
             ("glute_bridge", "40s / 20s"), ("plank", "30s / 30s"),
             ("lunge", "40s / 20s")], "corps entier"),
    Workout("glutes_15", "Fessiers à la maison 15 minutes", 15, "debutant", "aucun",
            [("glute_bridge", "3 x 15"), ("lunge", "3 x 10 par jambe"),
             ("squat", "3 x 15"), ("plank", "3 x 30s")], "bas du corps"),
    Workout("gym_upper", "Haut du corps en salle — débutante", 35, "debutant", "machine",
            [("lat_pulldown", "3 x 10"), ("dumbbell_row", "3 x 10 par bras"),
             ("push_up", "3 x 8"), ("dead_bug", "3 x 8 par côté")], "haut du corps"),
    Workout("gym_lower", "Bas du corps en salle", 40, "intermediaire", "machine",
            [("squat", "4 x 8"), ("romanian_deadlift", "3 x 10"),
             ("hip_thrust", "3 x 12"), ("lunge", "2 x 12 par jambe")], "bas du corps"),
    Workout("core_5", "Abdos 5 minutes chrono", 5, "debutant", "aucun",
            [("plank", "3 x 30s"), ("dead_bug", "3 x 10 par côté"),
             ("glute_bridge", "2 x 20")], "gainage"),
]

WORKOUTS_BY_KEY = {w.key: w for w in WORKOUTS}


# Idées de contenu prêtes à l'emploi par pilier — utilisées quand aucun LLM
# n'est configuré (mode 100 % gratuit et hors-ligne).
NUTRITION_TOPICS = [
    ("Combien de protéines par repas ?", "Vise une source de protéines à chaque repas : la satiété fait 80 % du travail.",
     ["une portion de protéines = la paume de la main", "les protéines rassasient plus longtemps que les glucides",
      "yaourt grec, œufs, thon, tofu, poulet : les quatre basiques"]),
    ("Quoi manger avant l'entraînement", "Un glucide simple 60 à 90 min avant, c'est suffisant pour une séance d'une heure.",
     ["banane + café", "pain complet + miel", "évite le repas très gras juste avant"]),
    ("Le petit-déjeuner qui tient jusqu'à midi", "Protéines + fibres + un vrai gras, pas juste du sucre.",
     ["yaourt grec, flocons d'avoine, baies", "œufs brouillés et avocat", "boire un grand verre d'eau au réveil"]),
    ("La règle de l'assiette", "Moitié légumes, un quart protéines, un quart féculents. Zéro calcul.",
     ["pas de balance nécessaire", "ça marche au restaurant aussi", "on ajuste les féculents selon l'activité du jour"]),
    ("Collation post-séance", "Rien d'obligatoire, mais un mélange protéines + glucides aide la récupération.",
     ["shaker + banane", "fromage blanc + fruits", "la fenêtre anabolique de 30 min est un mythe"]),
]

MOTIVATION_TOPICS = [
    ("La règle des 2 jours", "Tu n'es jamais autorisée à sauter deux jours d'affilée. C'est tout le système.",
     ["un jour off c'est de la récup", "deux jours off c'est le début d'un arrêt", "10 min comptent comme une séance"]),
    ("Commencer quand on n'a pas le temps", "Bloque 15 minutes dans l'agenda comme un rendez-vous médical.",
     ["même heure chaque jour", "tenue préparée la veille", "on baisse la barre jusqu'à ce que ce soit ridicule d'échouer"]),
    ("La salle fait peur ? Normal", "Tout le monde regarde son téléphone, pas toi. Voici un plan d'entrée en 3 étapes.",
     ["repérer la salle un jour creux", "3 machines maximum la première fois", "écouteurs + programme écrit"]),
    ("Progresser sans se peser", "Le poids ment. Le nombre de répétitions, non.",
     ["note tes charges et tes reps", "photos toutes les 4 semaines", "l'énergie et le sommeil sont des données"]),
    ("Après une pause de 3 mois", "On reprend à 50 % de ce qu'on faisait avant. Sans exception.",
     ["les courbatures ne sont pas un objectif", "2 séances par semaine suffisent pour relancer", "la technique revient avant la force"]),
]

LIFESTYLE_TOPICS = [
    ("Ma routine du matin à Miami", "Lever 5h45, eau, 20 minutes de marche au lever du soleil, puis la séance.",
     ["lumière du matin = meilleur sommeil le soir", "la marche avant le café", "téléphone en mode avion 30 min"]),
    ("Ce que je mets dans mon sac de sport", "Cinq objets, jamais plus.",
     ["gourde 1L", "bandes élastiques", "chaussures plates pour les jambes", "écouteurs", "serviette"]),
    ("Dimanche prep", "Une heure le dimanche, cinq jours tranquilles.",
     ["cuire une protéine en grande quantité", "laver et couper les légumes", "écrire les 4 séances de la semaine"]),
]

QA_TOPICS = [
    ("Cardio avant ou après la muscu ?", "Après, si ton objectif est la force. Avant, seulement pour un échauffement court.",
     ["10 min d'échauffement max avant", "le cardio long fatigue les jambes", "les deux peuvent aussi être sur des jours différents"]),
    ("Combien de séances par semaine ?", "Trois séances régulières battent six séances une semaine sur deux.",
     ["2 à 3 pour débuter", "48h entre deux séances sur le même groupe", "la marche quotidienne compte"]),
    ("Faut-il des courbatures ?", "Non. Les courbatures mesurent la nouveauté, pas l'efficacité.",
     ["elles diminuent avec l'habitude", "on peut progresser sans en avoir", "douleur articulaire ≠ courbature"]),
]

TOPIC_BANK = {
    "nutrition": NUTRITION_TOPICS,
    "motivation": MOTIVATION_TOPICS,
    "lifestyle": LIFESTYLE_TOPICS,
    "qa": QA_TOPICS,
}
