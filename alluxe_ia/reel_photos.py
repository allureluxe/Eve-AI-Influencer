"""Reel « une photo par idée » : chaque idée a sa photo plein écran, la
coupe tombe sur le rythme, le logo reste grand et visible tout du long.

Demandes de l'opérateur (4 oct.) : des images en rapport avec le sujet,
une musique tendance accrocheuse calée sur le rythme, le logo bien visible
(pas petit à côté de l'écriture), un sujet fort.

    python3 -m alluxe_ia.reel_photos 30-jamais-dans-une-ia

La musique est celle d'Instagram (bundle.social, ops/alluxe_ia_bundle.py) ;
la piste composée sert d'aperçu. Limite honnête : on ne choisit pas le
passage du morceau et on ne peut pas l'écouter d'ici, les coupes suivent
donc le tempo annoncé (BPM), à vérifier à l'oreille.
"""
from __future__ import annotations

import math
import os
import subprocess
import sys
from dataclasses import dataclass

from PIL import Image, ImageDraw

from alluxe_ia.musique import ecrire_wav
from alluxe_ia.slides import couper, medaillon, texte_police, titre_police

L, H, IPS = 1080, 1920, 30
G, D = 80, 920                     # la colonne de droite porte les boutons d'Instagram
HAUT, BAS = 250, 1480              # sous les onglets, au-dessus de la légende
ROUGE = (230, 45, 45)
BLANC = (255, 255, 255)
NOIR = (12, 14, 14)
ICI = os.path.dirname(os.path.abspath(__file__))
RACINE = os.path.dirname(ICI)


@dataclass
class Scene:
    photo: str                     # chemin relatif à alluxe_ia/fonds/
    titre: str
    sous_titre: str = ""
    numero: str = ""
    rouge: str = ""                # mot du titre écrit en rouge
    appel: bool = False


REELS = {
    "30-jamais-dans-une-ia": {
        # LABOUR (Paris Paloma), choix de l'opérateur après MJ (4 oct.).
        # Tempo non mesuré ici (~88 BPM). 5 temps par image (3,4 s) : à 4 temps,
        # l'opérateur trouvait les images un peu trop rapides.
        "son": "3635531743388988",
        "bpm": 88.0,
        "temps_par_scene": 5,
        "legende": (
            "5 choses à ne JAMAIS coller dans ChatGPT 🔒\n\n"
            "Tes conversations sont enregistrées. Selon les réglages, elles peuvent servir "
            "à entraîner les modèles. Avant de coller quoi que ce soit, relis cette liste.\n\n"
            "Enregistre ce Reel et envoie-le à quelqu'un qui colle tout dans l'IA.\n\n"
            "📎 Le kit du constructeur (gratuit) : lien dans ma bio.\n\n"
            "#chatgpt #ia #intelligenceartificielle #cybersecurite #donneespersonnelles "
            "#astuce #claude"),
        "scenes": [
            Scene("reel-30/0.jpg", "5 choses à ne JAMAIS coller dans ChatGPT.", rouge="JAMAIS"),
            Scene("reel-30/1.jpg", "Tes mots de passe.", "Aucune raison d'en donner un à une IA.", "1"),
            Scene("reel-30/2.jpg", "Ta carte bancaire, ton IBAN.", "Même pour « vérifier un calcul ».", "2"),
            Scene("reel-30/3.jpg", "La santé des autres.", "Dossiers, infos d'un proche : pas à toi de les donner.", "3"),
            Scene("reel-30/4.jpg", "Les documents confidentiels.", "Contrats, chiffres de ta boîte.", "4"),
            Scene("reel-30/5.jpg", "Tes papiers d'identité.", "Anonymise avant : nom, adresse, numéros.", "5"),
            Scene("reel-30/1.jpg", "Et vérifie ce réglage :",
                  "Paramètres > Données > désactive l'entraînement sur tes conversations."),
            Scene("reel-30/0.jpg", "Enregistre-le.", "Le kit gratuit est en lien dans la bio.",
                  appel=True),
        ],
    },
}

_cache: dict = {}


def _photo(chemin: str) -> Image.Image:
    if chemin not in _cache:
        src = Image.open(os.path.join(ICI, "fonds", chemin)).convert("RGB")
        k = max(L * 1.12 / src.width, H * 1.12 / src.height)
        _cache[chemin] = src.resize((int(src.width * k) + 1, int(src.height * k) + 1), Image.LANCZOS)
    return _cache[chemin]


def _voile() -> Image.Image:
    if "voile" not in _cache:
        v = Image.new("L", (L, H))
        d = ImageDraw.Draw(v)
        for y in range(0, H, 4):
            t = y / H
            a = 150 * max(0.0, 1 - t / 0.25) + 235 * min(1.0, max(0.0, (t - 0.3) / 0.45))
            d.rectangle((0, y, L, y + 4), fill=int(min(225, a)))
        _cache["voile"] = v
    return _cache["voile"]


def _rebond(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return 1 + 2.2 * (x - 1) ** 3 + 1.2 * (x - 1) ** 2 if x < 1 else 1.0


def _logo(img: Image.Image, d: ImageDraw.ImageDraw, accent) -> None:
    """Le logo, GRAND : 270 px, avec le nom en gros à côté."""
    m = medaillon(270, contenu_taille=206)
    img.paste(m, (G, HAUT), m)
    d.text((G + 292, HAUT + 82), "alluxe.ia", font=titre_police(72), fill=BLANC,
           stroke_width=3, stroke_fill=NOIR)
    d.text((G + 294, HAUT + 170), "construire avec l'IA", font=texte_police(38, gras=True),
           fill=accent, stroke_width=3, stroke_fill=NOIR)


def image(reel_id: str, t: float) -> Image.Image:
    cfg = REELS[reel_id]
    accent = (255, 214, 64)       # jaune vif : le plus visible sur photo sombre
    duree_scene = 60.0 / cfg["bpm"] * cfg["temps_par_scene"]
    i = min(int(t / duree_scene), len(cfg["scenes"]) - 1)
    s = cfg["scenes"][i]
    tl = t - i * duree_scene                      # temps dans la scène

    # Fond : la photo, avec un « punch » à la coupe puis un zoom lent.
    src = _photo(s.photo)
    z = 1.0 + 0.06 * max(0.0, 1 - tl / 0.25) + 0.05 * (tl / duree_scene)
    w, h = int(L * 1.12 / z), int(H * 1.12 / z)
    x0, y0 = (src.width - w) // 2, (src.height - h) // 2
    img = src.crop((x0, y0, x0 + w, y0 + h)).resize((L, H), Image.BILINEAR)
    if s.appel:
        img = Image.blend(img, Image.new("RGB", (L, H), accent), 0.88)
    else:
        img = Image.composite(Image.new("RGB", (L, H), NOIR), img, _voile())
    d = ImageDraw.Draw(img)
    # Éclair blanc très bref à chaque coupe : l'œil sent le rythme.
    if tl < 0.08 and i > 0:
        img = Image.blend(img, Image.new("RGB", (L, H), BLANC), 0.35 * (1 - tl / 0.08))
        d = ImageDraw.Draw(img)

    _logo(img, d, accent if not s.appel else NOIR)
    encre = NOIR if s.appel else BLANC
    entree = _rebond(tl / 0.3)

    y = 720 if s.numero else 860
    if s.numero:
        pn = titre_police(int(330 * (0.6 + 0.4 * entree)))
        d.text((G - 10, y - 60), s.numero, font=pn, fill=accent, stroke_width=10, stroke_fill=NOIR)
        y += 300
    taille = 128 if i == 0 else (104 if len(s.titre) < 30 else 92)   # l'accroche, plus grosse
    p = titre_police(int(taille * (0.85 + 0.15 * entree)))
    lignes = couper(s.titre, p, D - G)
    for li in lignes:
        x = G
        if s.rouge and s.rouge in li:
            avant, apres = li.split(s.rouge, 1)
            d.text((x, y), avant, font=p, fill=encre, stroke_width=3, stroke_fill=NOIR)
            x += d.textlength(avant, font=p)
            wr = d.textlength(s.rouge, font=p)
            d.rounded_rectangle((x - 8, y + p.size * 0.1, x + wr + 8, y + p.size * 1.08), radius=12, fill=ROUGE)
            d.text((x, y), s.rouge, font=p, fill=BLANC)
            x += wr
            d.text((x, y), apres, font=p, fill=encre, stroke_width=3, stroke_fill=NOIR)
        else:
            d.text((x, y), li, font=p, fill=encre, stroke_width=0 if s.appel else 3, stroke_fill=NOIR)
        y += int(p.size * 1.06)
    if s.sous_titre and tl > 0.25:
        ps = texte_police(46, gras=True)
        y += 24
        for li in couper(s.sous_titre, ps, D - G):
            d.text((G, y), li, font=ps, fill=encre if s.appel else (235, 235, 230),
                   stroke_width=0 if s.appel else 2, stroke_fill=NOIR)
            y += int(ps.size * 1.3)
    if s.appel:
        pb = titre_police(84)
        texte = "Lien en bio"
        wb = d.textlength(texte, font=pb)
        yb = min(y + 50, BAS - 140)
        d.rounded_rectangle((G - 6, yb, G + wb + 60, yb + 130), radius=65, fill=NOIR)
        d.text((G + 28, yb + 16), texte, font=pb, fill=accent)
    # Pas de barre de progression (4 oct., opérateur : inutile).
    return img


def duree(reel_id: str) -> float:
    cfg = REELS[reel_id]
    return 60.0 / cfg["bpm"] * cfg["temps_par_scene"] * len(cfg["scenes"])


def rendre(reel_id: str, sortie: str | None = None) -> str:
    sortie = sortie or os.path.join(RACINE, "data", "alluxe_ia", "reels", f"{reel_id}.mp4")
    os.makedirs(os.path.dirname(sortie), exist_ok=True)
    dt = duree(reel_id)
    piste = ecrire_wav(sortie + ".musique.wav", dt, graine=reel_id)
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{L}x{H}", "-r", str(IPS), "-i", "-",
           "-i", piste, "-t", f"{dt:.2f}",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-profile:v", "high", "-preset", "medium",
           "-crf", "20", "-movflags", "+faststart", "-c:a", "aac", "-b:a", "128k", "-shortest", sortie]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for k in range(int(dt * IPS)):
        p.stdin.write(image(reel_id, k / IPS).tobytes())
    p.stdin.close()
    code = p.wait()
    os.remove(piste)
    if code != 0:
        raise RuntimeError("ffmpeg a échoué")
    with open(sortie + ".legende.txt", "w", encoding="utf-8") as f:
        f.write(REELS[reel_id]["legende"])
    return sortie


if __name__ == "__main__":
    print(rendre(sys.argv[1] if len(sys.argv) > 1 else "30-jamais-dans-une-ia"))
