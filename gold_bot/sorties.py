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
              "retournement", "encore ouvert", "autre"]

# Ce que chaque categorie veut dire, en une ligne, pour les rapports.
EXPLICATION = {
    "objectif": "l'objectif a ete atteint",
    "stop suiveur": "stop touche APRES avoir ete remonte : gain verrouille",
    "stop initial": "stop d'origine touche : perte pleine",
    "temporel": "ferme faute de progression, pas faute de direction",
    "retournement": "sorti sur retournement, avec un gain acquis",
    "encore ouvert": "non termine (fin de periode de test)",
    "autre": "motif non reconnu",
}


def categorie_de_sortie(motif: str, r: float) -> str:
    """Classe un motif de fermeture. `r` decide du sens d'un stop touche."""
    m = (motif or "").lower()
    if m.startswith("objectif"):
        return "objectif"
    if m.startswith("stop-loss"):
        # Le signe du resultat est la SEULE facon de distinguer un stop
        # d'origine d'un stop remonte : le motif enregistre est le meme.
        # Un R nul compte comme perte : les frais, eux, ont ete payes.
        return "stop suiveur" if r > 0 else "stop initial"
    if m.startswith("stop temporel"):
        return "temporel"
    if m.startswith("retournement"):
        return "retournement"
    if m.startswith("fin de periode"):
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
