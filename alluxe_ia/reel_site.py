"""Reel 06 « J'ai construit CE site en 1 journée, sans savoir coder » (8 oct. 2026).

    python3 -m alluxe_ia.reel_site   ->  data/alluxe_ia/reels/06-site-en-1-journee.mp4

Format choisi pour faire s'ABONNER (recherche du 8 oct.) : accroche dans la 1re
seconde sur une image qui bouge déjà, avant/après, une valeur à ENREGISTRER (le
prompt exact), et une MINI-SÉRIE (« Partie 1 ») qui donne une raison de suivre.

Tout est vrai : alluxe.fr construit le 4 oct. (1re page 0 h 54, site multi-pages
20 h 30, git log) ; captures réelles du site public (data/alluxe_ia/captures/site) ;
prompt = le n° 1 du kit (alluxe_ia/posts.json, post 04) ; le code est écrit par
Claude (capture term/claude_*.png, reconstitution avec le vrai code).
"""
from __future__ import annotations

import glob
import math
import os

from PIL import Image, ImageDraw

from alluxe_ia.reel_captures_montage import (
    CREME, ENCRE, F, H, HT, JAUNE, NOIR, RACINE, W, decor, ease, ecran, legende, logo, mettre_logo, produire, texte)

PAGES = {n: Image.open(H + f"site/{n}.png").convert("RGB") for n in ("accueil", "offres", "kits", "commander")}
CLAUDE = [Image.open(f).convert("RGB") for f in sorted(glob.glob(H + "term/claude_*.png"))]
PROMPT = ["Je veux construire [ton idée,", "même floue]. Je ne suis pas", "développeur.", "",
          "Pose-moi 10 questions, une à", "la fois, pour comprendre ce", "que je veux vraiment.", "",
          "N'écris aucun code."]
COUPES = [("accueil", 0.0, [("6 pages.", JAUNE)]), ("offres", 0.05, [("Les prix,", None), ("affichés.", JAUNE)]),
          ("kits", 0.03, [("16 kits", None), ("gratuits.", JAUNE)]), ("commander", 0.0, [("Et un vrai", None), ("bon de commande.", JAUNE)])]


def carte_prompt(n_lignes: int, curseur: bool) -> Image.Image:
    """Une bulle de discussion : le vrai prompt n° 1 du kit, tapé ligne à ligne."""
    larg, haut = 900, 860
    img = Image.new("RGB", (larg, haut), (255, 255, 255)); d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, larg - 1, haut - 1), 40, outline=ENCRE, width=6)
    d.text((44, 36), "Ton message à l'IA", font=F(40), fill=(110, 118, 114))
    d.rounded_rectangle((36, 110, larg - 36, haut - 40), 34, fill=(253, 255, 208))
    y = 140
    for i, l in enumerate(PROMPT[:n_lignes]):
        d.text((70, y), l, font=F(50), fill=NOIR); y += 66
    if curseur and n_lignes:
        x = 70 + F(50).getlength(PROMPT[min(n_lignes, len(PROMPT)) - 1]) + 8
        d.rectangle((x, y - 62, x + 6, y - 10), fill=NOIR)
    return img


def image(t: float) -> Image.Image:
    img = Image.new("RGB", (W, HT), CREME)
    scene = sum(t >= s for s in (2.2, 5.4, 10.4, 12.8))
    if scene < 4: decor(img, t, scene + 3)
    d = ImageDraw.Draw(img)
    if t < 2.2:                                     # 1. accroche : le site défile déjà
        ecran(img, PAGES["accueil"], 820, 1100, decal=0.02 + t * 0.06)
        mettre_logo(img, 180)
        texte(d, 250, [("J'ai construit", None), ("CE site", JAUNE)], 130, t=t / 0.6)
        if t > 0.7: texte(d, 560, [("en 1 journée,", None), ("sans savoir coder.", None)], 84, t=(t - 0.7) / 0.6)
    elif t < 5.4:                                   # 2. le prompt exact, à enregistrer
        u = (t - 2.2) / 3.2
        n = min(len(PROMPT), int(u * 1.5 * len(PROMPT)) + 1)
        c = carte_prompt(n, int(t * 3) % 2 == 0)
        x = (W - c.width) // 2
        dd = ImageDraw.Draw(img)
        dd.rounded_rectangle((x + 12, 236, x + c.width + 16, 236 + c.height + 4), 44, fill=JAUNE)
        img.paste(c, (x, 220))
        legende(img, d, 1280, [("Le prompt exact.", None), ("Enregistre-le.", JAUNE)], 118, u, 1)
    elif t < 10.4:                                  # 3. le résultat : coupes rapides, vraies pages
        u = (t - 5.4) / 5.0
        k = min(3, int(u * 4)); v = u * 4 - k
        nom, depart, titre = COUPES[k]
        ecran(img, PAGES[nom], 140, 1720, decal=depart + v * 0.10, zoom=1.0 + 0.03 * v)
        legende(img, d, 1300, titre, 104, min(1, v * 2.5), 2)
    elif t < 12.8:                                  # 4. le code, écrit par l'IA
        u = (t - 10.4) / 2.4
        k = min(len(CLAUDE) - 1, int(u * 1.4 * (len(CLAUDE) - 1)))
        ecran(img, CLAUDE[k], 140, 1700, decal=1.0)
        legende(img, d, 1250, [("0 ligne de code", None), ("écrite par moi.", JAUNE)], 118, u, 3)
    else:                                           # 5. la série : une raison de s'abonner
        u = (t - 12.8) / 2.7
        img.paste(Image.new("RGB", (W, HT), JAUNE)); d = ImageDraw.Draw(img)
        l = logo.resize((240, 240)); img.paste(l, ((W - 240) // 2, 260), l)
        d.rounded_rectangle((330, 560, 750, 660), 50, fill=NOIR)
        f = F(64); s = "PARTIE 1"; d.text(((W - f.getlength(s)) / 2, 574), s, font=f, fill=JAUNE)
        f = F(78)
        for i, s in enumerate(["Je construis un", "business avec l'IA,", "sans coder."]):
            d.text(((W - f.getlength(s)) / 2, 730 + i * 96), s, font=f, fill=NOIR)
        pulse = 1 + 0.04 * math.sin(t * 9)
        f2 = F(int(62 * pulse)); s = "Abonne-toi pour la partie 2"
        d.rounded_rectangle(((W - f2.getlength(s)) / 2 - 34, 1100, (W + f2.getlength(s)) / 2 + 34, 1210), 55, fill=NOIR)
        d.text(((W - f2.getlength(s)) / 2, 1118), s, font=f2, fill=JAUNE)
        f3 = F(50); s = "et enregistre le prompt."
        d.text(((W - f3.getlength(s)) / 2, 1250), s, font=f3, fill=NOIR)
    return img


LEGENDE = (
    "J'ai construit ce site en 1 journée. Je ne sais pas coder 👇\n\n"
    "Le prompt de départ (copie-le) :\n"
    "« Je veux construire [ton idée, même floue]. Je ne suis pas développeur. "
    "Pose-moi 10 questions, une à la fois, pour comprendre ce que je veux vraiment. "
    "N'écris aucun code. »\n\n"
    "Pourquoi ça marche : l'IA arrête de deviner, et tu découvres ce que tu veux vraiment "
    "avant d'écrire la moindre ligne.\n\n"
    "Partie 1 sur 5 : je construis un business avec l'IA, sans coder.\n"
    "👉 Abonne-toi pour la partie 2 (le cahier des charges).\n"
    "💾 Enregistre ce Reel pour retrouver le prompt.\n"
    "📎 Les 12 prompts du kit, gratuits : lien dans ma bio\n\n"
    "#ia #intelligenceartificielle #chatgpt #claude #nocode #creerunsite #entrepreneur"
)
REELS = {"06-site-en-1-journee": {"legende": LEGENDE}}


def rendre(reel_id: str = "06-site-en-1-journee") -> None:
    produire(image, 15.5, os.path.join(RACINE, "data", "alluxe_ia", "reels", f"{reel_id}.mp4"), graine="site")


if __name__ == "__main__":
    rendre()
