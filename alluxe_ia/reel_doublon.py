"""Reel 05 « Mon IA tournait en double » -- l'incident réel du 4-5 oct. 2026.

    python3 -m alluxe_ia.reel_doublon   ->  data/alluxe_ia/reels/05-ia-en-double.mp4

Tout est vrai et daté (voir la mémoire dual-live-relance-ecrase-etat-5oct) :
le 2e robot réel (dual-live) a été démarré le 4 oct. à 22 h 31 en plus du
robot principal ; les deux écrivaient le même fichier d'état et se
l'écrasaient ; l'appli affichait 3 positions sur 8 ; arrêté le 5 oct. à
17 h 04, soit 18 h 33 de double marche. Les lignes de journal affichées
sont les vraies (journalctl), sans heures de la machine ni nom de plateforme.
L'écran Claude Code est une RECONSTITUTION de la session du 5 oct.

Règles (CLAUDE.md) : histoire technique seulement -- aucun montant, aucun
résultat, aucune plateforme, aucune crypto nommée.
"""
from __future__ import annotations

import math
import os

from PIL import Image, ImageDraw, ImageFont

import glob

from alluxe_ia.reel_captures_montage import (
    CREME, ENCRE, F, FPS, H, HT, JAUNE, NOIR, P, RACINE, W, decor, ease, ecran, legende, mettre_logo, produire, texte)

# Vraies captures (7 oct., l'opérateur : « mets des captures ») : la vraie sortie du
# serveur rendue dans un terminal (term5/), et l'écran Agent de l'appli.
DOUBLE = [Image.open(f).convert("RGB") for f in sorted(glob.glob(H + "term5/double_*.png"))]
ARRET = [Image.open(f).convert("RGB") for f in sorted(glob.glob(H + "term5/arret_*.png"))]
AGENT = Image.open(H + "x_Agent.png").convert("RGB").crop((0, 1150, 1080, 2338))

MONO = lambda s: ImageFont.truetype(P + "JetBrainsMono.ttf", s)  # noqa: E731
VERT, CORAIL, MENTHE, GRISC = (126, 224, 143), (255, 128, 96), (92, 224, 198), (150, 150, 150)
CLAUDE_OR = (217, 119, 87)

ROBOT1 = [("etat repris : 319 trades", None), ("194 marchés vus", None),
          ("position ouverte", VERT), ("mémoire écrite", JAUNE), ("194 marchés vus", None),
          ("mémoire écrite", JAUNE), ("194 marchés vus", None), ("mémoire écrite", JAUNE)]
ROBOT2 = [("[DUAL] demarrage", CORAIL), ("etat repris : 322 trades", None),
          ("max 1 position", None), ("mémoire écrite", JAUNE),
          ("194 marchés vus", None), ("mémoire écrite", JAUNE), ("mémoire écrite", JAUNE)]
CLAUDE = [("> Fais-moi un contrôle du robot réel,", (255, 255, 255)), ("  tout ce qui est affiché est faux.", (255, 255, 255)),
          ("", None), ("● 2 robots réels tournent sur", CLAUDE_OR), ("  le MÊME fichier d'état.", CLAUDE_OR),
          ("", None), ("● Bash(systemctl stop", (230, 230, 230)), ("        robot-dual-live)", (230, 230, 230)),
          ("  └ arrêté", GRISC), ("", None), ("● Mémoire relue :", (230, 230, 230)),
          ("  └ 8 positions sur 8 : OK", VERT)]


def terminal(titre: str, lignes, n_visibles: int, largeur: int, hauteur: int, taille=30, couleur_titre=MENTHE):
    """Un terminal dessiné (vraies lignes), révélées une à une."""
    t = Image.new("RGB", (largeur, hauteur), (26, 26, 26)); d = ImageDraw.Draw(t)
    d.rounded_rectangle((14, 14, largeur - 14, 84), 14, outline=couleur_titre, width=3)
    d.ellipse((34, 39, 54, 59), fill=couleur_titre); d.text((68, 30), titre, font=MONO(30), fill=couleur_titre)
    y = 110; f = MONO(taille)
    for texte_l, c in lignes[:n_visibles]:
        d.text((24, y), texte_l, font=f, fill=c or (205, 205, 205)); y += int(taille * 1.55)
    return t


def coller(img, carte, x, y, rayon=30):
    m = Image.new("L", carte.size, 0); ImageDraw.Draw(m).rounded_rectangle((0, 0, *carte.size), rayon, fill=255)
    dd = ImageDraw.Draw(img)
    dd.rounded_rectangle((x + 10, y + 14, x + carte.width + 18, y + carte.height + 22), rayon + 6, fill=JAUNE)
    dd.rounded_rectangle((x - 6, y - 6, x + carte.width + 6, y + carte.height + 6), rayon + 6, fill=ENCRE)
    img.paste(carte, (x, y), m)


def glitch(img, force):
    """Décalage rouge/bleu + bandes déplacées : l'affichage qui ment."""
    if force <= 0: return img
    r, g, b = img.split(); dx = int(18 * force)
    img = Image.merge("RGB", (r.transform(r.size, Image.AFFINE, (1, 0, -dx, 0, 1, 0)), g,
                              b.transform(b.size, Image.AFFINE, (1, 0, dx, 0, 1, 0))))
    for k in range(5):
        y = int((k * 397 + force * 1000) % (HT - 80)); h = 40 + k * 9
        bande = img.crop((0, y, W, y + h)); img.paste(bande, (int(math.sin(k * 7 + force * 9) * 60 * force), y))
    return img


def image(t: float) -> Image.Image:
    img = Image.new("RGB", (W, HT), CREME)
    scene = sum(t >= s for s in (2.4, 5.2, 8.0, 10.6, 13.0, 15.4))
    if scene < 6: decor(img, t, scene + 2)
    d = ImageDraw.Draw(img)
    if t < 2.4:                                    # 1. accroche : le vrai journal monte sous le titre
        ecran(img, DOUBLE[-1], 900 + int((1 - ease(t * 2)) * 400), 1000, decal=0.0)
        mettre_logo(img, 190)
        texte(d, 260, [("Mon IA tournait", None), ("EN DOUBLE.", JAUNE)], 128, t=t / 0.8)
        if t > 1.1: texte(d, 610, [("Et personne ne", None), ("l'avait vu.", None)], 84, t=(t - 1.1) / 0.7)
    elif t < 5.2:                                  # 2. le vrai journal : deux démarrages
        u = (t - 2.4) / 2.8
        k = min(len(DOUBLE) - 1, int(u * 1.3 * (len(DOUBLE) - 1)))
        ecran(img, DOUBLE[k], 140, 1700, decal=1.0)
        legende(img, d, 1300, [("2 robots.", None), ("1 seule mémoire.", JAUNE)], 118, u, 1)
    elif t < 8.0:                                  # 3. l'affichage qui ment
        u = (t - 5.2) / 2.8
        f = F(60); s = "positions affichées dans l'appli"
        d.text(((W - f.getlength(s)) / 2, 330), s, font=f, fill=ENCRE)
        n = "8" if u < 0.35 else "3"
        fg = F(520); d.text(((W - fg.getlength(n)) / 2, 380), n, font=fg, fill=CORAIL if n == "3" else ENCRE,
                            stroke_width=10, stroke_fill=ENCRE)
        if u > 0.45:
            f2 = F(64); s2 = "il y en avait 8."
            d.rounded_rectangle(((W - f2.getlength(s2)) / 2 - 26, 1000, (W + f2.getlength(s2)) / 2 + 26, 1100), 28, fill=JAUNE, outline=ENCRE, width=5)
            d.text(((W - f2.getlength(s2)) / 2, 1016), s2, font=f2, fill=NOIR)
        legende(img, d, 1330, [("Ils s'effaçaient", None), ("l'un l'autre.", JAUNE)], 118, u, 2)
        force = max(0.0, 1 - abs(u - 0.38) * 6)   # le glitch au moment où 8 devient 3
        img = glitch(img, force); d = ImageDraw.Draw(img)
    elif t < 10.6:                                 # 4. la durée
        u = (t - 8.0) / 2.6
        minutes = int((18 * 60 + 33) * ease(u * 1.6))
        s = f"{minutes // 60:02d} h {minutes % 60:02d}"
        f = F(250); x = (W - f.getlength("18 h 33")) / 2
        d.rounded_rectangle((x - 40, 380, x + f.getlength("18 h 33") + 40, 700), 50, fill=ENCRE)
        d.text((x, 410), s, font=f, fill=JAUNE)
        f2 = F(48); s2 = "du 4 oct. 22 h 31 au 5 oct. 17 h 04"
        d.text(((W - f2.getlength(s2)) / 2, 740), s2, font=f2, fill=ENCRE)
        legende(img, d, 1250, [("Pendant 18 heures.", None), ("Personne n'a rien vu.", JAUNE)], 92, u, 3)
    elif t < 13.0:                                 # 5. Claude trouve et arrête (vraie sortie du serveur)
        u = (t - 10.6) / 2.4
        k = min(len(ARRET) - 1, int(u * 1.4 * (len(ARRET) - 1)))
        ecran(img, ARRET[k], 140, 1700, decal=1.0)
        legende(img, d, 1250, [("Claude l'a trouvé.", None), ("Et arrêté.", JAUNE)], 118, u, 4)
    elif t < 15.4:                                 # 6. l'agent refuse d'y toucher (capture de l'appli)
        u = (t - 13.0) / 2.4
        ecran(img, AGENT, 140, 1500, zoom=1.0 + 0.05 * ease(u))
        legende(img, d, 1180, [("Et mon agent IA", None), ("refuse d'y toucher.", JAUNE)], 98, u, 5)
    else:                                          # 6. fin
        img.paste(Image.new("RGB", (W, HT), JAUNE)); d = ImageDraw.Draw(img)
        from alluxe_ia.reel_captures_montage import logo
        l = logo.resize((300, 300)); img.paste(l, ((W - 300) // 2, 380), l)
        f = F(92)
        for i, s in enumerate(["Je raconte mes", "vraies erreurs."]):
            d.text(((W - f.getlength(s)) / 2, 780 + i * 112), s, font=f, fill=NOIR)
        f2 = F(60); s = "Abonne-toi : @alluxe.ia"
        d.rounded_rectangle(((W - f2.getlength(s)) / 2 - 30, 1110, (W + f2.getlength(s)) / 2 + 30, 1210), 50, fill=NOIR)
        d.text(((W - f2.getlength(s)) / 2, 1125), s, font=f2, fill=JAUNE)
    return img


REELS = {
    "05-ia-en-double": {
        "legende": (
            "Mon IA tournait en double pendant 18 heures. Et personne ne l'avait vu 😳\n\n"
            "Un 2e robot avait été relancé par erreur. Les deux écrivaient dans le même fichier "
            "de mémoire et s'effaçaient l'un l'autre : l'appli affichait 3 positions… il y en avait 8.\n\n"
            "Claude a trouvé la cause en lisant les journaux, a arrêté le doublon, et tout est revenu.\n\n"
            "La leçon : un garde-fou qui ne s'exécute pas ne protège pas.\n\n"
            "Je ne suis pas développeur. Je construis des systèmes réels avec l'IA, et je raconte "
            "aussi mes vraies erreurs.\n"
            "👉 Abonne-toi pour la suite\n"
            "📎 Le kit gratuit : lien dans ma bio\n\n"
            "#ia #intelligenceartificielle #claude #automatisation #nocode #erreur #tech"
        ),
    },
}


def rendre(reel_id: str = "05-ia-en-double") -> None:
    produire(image, 17.4, os.path.join(RACINE, "data", "alluxe_ia", "reels", f"{reel_id}.mp4"), graine="doublon")


if __name__ == "__main__":
    rendre()
