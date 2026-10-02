"""Gabarit des slides de carrousel alluxe.ia (1080 x 1350, format 4:5).

UN SEUL GABARIT, ET C'EST VOULU. Le post qui a servi de modele
(@_mind__vision_) se reconnait avant d'etre lu : meme fond, meme en-tete,
meme place pour chaque element sur toutes les slides. C'est ce qui fait
qu'un abonne s'arrete sur le post suivant sans avoir lu le nom du compte.
Changer de couleurs ou de polices d'un post a l'autre detruirait ca.

Quatre types de slides, et un post n'en utilise pas d'autres :

    couverture  la promesse chiffree qui arrete le pouce
    texte       un titre et un paragraphe court
    prompt      un titre-benefice en gros + le prompt dans une fenetre
    appel       le mot-cle a commenter

Les polices sont livrees dans alluxe_ia/polices (licence OFL) : le rendu
ne depend pas de ce qui est installe sur le serveur.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from PIL import Image, ImageDraw, ImageFont

LARGEUR, HAUTEUR = 1080, 1350
MARGE = 84
ICI = os.path.dirname(os.path.abspath(__file__))
POLICES = os.path.join(ICI, "polices")

# Palette : encre vert profond, menthe pour la marque, ambre pour ce qui
# doit etre fait (le mot-cle). Deliberement PAS le noir et or du modele.
FOND = (14, 21, 19)
FOND_HAUT = (21, 34, 30)
ENCRE = (234, 241, 237)
DOUX = (150, 168, 160)
MENTHE = (92, 195, 180)
AMBRE = (227, 162, 74)
FENETRE = (24, 35, 32)
BORD = (48, 66, 60)

PSEUDO = "@alluxe.ia"
NOM = "alluxe.ia"


def _police(nom: str, taille: int, graisse: str | None = None) -> ImageFont.FreeTypeFont:
    f = ImageFont.truetype(os.path.join(POLICES, nom), taille)
    if graisse:
        try:
            f.set_variation_by_name(graisse)
        except (OSError, ValueError):
            pass
    return f


def titre_police(taille: int) -> ImageFont.FreeTypeFont:
    return _police("BricolageGrotesque.ttf", taille, "Bold")


def texte_police(taille: int, gras: bool = False) -> ImageFont.FreeTypeFont:
    return _police("AtkinsonHyperlegible-Bold.ttf" if gras
                   else "AtkinsonHyperlegible-Regular.ttf", taille)


def mono_police(taille: int) -> ImageFont.FreeTypeFont:
    return _police("JetBrainsMono.ttf", taille, "Regular")


@dataclass
class Slide:
    type: str                      # couverture | texte | prompt | appel
    titre: str = ""
    texte: str = ""
    prompt: str = ""
    mot_cle: str = ""


@dataclass
class Post:
    id: str
    legende: str
    slides: list[Slide] = field(default_factory=list)

    @classmethod
    def depuis(cls, d: dict) -> "Post":
        return cls(id=d["id"], legende=d["legende"],
                   slides=[Slide(**s) for s in d["slides"]])


# ---------------------------------------------------------------- texte

def couper(texte: str, police: ImageFont.FreeTypeFont, largeur: int) -> list[str]:
    """Coupe en lignes qui tiennent dans `largeur` pixels.

    Les retours a la ligne voulus (\\n) sont respectes : un prompt garde
    sa mise en page, un titre peut forcer sa coupure.
    """
    lignes: list[str] = []
    for paragraphe in texte.split("\n"):
        mots = _insecables(paragraphe.split(" "))
        courante = ""
        for mot in mots:
            essai = f"{courante} {mot}".strip()
            if police.getlength(essai) <= largeur or not courante:
                courante = essai
            else:
                lignes.append(courante)
                courante = mot
        lignes.append(courante)
    return lignes


# Typographie francaise : « : », « ? », « ! », « ; » et « » » ne commencent
# jamais une ligne, « « » n'en termine jamais une. On soude ces signes a
# leur voisin avant de couper.
_COLLES_AVANT = {":", ";", "?", "!", "»", "—"}


def _insecables(mots: list[str]) -> list[str]:
    sortie: list[str] = []
    for mot in mots:
        if sortie and mot in _COLLES_AVANT:
            sortie[-1] = f"{sortie[-1]} {mot}"
        elif sortie and sortie[-1].endswith("«"):
            sortie[-1] = f"{sortie[-1]} {mot}"
        else:
            sortie.append(mot)
    return sortie


def _hauteur(texte: str, police: ImageFont.FreeTypeFont, largeur: int,
             interligne: float) -> int:
    return int(len(couper(texte, police, largeur)) * police.size * interligne)


def _centre(hauteur: int) -> int:
    """Haut d'un bloc centre entre l'en-tete et le pied de slide."""
    haut, bas = 250, HAUTEUR - 150
    return max(haut, haut + (bas - haut - hauteur) // 2)


def _bloc(d: ImageDraw.ImageDraw, x: int, y: int, texte: str,
          police: ImageFont.FreeTypeFont, couleur, largeur: int,
          interligne: float = 1.18) -> int:
    """Ecrit un bloc et rend le y sous la derniere ligne."""
    hauteur = int(police.size * interligne)
    for ligne in couper(texte, police, largeur):
        d.text((x, y), ligne, font=police, fill=couleur)
        y += hauteur
    return y


def _ajuster(texte: str, fabrique, depart: int, minimum: int,
             largeur: int, hauteur_max: int, interligne: float = 1.18):
    """La plus grande taille ou le texte tient dans la boite."""
    taille = depart
    while taille > minimum:
        p = fabrique(taille)
        if len(couper(texte, p, largeur)) * p.size * interligne <= hauteur_max:
            return p
        taille -= 4
    return fabrique(minimum)


# ---------------------------------------------------------------- slides

def _fond_et_entete(numero: int, total: int) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (LARGEUR, HAUTEUR), FOND)
    d = ImageDraw.Draw(img)
    # Degrade vertical discret : le haut un peu plus clair, sans motif.
    for y in range(HAUTEUR // 2):
        t = 1 - y / (HAUTEUR / 2)
        c = tuple(int(FOND[i] + (FOND_HAUT[i] - FOND[i]) * t) for i in range(3))
        d.line([(0, y), (LARGEUR, y)], fill=c)

    # En-tete : pastille + nom + pseudo, identique sur chaque slide.
    cx, cy, r = MARGE + 44, MARGE + 44, 44
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=MENTHE)
    d.text((cx, cy + 2), "a.", font=titre_police(46), fill=FOND, anchor="mm")
    d.text((cx + r + 24, cy - 6), NOM, font=titre_police(38), fill=ENCRE, anchor="ls")
    d.text((cx + r + 24, cy + 34), PSEUDO, font=texte_police(28), fill=DOUX, anchor="ls")
    if total > 1:
        d.text((LARGEUR - MARGE, cy), f"{numero}/{total}",
               font=mono_police(28), fill=DOUX, anchor="rm")
    return img, d


def _couverture(d, s: Slide, total: int) -> None:
    largeur = LARGEUR - 2 * MARGE
    p = _ajuster(s.titre, titre_police, 108, 64, largeur, 620, 1.08)
    pt = texte_police(40)
    h = _hauteur(s.titre, p, largeur, 1.08)
    if s.texte:
        h += 40 + _hauteur(s.texte, pt, largeur, 1.3)
    y = _bloc(d, MARGE, _centre(h), s.titre, p, ENCRE, largeur, 1.08)
    if s.texte:
        _bloc(d, MARGE, y + 40, s.texte, pt, DOUX, largeur, 1.3)
    if total > 1:
        # La fleche vient de la police mono : Atkinson n'a pas ce glyphe.
        d.text((LARGEUR - MARGE, HAUTEUR - MARGE), "→",
               font=mono_police(40), fill=MENTHE, anchor="rs")
        d.text((LARGEUR - MARGE - 56, HAUTEUR - MARGE), "Glisse",
               font=texte_police(34, gras=True), fill=MENTHE, anchor="rs")


def _texte(d, s: Slide) -> None:
    largeur = LARGEUR - 2 * MARGE
    p = _ajuster(s.titre, titre_police, 76, 48, largeur, 330, 1.1)
    hp = _hauteur(s.titre, p, largeur, 1.1)
    pt = _ajuster(s.texte, texte_police, 46, 30, largeur, 800 - hp, 1.38)
    h = hp + 44 + _hauteur(s.texte, pt, largeur, 1.38)
    y = _bloc(d, MARGE, _centre(h), s.titre, p, ENCRE, largeur, 1.1)
    _bloc(d, MARGE, y + 44, s.texte, pt, DOUX, largeur, 1.38)


def _prompt(d, s: Slide) -> None:
    largeur = LARGEUR - 2 * MARGE
    p = _ajuster(s.titre, titre_police, 70, 46, largeur, 300, 1.1)
    hp = _hauteur(s.titre, p, largeur, 1.1)
    # La fenetre de chat : le prompt est lu en zoomant, donc il est petit
    # mais net. C'est cette fenetre qui fait sauvegarder le post.
    interieur = largeur - 2 * 36
    pm = _ajuster(s.prompt, mono_police, 32, 21, interieur, 860 - hp, 1.42)
    nb = len(couper(s.prompt, pm, interieur))
    h = int(nb * pm.size * 1.42) + 2 * 34 + 44
    y = _bloc(d, MARGE, _centre(hp + 46 + h), s.titre, p, ENCRE, largeur, 1.1) + 46
    d.rounded_rectangle([MARGE, y, LARGEUR - MARGE, y + h], radius=26,
                        fill=FENETRE, outline=BORD, width=2)
    d.text((MARGE + 36, y + 30), "PROMPT", font=mono_police(22), fill=MENTHE)
    _bloc(d, MARGE + 36, y + 30 + 44, s.prompt, pm, ENCRE, interieur, 1.42)
    d.text((LARGEUR - MARGE, HAUTEUR - MARGE), "Sauvegarde ce post",
           font=texte_police(30), fill=DOUX, anchor="rs")


def _appel(d, s: Slide) -> None:
    largeur = LARGEUR - 2 * MARGE
    h = 92 + 180 + (_hauteur(s.texte, texte_police(42), largeur, 1.35) if s.texte else 0)
    if s.titre:
        h += _hauteur(s.titre, titre_police(64), largeur, 1.1) + 40
    y = _centre(h)
    if s.titre:
        y = _bloc(d, MARGE, y, s.titre, titre_police(64), ENCRE, largeur, 1.1) + 40
    d.text((MARGE, y), "Commente", font=titre_police(64), fill=ENCRE)
    y += 92
    # Le mot-cle dans un cartouche ambre : c'est la seule action demandee.
    pm = titre_police(110)
    w = int(pm.getlength(s.mot_cle))
    d.rounded_rectangle([MARGE - 8, y - 6, MARGE + w + 40, y + 132],
                        radius=22, fill=AMBRE)
    d.text((MARGE + 16, y + 8), s.mot_cle, font=pm, fill=FOND)
    y += 180
    if s.texte:
        _bloc(d, MARGE, y, s.texte, texte_police(42), DOUX, largeur, 1.35)


def rendre(post: Post) -> list[Image.Image]:
    """Toutes les slides d'un post, dans l'ordre."""
    total = len(post.slides)
    images = []
    for i, s in enumerate(post.slides, start=1):
        img, d = _fond_et_entete(i, total)
        if s.type == "couverture":
            _couverture(d, s, total)
        elif s.type == "texte":
            _texte(d, s)
        elif s.type == "prompt":
            _prompt(d, s)
        elif s.type == "appel":
            _appel(d, s)
        else:
            raise ValueError(f"type de slide inconnu : {s.type!r}")
        images.append(img)
    return images


def photo_profil(taille: int = 1080) -> Image.Image:
    """La photo de profil : la pastille « a. » seule, lisible en 110 px.

    Instagram la recoupe en cercle : tout le dessin tient dans le disque
    central, rien d'important dans les coins.
    """
    img = Image.new("RGB", (taille, taille), FOND)
    d = ImageDraw.Draw(img)
    r = int(taille * 0.42)
    c = taille // 2
    d.ellipse([c - r, c - r, c + r, c + r], fill=MENTHE)
    d.text((c, c + int(taille * 0.02)), "a.", font=titre_police(int(taille * 0.46)),
           fill=FOND, anchor="mm")
    return img
