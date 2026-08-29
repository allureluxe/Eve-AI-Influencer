"""Comment un trade s'est termine — et pourquoi la question compte.

L'operateur a lu son journal, vu « fermeture en stop » sur toutes les
lignes, et conclu que le robot ne gagnait jamais. La conclusion etait
fausse, pour une raison de vocabulaire.

Un stop n'est pas un niveau fixe. Il part sous le prix d'entree, puis :
  - a `breakeven_at_r`, il remonte au prix d'entree ;
  - a `trail_start_r`, il suit le sommet a `trail_atr_mult` ATR.

Une fois remonte, le toucher n'est plus une perte : c'est un GAIN
VERROUILLE. Le motif enregistre reste pourtant « stop-loss touche »,
identique a celui d'une perte pleine. Deux evenements opposes portent le
meme nom dans le journal.

Ce module separe les deux, partout de la meme facon — le rejeu
(`comparer.py`) et l'etat du robot (`etat.py`) l'utilisent tous les deux,
pour qu'un chiffre lu a un endroit veuille dire la meme chose a l'autre.
"""
from __future__ import annotations

CATEGORIES = ["objectif", "stop suiveur", "stop initial", "temporel",
              "retournement", "securite", "abandon technique",
              "prise partielle", "encore ouvert", "autre"]

# Ce que chaque categorie veut dire, en une ligne, pour les rapports.
EXPLICATION = {
    "objectif": "l'objectif a ete atteint",
    "stop suiveur": "stop touche APRES avoir ete remonte : gain verrouille",
    "stop initial": "stop d'origine touche : perte pleine",
    "temporel": "ferme faute de progression, pas faute de direction",
    "retournement": "sorti sur retournement, avec un gain acquis",
    "securite": "perte anormale : filet de securite declenche",
    "abandon technique": "le robot n'a PAS pu proteger la position et l'a fermee",
    "prise partielle": "une part encaissee en chemin (le trade continue)",
    "encore ouvert": "non termine (fin de periode de test)",
    "autre": "motif non reconnu",
}

# LES LIBELLES DU BROKER REEL NE SONT PAS CEUX DU SIMULATEUR.
#
# Premiere version de ce module : classee sur « stop-loss touche », le
# libelle du simulateur. En reel, Bitvavo ecrit « stop declenche sur la
# plateforme » — et 75 % des trades de l'operateur tombaient dans
# « autre ». Un rapport qui range les trois quarts de ses lignes dans
# « motif non reconnu » ne renseigne sur rien.
#
# L'ordre compte : « stop impossible a poser » commence par « stop » sans
# etre un stop touche. Les cas particuliers passent donc AVANT.
_ECHECS_TECHNIQUES = ("stop impossible", "stop sous le minimum")
_STOPS_TOUCHES = ("stop-loss", "stop declenche", "stop deja atteint")


def _sans_accents(texte: str) -> str:
    """« stop déjà atteint » et « stop deja atteint » doivent se ranger pareil."""
    for accentue, simple in (("é", "e"), ("è", "e"), ("ê", "e"), ("à", "a"),
                             ("â", "a"), ("î", "i"), ("ô", "o"), ("û", "u"),
                             ("ç", "c")):
        texte = texte.replace(accentue, simple)
    return texte


def categorie_de_sortie(motif: str, r: float) -> str:
    """Classe un motif de fermeture. `r` decide du sens d'un stop touche."""
    m = _sans_accents((motif or "").lower())

    # Le robot n'a pas pu poser de stop et a ferme pour ne pas rester
    # sans protection. Ce n'est pas un resultat de marche, c'est un
    # incident — le confondre avec une perte ferait chercher un defaut de
    # strategie la ou il y a un defaut d'execution.
    if m.startswith(_ECHECS_TECHNIQUES):
        return "abandon technique"
    if m.startswith("objectif"):
        return "objectif"
    if m.startswith(_STOPS_TOUCHES):
        # Le signe du resultat est la SEULE facon de distinguer un stop
        # d'origine d'un stop remonte : le motif enregistre est le meme.
        # Un R nul compte comme perte : les frais, eux, ont ete payes.
        return "stop suiveur" if r > 0 else "stop initial"
    if m.startswith("stop temporel"):
        return "temporel"
    if m.startswith("retournement"):
        return "retournement"
    if m.startswith("perte anormale"):
        return "securite"
    # Une prise partielle n'est pas une fin de trade : elle est comptee a
    # part par `resumer`. Elle est classee ici quand meme, sinon un trade
    # dont le drapeau `partial` s'est perdu tomberait dans « autre » sans
    # qu'on sache d'ou il vient.
    if m.startswith("prise partielle"):
        return "prise partielle"
    if m.startswith(("fin de periode", "fin de test")):
        return "encore ouvert"
    return "autre"


def repartition(trades) -> dict[str, int]:
    """Compte les trades par categorie de sortie. Toutes les cles presentes."""
    out = {c: 0 for c in CATEGORIES}
    for t in trades:
        out[categorie_de_sortie(t.reason, t.r_multiple)] += 1
    return out


def duree_lisible(heures: float) -> str:
    if heures < 48:
        return f"{heures:.0f} h"
    return f"{heures/24:.1f} j"
