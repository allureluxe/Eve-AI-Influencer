"""Visuels promo de Noël pour les livres de la famille (13 oct. 2026).

    .venv/bin/python alluxe_ia/promo_livres.py

Post Instagram 1080×1350 et story 1080×1920, dans data/alluxe_ia/promo-livres/.
Couvertures : docs/kit/livres/ (téléchargées depuis Amazon). Rien n'est publié ici.
"""
from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

RACINE = Path(__file__).resolve().parent.parent
LIVRES = RACINE / "docs/kit/livres"
SORTIE = RACINE / "data/alluxe_ia/promo-livres"
POLICE = RACINE / "alluxe_ia/polices/BricolageGrotesque.ttf"
TEXTE = RACINE / "alluxe_ia/polices/AtkinsonHyperlegible-Bold.ttf"
ROUGE, NUIT, OR, BLANC = (179, 22, 29), (110, 15, 18), (233, 185, 73), (255, 255, 255)


def police(chemin: Path, taille: int, graisse: int | None = None) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(str(chemin), taille)
    if graisse:
        try:
            f.set_variation_by_axes([96, graisse])          # opsz, wght (police variable)
        except Exception:                                    # noqa: BLE001
            pass
    return f


def fond(l: int, h: int) -> Image.Image:
    """Dégradé rouge profond + neige légère."""
    im = Image.new("RGB", (l, h))
    d = ImageDraw.Draw(im)
    for y in range(h):
        k = y / h
        d.line([(0, y), (l, y)], fill=tuple(int(ROUGE[i] * (1 - k) + NUIT[i] * k) for i in range(3)))
    rnd = random.Random(13)
    neige = Image.new("RGBA", (l, h), (0, 0, 0, 0))
    dn = ImageDraw.Draw(neige)
    for _ in range(140):
        x, y, r = rnd.randint(0, l), rnd.randint(0, h), rnd.choice([2, 3, 3, 4, 6])
        dn.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, rnd.randint(60, 170)))
    return Image.alpha_composite(im.convert("RGBA"), neige)


def couverture(nom: str, largeur: int, angle: float) -> Image.Image:
    c = Image.open(LIVRES / nom).convert("RGBA")
    c = c.resize((largeur, int(c.height * largeur / c.width)), Image.LANCZOS)
    # ombre portée
    pad = 40
    o = Image.new("RGBA", (c.width + 2 * pad, c.height + 2 * pad), (0, 0, 0, 0))
    ImageDraw.Draw(o).rounded_rectangle([pad + 14, pad + 20, pad + c.width + 14, pad + c.height + 20], 12, fill=(0, 0, 0, 150))
    o = o.filter(ImageFilter.GaussianBlur(16))
    o.alpha_composite(c, (pad, pad))
    return o.rotate(angle, resample=Image.BICUBIC, expand=True)


def centre(d: ImageDraw.ImageDraw, l: int, y: int, texte: str, f, couleur, interligne: int = 8) -> int:
    for ligne in texte.split("\n"):
        b = d.textbbox((0, 0), ligne, font=f)
        d.text(((l - (b[2] - b[0])) // 2, y), ligne, font=f, fill=couleur)
        y += b[3] - b[1] + interligne
    return y


def visuel(l: int, h: int, nom: str) -> Path:
    im = fond(l, h)
    d = ImageDraw.Draw(im)
    story = h >= 1500
    haut = 50 if not story else 230
    gap = 0 if not story else 60
    # bandeau or
    pf = police(TEXTE, 34)
    etiquette = "IDÉE CADEAU DE NOËL"
    b = d.textbbox((0, 0), etiquette, font=pf)
    w = b[2] - b[0] + 60
    d.rounded_rectangle([(l - w) // 2, haut, (l + w) // 2, haut + 64], 32, fill=OR)
    d.text(((l - (b[2] - b[0])) // 2, haut + 12), etiquette, font=pf, fill=NUIT)
    y = centre(d, l, haut + 100, "Le cadeau qui fait\nrire les enfants", police(POLICE, 92, 800), BLANC, 4)
    # couvertures en éventail
    yc = y + 20 + gap
    tailles = [("dm02.jpg", 9), ("dm11.jpg", -9), ("dm05.jpg", 0)]
    larg = 290 if not story else 300
    positions = {"dm02.jpg": l // 2 - 265, "dm11.jpg": l // 2 + 265, "dm05.jpg": l // 2}
    hauteur_pile = 0
    for f, a in tailles:
        c = couverture(f, larg if f != "dm05.jpg" else larg + 40, a)
        x = positions[f] - c.width // 2
        dy = 50 if f != "dm05.jpg" else 0
        im.alpha_composite(c, (x, yc + dy))
        hauteur_pile = max(hauteur_pile, dy + c.height)
    d = ImageDraw.Draw(im)
    y = yc + hauteur_pile - 10 + gap
    y = centre(d, l, y, "Les détectives maladroits", police(POLICE, 64, 800), OR, 6)
    y = centre(d, l, y + 6, "19 enquêtes loufoques de Lucie et Bastien", police(TEXTE, 38), BLANC, 6)
    # pastille prix
    pf = police(POLICE, 54, 800)
    txt = "dès 8,43 € le tome"
    b = d.textbbox((0, 0), txt, font=pf)
    w, hh = b[2] - b[0] + 80, 96
    y += 30 + gap // 2
    d.rounded_rectangle([(l - w) // 2, y, (l + w) // 2, y + hh], 48, fill=BLANC)
    d.text(((l - (b[2] - b[0])) // 2, y + 14), txt, font=pf, fill=ROUGE)
    y += hh + 30 + gap // 2
    centre(d, l, y, "Sur Amazon · lien sur alluxe.fr/livres", police(TEXTE, 34), (253, 232, 230), 6)
    sortie = SORTIE / nom
    im.convert("RGB").save(sortie, quality=92)
    return sortie


if __name__ == "__main__":
    SORTIE.mkdir(parents=True, exist_ok=True)
    print(visuel(1080, 1350, "post-1080x1350.jpg"))
    print(visuel(1080, 1920, "story-1080x1920.jpg"))
