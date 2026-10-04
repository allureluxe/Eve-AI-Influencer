"""Les Reels de @alluxe.ia : du texte animé en 9:16, même charte que les slides.

Un Reel est une suite de « temps » (Temps) : une phrase qui entre en
glissant, reste affichée, puis laisse la place à la suivante. Le dernier
temps porte l'appel (« Lien en bio ») dans le cartouche ambre des slides.

    python3 -m alluxe_ia.reel 01-tout-construit   ->  data/alluxe_ia/reels/<id>.mp4

ZONES SÛRES. Instagram couvre le haut (~220 px : onglets), le bas
(~420 px : légende, son) et la droite (~140 px : boutons j'aime,
commentaire, partage) d'un Reel de 1080 x 1920. Tout le texte reste dans
le rectangle libre ; le reste ne porte que le fond.

SON. Une musique composée par programme (`alluxe_ia/musique.py`, une
variante par Reel). Jusqu'au 4 oct. c'était une piste muette, et le
premier Reel a fait 5 vues : un Reel silencieux part avec un gros
handicap. La musique d'Instagram n'est ouverte aux programmes que pour
les comptes reliés par Facebook, pas par la connexion « Instagram ».

Nécessite ffmpeg.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass

from PIL import Image, ImageDraw

from alluxe_ia.musique import ecrire_wav
from alluxe_ia.slides import (AMBRE, DOUX, ENCRE, FOND, FOND_HAUT, MENTHE, NOM, PSEUDO,
                              couper, medaillon, mono_police, texte_police, titre_police)

LARGEUR, HAUTEUR = 1080, 1920
IPS = 30
GAUCHE = 90
LARGEUR_TEXTE = 1080 - GAUCHE - 160      # la colonne de boutons à droite
HAUT_LIBRE, BAS_LIBRE = 300, 1450        # entre les onglets et la légende
RAYON_LOGO = 250                          # logo de 500 px (double le 4 oct.)
HAUT_LOGO = HAUT_LIBRE - 40               # haut du logo, juste sous les onglets
BAS_LOGO = HAUT_LOGO + 2 * RAYON_LOGO
ENTREE = 0.5                             # secondes de glissement à l'arrivée

ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(ICI)


@dataclass
class Temps:
    texte: str
    duree: float
    taille: int = 92
    couleur: tuple = ENCRE
    sous_texte: str = ""
    mot_cle: str = ""
    amorce: str = "Le kit gratuit :"


# Les Reels, par identifiant. Le premier reprend l'accroche du post 1.
REELS: dict[str, dict] = {
    "01-tout-construit": {
        "legende": (
            "Je ne sais pas coder. Tout ça, je l'ai construit en parlant à Claude "
            "et à ChatGPT.\n\n"
            "Ici je montre les coulisses : comment c'est fait, et surtout ce qui casse.\n\n"
            "📎 Le kit du constructeur (gratuit) : lien dans ma bio.\n\n"
            "#ia #claude #chatgpt #vibecoding #buildinpublic #automatisation #nocode"),
        "temps": [
            Temps("Je ne sais pas coder.", 2.6, taille=118),
            Temps("J'ai quand même construit tout ça avec l'IA :", 3.0, taille=96, couleur=MENTHE),
            Temps("Un labo qui teste des idées jour et nuit.", 2.8),
            Temps("Des comptes d'essai à argent fictif.", 2.8),
            Temps("Une appli sur mon téléphone.", 2.5),
            Temps("Un agent qui écrit du code à ma place.", 2.8),
            Temps("Et cette page, qui se publie toute seule.", 3.0),
            Temps("Je te montre comment.", 3.0, taille=100, couleur=ENCRE,
                  sous_texte="les prompts que j'utilise vraiment.",
                  mot_cle="Lien en bio"),
        ],
    },
}


def _fond() -> Image.Image:
    img = Image.new("RGB", (LARGEUR, HAUTEUR), FOND)
    d = ImageDraw.Draw(img)
    for y in range(HAUTEUR // 2):
        t = 1 - y / (HAUTEUR / 2)
        d.line([(0, y), (LARGEUR, y)],
               fill=tuple(int(FOND[i] + (FOND_HAUT[i] - FOND[i]) * t) for i in range(3)))
    # Signature en haut de la zone libre : le même en-tête que les slides.
    # Logo du Reel : cercle légèrement agrandi pour laisser respirer ALLUXE.
    # 4 oct. 2026, operateur : « le logo du Reel trop petit, double-le » ->
    # 250 -> 500 px, contenu ALLUXE double aussi (190 -> 380 px).
    r = RAYON_LOGO
    m = medaillon(2 * r, contenu_taille=380)
    img.paste(m, (GAUCHE, HAUT_LOGO), m)
    cy = HAUT_LOGO + r
    d.text((GAUCHE + 2 * r + 26, cy - 4), NOM, font=titre_police(40), fill=ENCRE, anchor="ls")
    d.text((GAUCHE + 2 * r + 26, cy + 36), PSEUDO, font=texte_police(28), fill=DOUX, anchor="ls")
    return img


def _calque(t: Temps) -> tuple[Image.Image, int]:
    """Le bloc de texte d'un temps, sur fond transparent, et sa hauteur."""
    police = titre_police(t.taille)
    lignes = couper(t.texte, police, LARGEUR_TEXTE)
    interligne = int(t.taille * 1.1)
    h = interligne * len(lignes)
    if t.mot_cle:
        h += 70 + 80 + 120
    if t.sous_texte:
        h += 30 + 50 * len(couper(t.sous_texte, texte_police(40), LARGEUR_TEXTE))
    img = Image.new("RGBA", (LARGEUR, h + 20), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    y = 0
    for ligne in lignes:
        d.text((GAUCHE, y), ligne, font=police, fill=t.couleur)
        y += interligne
    if t.mot_cle:
        y += 70
        # L'amorce sur sa ligne, le cartouche dessous : « Lien en bio »
        # ne tient pas a cote dans la colonne libre.
        d.text((GAUCHE, y + 6), t.amorce, font=titre_police(56), fill=ENCRE)
        y += 80
        pm = mono_police(84)
        w = int(d.textlength(t.mot_cle, font=pm))
        x = GAUCHE
        d.rounded_rectangle((x, y - 8, x + w + 44, y + 100), radius=18, fill=AMBRE)
        d.text((x + 22, y), t.mot_cle, font=pm, fill=FOND)
        y += 120
    if t.sous_texte:
        y += 30
        for ligne in couper(t.sous_texte, texte_police(40), LARGEUR_TEXTE):
            d.text((GAUCHE, y), ligne, font=texte_police(40), fill=DOUX)
            y += 50
    return img, h


def _adoucir(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return 1 - (1 - x) ** 3


def images(temps: list[Temps]):
    """Rend chaque image du Reel, dans l'ordre."""
    fond = _fond()
    total = sum(t.duree for t in temps)
    debut = 0.0
    for k, t in enumerate(temps):
        calque, h = _calque(t)
        # Le texte se centre SOUS le logo agrandi, sans jamais le recouvrir.
        y0 = max(BAS_LOGO + 40, (BAS_LOGO + 40 + BAS_LIBRE) // 2 - h // 2)
        n = round(t.duree * IPS)
        for i in range(n):
            s = i / IPS
            # Le premier temps est déjà en place : la première image sert
            # de miniature au Reel, elle ne doit pas être vide.
            p = 1.0 if k == 0 else _adoucir(s / ENTREE)
            img = fond.copy()
            c = calque.copy()
            if p < 1:
                c.putalpha(c.getchannel("A").point(lambda a, p=p: int(a * p)))
            img.paste(c, (0, int(y0 + (1 - p) * 60)), c)
            # Barre de progression fine, dans la zone libre.
            d = ImageDraw.Draw(img)
            avance = (debut + s) / total
            d.rectangle((GAUCHE, BAS_LIBRE + 40, LARGEUR - 160, BAS_LIBRE + 46), fill=(40, 56, 51))
            d.rectangle((GAUCHE, BAS_LIBRE + 40,
                         GAUCHE + int((LARGEUR - 160 - GAUCHE) * avance), BAS_LIBRE + 46), fill=MENTHE)
            yield img
        debut += t.duree


def rendre(reel_id: str, sortie: str | None = None) -> str:
    temps = REELS[reel_id]["temps"]
    sortie = sortie or os.path.join(RACINE, "data", "alluxe_ia", "reels", f"{reel_id}.mp4")
    os.makedirs(os.path.dirname(sortie), exist_ok=True)
    duree = sum(t.duree for t in temps)
    piste = sortie + ".musique.wav"
    ecrire_wav(piste, duree, graine=reel_id)
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{LARGEUR}x{HAUTEUR}",
           "-r", str(IPS), "-i", "-",
           "-i", piste,
           "-t", f"{duree:.2f}",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-profile:v", "high",
           "-preset", "medium", "-crf", "20", "-movflags", "+faststart",
           "-c:a", "aac", "-b:a", "128k", "-shortest", sortie]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for img in images(temps):
        p.stdin.write(img.tobytes())
    p.stdin.close()
    code = p.wait()
    os.remove(piste)
    if code != 0:
        raise RuntimeError("ffmpeg a échoué")
    with open(sortie + ".legende.txt", "w", encoding="utf-8") as f:
        f.write(REELS[reel_id]["legende"])
    return sortie


if __name__ == "__main__":
    print(rendre(sys.argv[1] if len(sys.argv) > 1 else "01-tout-construit"))
