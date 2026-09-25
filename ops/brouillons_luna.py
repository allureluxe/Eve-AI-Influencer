#!/usr/bin/env python3
"""Produit des BROUILLONS de photos de Luna, pour qu'il ait le choix.

POURQUOI DES BROUILLONS, ET POURQUOI PLUSIEURS
==============================================

Demande de l'operateur le 25 septembre : « les premieres sont tres
importantes ». Elles le sont doublement -- ce sont elles qui decident
si quelqu'un s'abonne, et ce sont elles qu'on verra encore dans un an
en haut du profil.

Or jusqu'ici il n'avait AUCUN choix. Une photo sortait, il la prenait
ou il attendait le lendemain : le quota Cloudflare ne permettait que
deux ou trois images FLUX.2 par jour, et les essais rates les
consommaient aussi.

    FLUX.2-dev      ~4 200 neurones l'image ->   2 par jour
    FLUX.1-schnell  ~   40 neurones l'image -> 150 par jour

Neuf brouillons coutent donc ~360 neurones sur les 10 000 offerts : il
reste de quoi refaire DEUX images en qualite finale une fois qu'il a
choisi. Chercher d'abord, depenser ensuite.

CE QUE CES IMAGES NE SONT PAS : des photos a publier. schnell est moins
realiste que FLUX.2 et refuse parfois des scenes anodines. Elles
servent a trancher un cadrage, une pose, une lumiere -- pas a finir sur
le compte.

    python3 ops/brouillons_luna.py
    python3 ops/brouillons_luna.py --scenes piscine_profil --par-scene 5
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gold_bot.env import charger_env      # noqa: E402

charger_env()

from luna.moteurs import ErreurMoteur, GenerateurImages   # noqa: E402
from luna.photos import SCENES_PAR_CLE, prompt_photo        # noqa: E402

log = logging.getLogger("brouillons")

#: Les trois premieres publications, dans l'ordre ou il les a demandees.
TRIO = ("piscine_profil", "piscine_story", "cafe")

#: LES ANGLES, ET C'EST EUX QUI FONT CHOISIR -- PAS LA GRAINE.
#:
#: Demande de l'operateur : « je veux des angles, de pres, de loin,
#: devant, derriere, de cote, comme ca je choisis ». Il a raison, et ma
#: premiere version se contentait de changer la graine : trois tirages
#: du MEME cadrage, donc trois fois la meme decision a prendre.
#:
#: Chaque angle est formule comme une photo qu'une AMIE prendrait avec
#: son telephone -- pas comme une position de camera de studio. « Shot
#: from a low angle » appartient au vocabulaire de tournage ; « holding
#: the phone down near the water » decrit un geste que quelqu'un fait
#: vraiment.
ANGLES = (
    ("pres", "framed close, head and shoulders filling the frame, "
             "the friend standing right next to her"),
    ("loin", "taken from several metres away, her whole body small in "
             "the frame, the place around her clearly visible"),
    ("devant", "taken straight in front of her at her own eye level, "
               "she is looking into the lens"),
    ("dos", "taken from behind her, she is facing away looking out at "
            "the water, her shoulders and back of her head visible, "
            "nothing suggestive, an ordinary candid back view"),
    ("cote", "taken from her side in three-quarter view, she is not "
             "looking at the camera, caught mid-movement"),
    ("plonge", "the friend is standing up and holding the phone above "
               "her, looking down, the ground visible around her"),
)

DOSSIER = Path("data/luna-brouillons")

#: Cloudflare refuse tout prompt de plus de 2048 caracteres (erreur 5006).
LIMITE_PROMPT = 2048


def _tailler(prompt: str) -> str:
    """Ramene le prompt sous la limite en coupant par la FIN.

    L'ordre des mots n'est pas neutre : les moteurs d'images ponderent
    le debut plus lourdement que la fin. Ce qui compte le plus -- l'angle
    demande, puis l'ancre d'apparence de Luna -- est en tete et doit
    survivre intact. Ce qui se perd en queue, ce sont les derniers
    details de decor, dont l'absence se voit a peine.

    Couper au dernier separateur plutot qu'au caractere exact : une
    phrase tronquee au milieu d'un mot deroute le moteur plus qu'elle ne
    l'aide.
    """
    if len(prompt) <= LIMITE_PROMPT:
        return prompt
    coupe = prompt[:LIMITE_PROMPT]
    virgule = coupe.rfind(", ")
    return coupe[:virgule] if virgule > LIMITE_PROMPT // 2 else coupe


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="  %(message)s")
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenes", nargs="*", default=list(TRIO))
    ap.add_argument("--par-scene", type=int, default=len(ANGLES),
                    help="nombre d'angles a produire par scene")
    args = ap.parse_args()

    gen = GenerateurImages()
    if not gen.disponible:
        log.error("aucun generateur configure")
        return 1

    DOSSIER.mkdir(parents=True, exist_ok=True)
    # On NE VIDE PAS le dossier : un passage rate ne doit pas effacer
    # les brouillons d'hier, qui sont peut-etre les seuls qu'il ait.
    jour = dt.datetime.now().strftime("%d-%m-%Hh%M")
    faits, rates = 0, 0

    for cle in args.scenes:
        scene = SCENES_PAR_CLE.get(cle)
        if scene is None:
            log.warning("scene inconnue : %s", cle)
            continue
        d = prompt_photo(cle)
        for n, (nom_angle, formule) in enumerate(ANGLES[:args.par_scene], 1):
            # L'ANGLE EST INSERE EN TETE DU PROMPT.
            #
            # Les moteurs d'images ponderent le debut plus lourdement
            # que la fin : mis apres trois lignes de decor, un cadrage
            # est une suggestion ; mis devant, c'est une consigne. Meme
            # raison que pour le cadrage dans `prompt_photo`.
            prompt = _tailler(f"{formule}, {d['prompt']}")
            # La graine varie AUSSI, sinon deux angles proches rendent
            # la meme pose.
            graine = 10_000 + n * 977
            destination = DOSSIER / f"{cle}-{nom_angle}-{jour}.jpg"
            try:
                brut = gen.generer(prompt, d["negatif"], graine,
                                   format="portrait", qualite="brouillon")
            except ErreurMoteur as e:
                log.warning("%s / %s : echec -- %s", cle, nom_angle,
                            str(e)[:120])
                rates += 1
                continue
            destination.write_bytes(brut)
            log.info("%s / %-7s : %d Ko -> %s", cle, nom_angle,
                     len(brut) // 1024, destination.name)
            faits += 1

    log.info("%d brouillon(s) produit(s), %d echec(s), dans %s",
             faits, rates, DOSSIER.resolve())
    return 0 if faits else 1


if __name__ == "__main__":
    raise SystemExit(main())
