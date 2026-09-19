#!/usr/bin/env python3
"""Genere les images de profil de Luna : portrait et couverture.

Ecrit le 19 sept. 2026, pour les comptes Instagram et Facebook. Trois
usages, deux cadrages :

  - PORTRAIT (carre) : photo de profil Instagram ET Facebook. Le visage
    doit rester lisible dans un cercle de 110 pixels, donc cadre serre --
    une photo en pied devient une tache a cette taille.
  - COUVERTURE (tres large, 1640x624) : le bandeau Facebook. Surtout PAS
    un portrait etire : un visage dans ce format est deforme et coupe par
    la photo de profil qui se superpose en bas a gauche. Une scene
    d'ambiance ou elle est petite, ou absente, tient beaucoup mieux.

POURQUOI IL TOURNE LA NUIT. Les deux fournisseurs d'images sont sur des
paliers gratuits : Hugging Face est epuise pour le mois, et Cloudflare
plafonne a 10 000 "neurones" par jour -- brules le 19 sept. en essayant
FLUX.2, l'age, le style et le cadrage. Le quota Cloudflare repart a
minuit UTC ; ce script est programme juste apres.

    python3 ops/photos_profil_luna.py
"""
from __future__ import annotations

import os
import sys
import time

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from gold_bot.env import charger_env  # noqa: E402

charger_env()

from luna.moteurs import GenerateurImages  # noqa: E402
from luna.persona import LUNA  # noqa: E402
from luna.photos import NEGATIF, RENDU, SIGNATURE  # noqa: E402

DOSSIER = os.path.join(RACINE, "data", "luna-profil")

PORTRAIT = (
    "head and shoulders portrait, her face fills most of the frame, "
    "centred composition, looking straight at the camera, warm natural "
    "daylight from a window, plain uncluttered background, relaxed "
    "confident half-smile")

# Elle est LOIN et petite : une couverture doit poser une ambiance, pas
# montrer un visage (la photo de profil s'y superpose en bas a gauche).
COUVERTURE = (
    "very wide panoramic banner photograph, a young woman seen small and "
    "from behind at a desk by a large window, open laptop and handwritten "
    "notes, a cup of coffee, warm late afternoon light, a city skyline "
    "blurred far outside the window, lots of empty space in the upper "
    "right of the frame, calm studious atmosphere, cinematic wide crop")


def _generer(nom: str, scene: str, essais: int = 20) -> bool:
    prompt = ", ".join((LUNA.apparence.ancre, scene, RENDU, SIGNATURE))
    chemin = os.path.join(DOSSIER, nom)
    for essai in range(essais):
        try:
            image = GenerateurImages().generer(
                prompt, NEGATIF, LUNA.apparence.graine)
        except Exception as exc:                             # noqa: BLE001
            dernier = essai == essais - 1
            transitoire = "429" in str(exc) or "4006" in str(exc)
            if dernier or not transitoire:
                print(f"{nom} : echec -- {str(exc)[:140]}")
                return False
            time.sleep(120)
            continue
        os.makedirs(DOSSIER, exist_ok=True)
        with open(chemin, "wb") as f:
            f.write(image)
        print(f"{nom} : {len(image) // 1024} Ko -> {chemin}")
        return True
    return False


def main() -> int:
    ok = 0
    for nom, scene in (("portrait.jpg", PORTRAIT),
                       ("couverture.jpg", COUVERTURE)):
        if _generer(nom, scene):
            ok += 1
    print(f"\n{ok}/2 image(s) generee(s) dans {DOSSIER}")
    return 0 if ok == 2 else 1


if __name__ == "__main__":
    raise SystemExit(main())
