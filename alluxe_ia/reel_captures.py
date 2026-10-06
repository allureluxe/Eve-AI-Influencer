"""Les Reels « captures » de @alluxe.ia : fiche (légende) pour ops/alluxe_ia_bundle.py.

Le montage est dans alluxe_ia/reel_captures_montage.py (lancé seulement si la
vidéo manque : il lit les captures de data/alluxe_ia/captures/).
"""
from __future__ import annotations

import runpy

REELS = {
    "04-construit-par-ia": {
        "legende": (
            "Je ne suis pas développeur. Pourtant, tout ça tourne seul 👇\n\n"
            "1. Claude écrit le code, et les tests qui le vérifient\n"
            "2. Un robot surveille 194 marchés, jour et nuit\n"
            "3. Il trie avant d'agir : 220 regardés, 218 refusés, 2 retenus\n"
            "4. Un labo a testé 3 254 idées\n"
            "5. Un agent IA refuse ce qui est dangereux\n\n"
            "Je te montre comment je construis tout ça, étape par étape, sans jargon.\n"
            "👉 Abonne-toi pour la suite\n"
            "📎 Le kit gratuit : lien dans ma bio\n\n"
            "#ia #intelligenceartificielle #claude #chatgpt #automatisation #nocode #productivite"
        ),
    },
}


def rendre(reel_id: str) -> None:
    if reel_id not in REELS:
        raise KeyError(reel_id)
    runpy.run_module("alluxe_ia.reel_captures_montage", run_name="__main__")
