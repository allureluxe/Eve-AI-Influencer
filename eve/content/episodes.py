"""Les épisodes du récit : le fil narratif, écrit à l'avance, publié à temps.

Chaque épisode correspond à une étape de l'arc défini dans le character
bible. Il peut être **écrit et produit** quand on veut ; il ne peut être
**publié** qu'une fois l'étape franchie pour de vrai dans le journal.

C'est la seule façon d'avoir des vidéos prêtes d'avance sans jamais
raconter quelque chose qui n'a pas eu lieu.
"""
from __future__ import annotations

from dataclasses import dataclass

from eve.content import story


@dataclass(frozen=True)
class Episode:
    cle: str
    numero: int
    titre: str
    hook: str            # les trois premières secondes : elles font la portée
    ouverture: str
    points: list[str]
    ecran_final: str = ""


# L'ordre est le fil narratif. On ne le mélange pas : l'épisode 4 n'a aucun
# sens si on n'a pas vu le 1.
EPISODES: list[Episode] = [
    Episode(
        "pourquoi", 1,
        "Pourquoi je m'y suis mise",
        "Y a un an, je savais même pas ce que c'était un algorithme.",
        "Vraiment, zéro. Et aujourd'hui j'ai un programme qui achète et vend tout seul.",
        ["un jour je tombe sur un mec qui montre son programme qui achète et vend tout seul",
         "et je me dis : mais attends, pourquoi je pourrais pas faire ça moi",
         "j'ai commencé le soir après le boulot, avec des tutos gratuits",
         "je vais tout montrer ici, y compris quand ça marche pas"],
        "ÉPISODE 1"),
    Episode(
        "premieres_lignes", 2,
        "Les premières lignes",
        "Ma première version faisait deux cents lignes. Et elle servait à rien.",
        "Elle lisait le prix, elle affichait un truc. C'est tout.",
        ["elle lisait le prix, elle affichait un truc, c'est tout",
         "j'ai mis trois semaines à comprendre pourquoi ça plantait la nuit",
         "j'écris chaque règle en français dans un carnet avant de la coder",
         "si je peux pas l'écrire en une phrase, c'est que c'est pas clair"],
        "ÉPISODE 2"),
    Episode(
        "backtest", 3,
        "Je le teste sur le passé",
        "Ma première courbe était magnifique. Et c'était très mauvais signe.",
        "Le backtest, c'est faire tourner le programme sur des années déjà passées.",
        ["ça dit pas si ça va marcher demain, ça dit juste si c'est pas absurde",
         "ma première courbe était magnifique, et c'était mauvais signe",
         "quand c'est trop beau, c'est que t'as bidouillé jusqu'à ce que ça colle",
         "j'ai coupé trois règles sur cinq et gardé la version moche"],
        "ÉPISODE 3"),
    Episode(
        "demo", 4,
        "En démo, sans argent",
        "L'étape que tout le monde saute. Et c'est là que j'ai trouvé le pire bug.",
        "Avant de mettre un euro, je l'ai fait tourner sur un compte de démonstration.",
        ["deux semaines, sans rien risquer",
         "j'ai trouvé trois bugs, dont un qui doublait les positions",
         "aucun backtest n'avait vu ce bug, parce qu'il vient du temps réel",
         "franchement, cette étape est celle que tout le monde saute — et c'est l'erreur"],
        "ÉPISODE 4"),
    Episode(
        "cent_euros", 5,
        "J'ouvre un compte avec 100 €",
        "Voilà. J'ai mis cent euros dessus.",
        "Pas mille, pas dix mille. Cent euros que je peux perdre entièrement.",
        ["c'est le seul critère : de l'argent dont je n'ai pas besoin",
         "assez pour que ce soit réel, assez peu pour que je dorme",
         "la première règle que j'ai codée, c'est combien je peux perdre par jour",
         "le programme s'arrête tout seul si ça dépasse"],
        "ÉPISODE 5"),
    Episode(
        "premiere_semaine", 6,
        "La première semaine",
        "Première semaine terminée. Je vous dois les chiffres.",
        "Sans arrondir, et sans rien cacher.",
        ["je publie le chiffre chaque semaine, qu'il monte ou qu'il baisse",
         "une bonne semaine prouve rien, une mauvaise non plus",
         "ce qui compte c'est dans six mois, pas dans sept jours",
         "et si ça marche pas du tout, je le dirai aussi"],
        "ÉPISODE 6"),
]

PAR_CLE = {e.cle: e for e in EPISODES}


def prets_a_publier(persona, journal: story.Journal | None) -> list[Episode]:
    """Épisodes dont l'étape a vraiment eu lieu.

    Le premier ne prétend à aucun résultat : il est toujours publiable.
    """
    ouverts = {e["key"] for e in story.episodes_disponibles(persona, journal)}
    return [e for e in EPISODES if e.cle in ouverts]


def bloques(persona, journal: story.Journal | None) -> list[Episode]:
    prets = {e.cle for e in prets_a_publier(persona, journal)}
    return [e for e in EPISODES if e.cle not in prets]


def sujet(episode: Episode, journal: story.Journal | None) -> tuple[str, str, list[str]]:
    """Trame (titre, ouverture, points) pour le générateur de script.

    L'épisode « première semaine » est le seul à porter des chiffres : ils
    viennent du journal, jamais du texte écrit ici.
    """
    points = list(episode.points)
    if episode.cle == "premiere_semaine" and journal is not None:
        chiffres = journal.resume_chiffre()
        if chiffres:
            points.insert(0, chiffres)
    return episode.titre, episode.ouverture, points
