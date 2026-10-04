"""Reel « conversation animée » : une vraie scène qui bouge à chaque image.

Pourquoi ce format (4 oct.) : le Reel 01, des phrases sur fond fixe, a
touché 2 personnes. Instagram montre moins les Reels faits surtout de
texte ; ce qui retient dans les comptes sans visage, c'est une scène en
mouvement, une accroche de 6 à 8 mots et une chute. Ici : la question
s'écrit, l'IA répond lettre par lettre, un tampon FAUX tombe, la
correction s'affiche, la bonne réponse s'écrit.

    python3 -m alluxe_ia.reel_chat   ->  data/alluxe_ia/reels/02-ia-invente-un-prix.mp4

La musique : celle d'Instagram via bundle.social (ops/alluxe_ia_bundle.py) ;
la piste composée (alluxe_ia/musique.py) sert d'aperçu et de secours.
"""
from __future__ import annotations

import math
import os
import subprocess

from PIL import Image, ImageDraw, ImageFilter

from alluxe_ia.musique import ecrire_wav
from alluxe_ia.slides import AMBRE, MENTHE, couper, mono_police, texte_police, titre_police

# VERSION CLAIRE (4 oct., demande opérateur) : un texte foncé sur fond clair se lit le
# mieux, et le sombre est assombri encore par la compression d'Instagram.
FOND = (250, 247, 240)          # crème
ENCRE = (17, 20, 19)            # presque noir
DOUX = (112, 120, 116)
FENETRE = (255, 255, 255)
BORD = (226, 222, 212)
BULLE_IA = (238, 240, 238)
BULLE_MOI = (18, 150, 128)       # menthe foncée : texte blanc lisible
SURLIGNEUR = (255, 214, 64)
ROSE = (255, 150, 170)

L, H, IPS = 1080, 1920, 30
G, D = 80, 940                        # bords gauche / droit (boutons Instagram à droite)
ROUGE = (226, 52, 52)
VERT = (30, 170, 95)
RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- la scène, en secondes -------------------------------------------------
QUESTION = "Le kit coûte combien ?"
FAUSSE = "À partir de 79 €, livraison offerte !"
VRAIE = "Il est gratuit : 6 pages, 12 prompts, sans inscription."
CORRECTIFS = ["1. Voici les faits : […]",
              "2. N'invente aucun prix ni lien.",
              "3. Si tu ne sais pas, dis-le."]
SCENE = 17.0                     # la conversation
OUVERTURE = 1.8                  # la photo du sujet, comme la couverture des carrousels
DUREE = OUVERTURE + SCENE
PHOTO = "24-ia-qui-invente"       # alluxe_ia/fonds/<id>.jpg


def _lisse(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def _rebond(x: float) -> float:
    """0 -> 1 avec un léger dépassement (effet « pop »)."""
    x = max(0.0, min(1.0, x))
    return 1 + 2.2 * (x - 1) ** 3 + 1.2 * (x - 1) ** 2 if x < 1 else 1.0


def _halo(rayon: int, couleur: tuple) -> Image.Image:
    img = Image.new("RGBA", (rayon * 2, rayon * 2), (0, 0, 0, 0))
    ImageDraw.Draw(img).ellipse((rayon // 2, rayon // 2, rayon * 3 // 2, rayon * 3 // 2),
                                fill=couleur + (95,))
    return img.filter(ImageFilter.GaussianBlur(rayon // 4))


HALO_MENTHE = _halo(520, MENTHE)
HALO_AMBRE = _halo(460, AMBRE)
HALO_ROUGE = _halo(600, ROUGE)
HALO_ROSE = _halo(420, ROSE)


def _fond(t: float, alerte: float) -> Image.Image:
    img = Image.new("RGB", (L, H), FOND)
    # Deux halos de couleur qui dérivent lentement : le fond n'est jamais immobile.
    x1 = int(-200 + 260 * math.sin(t * 0.55)); y1 = int(300 + 220 * math.cos(t * 0.4))
    x2 = int(520 + 240 * math.cos(t * 0.5)); y2 = int(1050 + 260 * math.sin(t * 0.45))
    img.paste(HALO_MENTHE, (x1, y1), HALO_MENTHE)
    img.paste(HALO_AMBRE, (x2, y2), HALO_AMBRE)
    x3 = int(600 + 200 * math.sin(t * 0.7 + 1)); y3 = int(-150 + 160 * math.cos(t * 0.6))
    img.paste(HALO_ROSE, (x3, y3), HALO_ROSE)
    if alerte > 0:
        h = HALO_ROUGE.copy()
        h.putalpha(h.getchannel("A").point(lambda a: int(a * alerte)))
        img.paste(h, (L // 2 - 600, 650), h)
    return img


def _bulle(d: ImageDraw.ImageDraw, texte: str, y: int, de_moi: bool, police, echelle: float = 1.0,
           barre: bool = False) -> int:
    larg_max = 620
    lignes = couper(texte, police, larg_max) if texte else [""]
    w = max(d.textlength(li, font=police) for li in lignes) + 56
    w = max(w, 120)
    h = int(len(lignes) * police.size * 1.25) + 40
    x0 = D - 60 - w if de_moi else G + 60
    cx, cy = x0 + w / 2, y + h / 2
    if echelle < 0.05:                # la bulle n'est pas encore apparue
        return y + h
    w2, h2 = w * echelle, h * echelle
    box = (cx - w2 / 2, cy - h2 / 2, cx + w2 / 2, cy + h2 / 2)
    d.rounded_rectangle(box, radius=int(30 * echelle),
                        fill=BULLE_MOI if de_moi else BULLE_IA)
    if echelle > 0.85:
        yy = y + 20
        for li in lignes:
            d.text((x0 + 28, yy), li, font=police, fill=(255, 255, 255) if de_moi else ENCRE)
            if barre:
                lw = d.textlength(li, font=police)
                d.line((x0 + 24, yy + police.size * 0.6, x0 + 32 + lw, yy + police.size * 0.6),
                       fill=ROUGE, width=7)
            yy += int(police.size * 1.25)
    return y + h


def _points(d: ImageDraw.ImageDraw, y: int, t: float) -> int:
    d.rounded_rectangle((G + 60, y, G + 60 + 150, y + 80), radius=30, fill=BULLE_IA)
    for i in range(3):
        a = 0.5 + 0.5 * math.sin(t * 9 - i * 0.9)
        c = tuple(int(DOUX[k] * (0.5 + 0.5 * a)) for k in range(3))
        d.ellipse((G + 90 + i * 38, y + 30 - 6 * a, G + 112 + i * 38, y + 52 - 6 * a), fill=c)
    return y + 80


def _tape(texte: str, t: float, debut: float, vitesse: float = 26.0) -> str:
    n = int(max(0.0, t - debut) * vitesse)
    return texte[:n]


def _accroche(d: ImageDraw.ImageDraw, texte: str, t_local: float, couleur: tuple,
              surligne: str = "") -> None:
    """Accroche en gros, avec un coup de surligneur jaune sur les mots clés."""
    p = titre_police(int(100 * (0.7 + 0.3 * _rebond(t_local / 0.35))))
    lignes = couper(texte, p, D - G)
    y = 290
    trace = _lisse((t_local - 0.3) / 0.35)          # le surligneur se pose après le texte
    for li in lignes:
        if surligne and surligne in li and trace > 0:
            x0 = G + d.textlength(li[: li.index(surligne)], font=p)
            w = d.textlength(surligne, font=p)
            d.rounded_rectangle((x0 - 10, y + p.size * 0.18, x0 - 10 + (w + 20) * trace,
                                 y + p.size * 1.08), radius=10, fill=SURLIGNEUR)
        d.text((G, y), li, font=p, fill=couleur)
        y += int(p.size * 1.1)


def image(t: float) -> Image.Image:
    if t < OUVERTURE:
        return _ouverture(t)
    return _scene(t - OUVERTURE)


_PHOTO_CACHE: dict = {}


def _ouverture(t: float) -> Image.Image:
    """La photo du sujet en plein écran, qui zoome doucement, avec le titre
    surligné : la même signature que la couverture des carrousels."""
    from alluxe_ia import slides as base
    if "src" not in _PHOTO_CACHE:
        src = Image.open(base._fond_photo(PHOTO)).convert("RGB")
        k = max(L * 1.15 / src.width, H * 1.15 / src.height)
        _PHOTO_CACHE["src"] = src.resize((int(src.width * k) + 1, int(src.height * k) + 1), Image.LANCZOS)
        _PHOTO_CACHE["accent"] = base.couleur_du_post(PHOTO)
    src = _PHOTO_CACHE["src"]
    accent, encre_accent = _PHOTO_CACHE["accent"]
    z = 1.15 - 0.15 * (t / OUVERTURE)              # zoom arrière lent
    w, h = int(L * z), int(H * z)
    x0, y0 = (src.width - w) // 2, (src.height - h) // 2
    img = src.crop((x0, y0, x0 + w, y0 + h)).resize((L, H), Image.BILINEAR)
    voile = Image.new("L", (L, H))
    dv = ImageDraw.Draw(voile)
    for y in range(0, H, 4):
        a = int(min(225, 250 * max(0.0, (y / H - 0.3) / 0.6)))
        dv.rectangle((0, y, L, y + 4), fill=a)
    img = Image.composite(Image.new("RGB", (L, H), (8, 10, 10)), img, voile)
    d = ImageDraw.Draw(img)
    p = titre_police(int(118 * (0.75 + 0.25 * _rebond(t / 0.4))))
    lignes = couper("Mon IA a inventé un prix.", p, D - G)
    y = 1000
    for i, li in enumerate(lignes):
        if i == len(lignes) - 1:
            w2 = d.textlength(li, font=p) * _lisse((t - 0.4) / 0.4)
            d.rounded_rectangle((G - 12, y + p.size * 0.12, G + w2 + 14, y + p.size * 1.06),
                                radius=14, fill=accent)
            d.text((G, y), li, font=p, fill=encre_accent if w2 > 10 else (255, 255, 255))
        else:
            d.text((G, y), li, font=p, fill=(255, 255, 255))
        y += int(p.size * 1.04)
    return img


def _scene(t: float) -> Image.Image:
    tampon = _lisse((t - 3.9) / 0.25)
    alerte = max(0.0, 1 - abs(t - 4.2) / 0.9) if 3.9 <= t <= 5.1 else 0.0
    img = _fond(t, alerte)
    d = ImageDraw.Draw(img)

    # Pas d'en-tête : les 220 px du haut sont couverts par les onglets d'Instagram.

    # Accroche : 6 à 8 mots, elle change au moment du tampon puis pour la chute.
    if t < 4.3:
        _accroche(d, "Mon IA a inventé un prix.", t, ENCRE, "un prix.")
    elif t < 13.6:
        _accroche(d, "Le kit est GRATUIT.", t - 4.3, ENCRE, "GRATUIT.")
    else:
        _accroche(d, "Elle n'invente plus.", t - 13.6, ENCRE, "plus.")

    # La fenêtre de discussion, qui monte au début.
    monte = _lisse(t / 0.5)
    haut = int(560 + (1 - monte) * 300)
    d.rounded_rectangle((G + 8, haut + 14, D + 8, 1434), radius=44, fill=(232, 227, 216))
    d.rounded_rectangle((G, haut, D, 1420), radius=44, fill=FENETRE, outline=BORD, width=3)
    d.text((G + 40, haut + 30), "Assistant alluxe.fr", font=texte_police(32, gras=True), fill=DOUX)
    d.ellipse((D - 70, haut + 38, D - 46, haut + 62), fill=VERT)
    y = haut + 110
    pb = texte_police(50)

    if t < 9.6:
        # Acte 1 : la question, l'invention, le tampon.
        if t > 0.6:
            y = _bulle(d, QUESTION, y, True, pb, _rebond((t - 0.6) / 0.3)) + 30
        if 1.3 < t < 2.0:
            _points(d, y, t)
        elif t >= 2.0:
            yb = y
            y = _bulle(d, _tape(FAUSSE, t, 2.0) or " ", y, False, pb, barre=t > 4.0) + 30
            if tampon > 0:
                s = 1.8 - 0.8 * _rebond((t - 3.9) / 0.3)
                pt = titre_police(int(120 * s))
                tw = d.textlength("FAUX", font=pt)
                calque = Image.new("RGBA", (int(tw) + 60, int(pt.size * 1.4)), (0, 0, 0, 0))
                dc = ImageDraw.Draw(calque)
                dc.rounded_rectangle((4, 4, calque.width - 4, calque.height - 4), radius=18,
                                     outline=ROUGE + (255,), width=10)
                dc.text((30, pt.size * 0.12), "FAUX", font=pt, fill=ROUGE + (255,))
                calque = calque.rotate(-12, expand=True, resample=Image.BICUBIC)
                calque.putalpha(calque.getchannel("A").point(lambda a: int(a * tampon)))
                img.paste(calque, (int(L / 2 - calque.width / 2 - 40), int(yb - 40)), calque)
        # Le correctif, ligne par ligne, dans une fenêtre de prompt.
        if t > 5.0:
            yc = max(y + 20, 1000)
            d.rounded_rectangle((G + 40, yc, D - 40, yc + 330), radius=24, fill=(255, 250, 235),
                                outline=AMBRE, width=3)
            d.text((G + 70, yc + 24), "Ajouté à sa consigne :", font=texte_police(32, gras=True),
                   fill=AMBRE)
            for i, ligne in enumerate(CORRECTIFS):
                debut = 5.4 + 1.2 * i
                if t > debut:
                    d.text((G + 70, yc + 90 + i * 74), _tape(ligne, t, debut, 34),
                           font=mono_police(34), fill=ENCRE)
    else:
        # Acte 2 : la même question, la bonne réponse.
        y = _bulle(d, QUESTION, y, True, pb, _rebond((t - 9.7) / 0.3)) + 30
        if 10.3 < t < 11.0:
            _points(d, y, t)
        elif t >= 11.0:
            y = _bulle(d, _tape(VRAIE, t, 11.0, 30) or " ", y, False, pb) + 30
            if t > 13.1:
                r = int(46 * _rebond((t - 13.1) / 0.3))
                cx, cy = G + 100, y + 50
                d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=VERT)
                if r > 30:
                    d.line((cx - 20, cy, cx - 5, cy + 16, cx + 22, cy - 16), fill=(255, 255, 255), width=9)
        # La chute : l'appel, qui pulse.
        if t > 14.0:
            p = _rebond((t - 14.0) / 0.35) * (1 + 0.03 * math.sin(t * 6))
            pc = mono_police(int(60 * p))
            texte = "Lien en bio"
            tw = d.textlength(texte, font=pc)
            yc = 1240
            d.text((G + 60, yc - 60), "Les 12 prompts du kit :", font=texte_police(36, gras=True),
                   fill=ENCRE)
            d.rounded_rectangle((G + 50, yc, G + 90 + tw, yc + pc.size + 34), radius=16, fill=AMBRE)
            d.text((G + 70, yc + 14), texte, font=pc, fill=ENCRE)

    # Barre de progression fine sous la fenêtre.
    d.rectangle((G, 1450, D, 1456), fill=BORD)
    d.rectangle((G, 1450, G + int((D - G) * t / SCENE), 1456), fill=MENTHE)
    return img


def rendre(reel_id: str = "02-ia-invente-un-prix", sortie: str | None = None) -> str:
    sortie = sortie or os.path.join(RACINE, "data", "alluxe_ia", "reels", f"{reel_id}.mp4")
    os.makedirs(os.path.dirname(sortie), exist_ok=True)
    piste = ecrire_wav(sortie + ".musique.wav", DUREE, graine=reel_id)
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{L}x{H}", "-r", str(IPS), "-i", "-",
           "-i", piste, "-t", f"{DUREE:.2f}",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-profile:v", "high", "-preset", "medium",
           "-crf", "20", "-movflags", "+faststart", "-c:a", "aac", "-b:a", "128k", "-shortest", sortie]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(int(DUREE * IPS)):
        p.stdin.write(image(i / IPS).tobytes())
    p.stdin.close()
    code = p.wait()
    os.remove(piste)
    if code != 0:
        raise RuntimeError("ffmpeg a échoué")
    return sortie


if __name__ == "__main__":
    print(rendre())
