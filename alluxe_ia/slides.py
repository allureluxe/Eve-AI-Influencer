"""Gabarit des slides de carrousel alluxe.ia (1080 x 1350, format 4:5).

UN SEUL GABARIT, ET C'EST VOULU. Le post qui a servi de modele
(@_mind__vision_) se reconnait avant d'etre lu : meme fond, meme en-tete,
meme place pour chaque element sur toutes les slides. C'est ce qui fait
qu'un abonne s'arrete sur le post suivant sans avoir lu le nom du compte.
Depuis le 4 oct. (style « vif »), seule la COULEUR change d'un post a
l'autre, en rotation fixe : les places, les polices et l'en-tete restent.

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
import re
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

# Deux thèmes. « clair » (4 oct., demande opérateur après le Reel à 5 vues) :
# texte foncé sur crème, surligneur jaune sur la couverture. Les comptes IA
# qui marchent sont clairs et contrastés ; le sombre est encore assombri par
# la compression d'Instagram. `utiliser_theme("clair")` l'active.
THEME = "vif"
THEMES = {
    "sombre": dict(FOND=FOND, FOND_HAUT=FOND_HAUT, ENCRE=ENCRE, DOUX=DOUX, MENTHE=MENTHE,
                   FENETRE=FENETRE, BORD=BORD),
    "clair": dict(FOND=(250, 247, 240), FOND_HAUT=(255, 252, 246), ENCRE=(17, 20, 19),
                  DOUX=(80, 88, 84), MENTHE=(18, 150, 128), FENETRE=(255, 255, 255),
                  BORD=(226, 222, 212)),
}
THEMES["vif"] = dict(THEMES["clair"])
SURLIGNEUR = (255, 214, 64)


def utiliser_theme(nom: str) -> None:
    global THEME
    THEME = nom
    globals().update(THEMES[nom])


# Le compte utilise désormais le gabarit vif de Claude : couleurs pleines + cartes + fenêtres de conversation.
utiliser_theme("vif")

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
    etiquette: str = ""            # style pop : la pastille de la couverture


@dataclass
class Post:
    id: str
    legende: str
    slides: list[Slide] = field(default_factory=list)
    etiquette: str = ""            # « HISTOIRE VRAIE », « PROMPT À VOLER »…
    chiffre: str | None = None     # None : tiré du titre ; "" : aucun

    @classmethod
    def depuis(cls, d: dict) -> "Post":
        return cls(id=d["id"], legende=d["legende"],
                   slides=[Slide(**s) for s in d["slides"]],
                   etiquette=d.get("etiquette", ""), chiffre=d.get("chiffre"))


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
        # « ». » ou « », » : le guillemet suivi d'une ponctuation reste collé aussi.
        if sortie and (mot in _COLLES_AVANT or mot[:1] == "»"):
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
    haut, bas = 310, HAUTEUR - 150
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

LOGO = os.path.join(ICI, "logo-allure.png")


def medaillon(taille: int, contenu_taille: int | None = None) -> Image.Image:
    """Le logo complet ALLUXE dans un rond : UN seul anneau menthe, disque
    clair, l'illustration et « ALLUXE » dessous, dans l'ecriture serif du logo
    ALLURE d'origine (Nimbus Roman, jumelle de Times).

    4 oct. 2026, demande de l'operateur : un seul cercle menthe (il y en avait
    deux), le nom ALLUXE visible, le meme logo que le site alluxe.fr. Le nom
    occupe ~17 % du diametre pour rester lisible sur un telephone, ou une
    slide de 1080 px s'affiche environ trois fois plus petite.
    Dessine en 4x puis reduit, sinon le bord du cercle crenele en petit.
    """
    k = 4
    # Le cercle peut être plus grand que le bloc logo interne (utile pour le Reel).
    contenu = contenu_taille or taille
    t = taille * k
    tc = contenu * k
    img = Image.new("RGBA", (t, t), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([0, 0, t - 1, t - 1], fill=MENTHE)
    a = int(t * 0.045)
    d.ellipse([a, a, t - 1 - a, t - 1 - a], fill=(236, 241, 239))

    logo = Image.open(LOGO).convert("RGBA")
    w = int(tc * 0.68)
    h = int(logo.height * w / logo.width)
    logo = logo.resize((w, h), Image.LANCZOS)
    # Le plus grand corps qui tient dans 62 % du diametre : le nom est bas
    # dans le disque, la ou le cercle se resserre.
    corps = int(tc * 0.22)
    while True:
        nom = ImageFont.truetype(os.path.join(POLICES, "NimbusRoman-Regular.otf"), corps)
        bb = d.textbbox((0, 0), "ALLUXE", font=nom)
        if bb[2] - bb[0] <= tc * 0.62 or corps < tc * 0.05:
            break
        corps -= max(1, k)
    ecart = int(tc * 0.02)
    total = h + ecart + (bb[3] - bb[1])
    y0 = (t - total) // 2
    img.alpha_composite(logo, ((t - w) // 2, y0))
    d.text(((t - (bb[2] - bb[0])) // 2 - bb[0], y0 + h + ecart - bb[1]),
           "ALLUXE", font=nom, fill=(17, 17, 17))
    return img.resize((taille, taille), Image.LANCZOS)


def _fond_et_entete(numero: int, total: int) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (LARGEUR, HAUTEUR), FOND)
    d = ImageDraw.Draw(img)
    # Degrade vertical discret : le haut un peu plus clair, sans motif.
    for y in range(HAUTEUR // 2):
        t = 1 - y / (HAUTEUR / 2)
        c = tuple(int(FOND[i] + (FOND_HAUT[i] - FOND[i]) * t) for i in range(3))
        d.line([(0, y), (LARGEUR, y)], fill=c)

    # En-tete : medaillon + nom + pseudo, identique sur chaque slide.
    # Medaillon 260 px (200 avant le 4 oct.) : le nom ALLUXE doit se lire.
    cx, cy, r = MARGE + 130, MARGE + 130, 130
    m = medaillon(2 * r, contenu_taille=190)
    img.paste(m, (cx - r, cy - r), m)
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
    y0 = _centre(h)
    if THEME == "clair":
        # Surligneur sous la dernière ligne du titre : c'est la chute de l'accroche.
        lignes = couper(s.titre, p, largeur)
        yl = y0 + int(p.size * 1.08) * (len(lignes) - 1)
        w = d.textlength(lignes[-1], font=p)
        d.rounded_rectangle((MARGE - 12, yl + p.size * 0.16, MARGE + w + 14, yl + p.size * 1.06),
                            radius=12, fill=SURLIGNEUR)
    y = _bloc(d, MARGE, y0, s.titre, p, ENCRE, largeur, 1.08)
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
    # La phrase avant le cartouche : « Commente » (mot-cle a commenter), ou
    # le titre de la slide quand il est donne (« Le kit gratuit : », depuis
    # le 4 oct. : le kit est en lien dans la bio, plus en message prive).
    amorce = s.titre or "Commente"
    h = 92 + 180 + (_hauteur(s.texte, texte_police(42), largeur, 1.35) if s.texte else 0)
    y = _centre(h)
    d.text((MARGE, y), amorce, font=titre_police(64), fill=ENCRE)
    y += 92
    # Le mot-cle dans un cartouche ambre : c'est la seule action demandee.
    pm = titre_police(110)
    w = int(pm.getlength(s.mot_cle))
    d.rounded_rectangle([MARGE - 8, y - 6, MARGE + w + 40, y + 132],
                        radius=22, fill=AMBRE)
    d.text((MARGE + 16, y + 8), s.mot_cle, font=pm, fill=ENCRE if THEME == "clair" else FOND)
    y += 180
    if s.texte:
        _bloc(d, MARGE, y, s.texte, texte_police(42), DOUX, largeur, 1.35)


# ---------------------------------------------------------------- style « vif »
#
# 4 oct., demande de l'opérateur : « je veux que mon compte Instagram il
# claque, que dès que les gens tombent dessus ils soient pris ». Ce qui
# change par rapport au gabarit unique d'origine :
#   - la couverture et l'appel prennent une COULEUR VIVE pleine page, une
#     par post, en rotation : la grille du profil devient multicolore ;
#   - une étiquette qui intrigue (« HISTOIRE VRAIE », « PROMPT À VOLER ») ;
#   - le chiffre du titre (108, 656…) en géant, en filigrane derrière ;
#   - les prompts dans une vraie fenêtre de conversation.
# Ce qui ne change pas : l'en-tête, les polices, la place de chaque
# élément. On reconnaît toujours le compte avant de lire son nom.

# (fond, encre) : l'encre est choisie pour le contraste sur ce fond.
PALETTE_VIVE = [
    ((255, 214, 64), (17, 20, 19)),     # jaune
    ((47, 92, 255), (255, 255, 255)),   # bleu électrique
    ((255, 94, 77), (17, 20, 19)),      # corail
    ((17, 20, 19), (255, 255, 255)),    # noir (le surligneur jaune y ressort)
    ((0, 200, 150), (17, 20, 19)),      # menthe vive
    ((124, 77, 255), (255, 255, 255)),  # violet
    ((255, 122, 184), (17, 20, 19)),    # rose
]


def couleur_du_post(post_id: str) -> tuple[tuple, tuple]:
    """La couleur d'un post, fixée par son numéro : un post garde sa couleur
    à chaque rendu, et des posts voisins n'ont jamais la même."""
    try:
        n = int(post_id.split("-")[0]) - 1
    except ValueError:
        n = sum(map(ord, post_id))
    return PALETTE_VIVE[n % len(PALETTE_VIVE)]


def _chiffre(post: Post) -> str:
    """Le chiffre à mettre en géant : donné par le post, sinon le premier
    nombre du titre s'il arrive dans les quatre premiers mots."""
    if post.chiffre is not None:
        return post.chiffre
    titre = post.slides[0].titre if post.slides else ""
    for mot in titre.split()[:4]:
        m = re.match(r"^(\d[\d\s]*)", mot)
        if m:
            return m.group(1).strip()
    return ""


def _ombre(c: tuple, k: float = 0.86) -> tuple:
    """Un ton plus sombre de la même couleur (ou plus clair sur le noir)."""
    if sum(c) < 120:
        return tuple(min(255, v + 34) for v in c)
    return tuple(int(v * k) for v in c)


def _pastille(d, x: int, y: int, texte: str, fond, encre, taille: int = 30,
              droite: bool = False, fleche: bool = False) -> int:
    """Étiquette arrondie ; rend sa largeur. La flèche vient de la police
    mono : Atkinson n'a pas ce glyphe."""
    p = texte_police(taille, gras=True)
    pf = mono_police(taille)
    wf = int(pf.getlength(" →")) if fleche else 0
    w = int(p.getlength(texte)) + wf + 2 * 26
    h = int(taille * 1.9)
    x0 = x - w if droite else x
    d.rounded_rectangle((x0, y, x0 + w, y + h), radius=h // 2, fill=fond)
    d.text((x0 + 26, y + h // 2), texte, font=p, fill=encre, anchor="lm")
    if fleche:
        d.text((x0 + w - 26, y + h // 2), "→", font=pf, fill=encre, anchor="rm")
    return w


def _entete_vif(img, d, fond, encre, etiquette: str) -> None:
    cx, cy, r = MARGE + 80, MARGE + 80, 80
    m = medaillon(2 * r, contenu_taille=118)
    img.paste(m, (cx - r, cy - r), m)
    d.text((cx + r + 22, cy - 4), NOM, font=titre_police(36), fill=encre, anchor="ls")
    d.text((cx + r + 22, cy + 32), PSEUDO, font=texte_police(26), fill=encre, anchor="ls")
    if etiquette:
        _pastille(d, LARGEUR - MARGE, cy - 29, etiquette, encre, fond, 28, droite=True)


def _pleine_page(post: Post, numero: int, total: int):
    fond, encre = couleur_du_post(post.id)
    img = Image.new("RGB", (LARGEUR, HAUTEUR), fond)
    d = ImageDraw.Draw(img)
    return img, d, fond, encre


def _couverture_vive(post: Post, s: Slide, total: int) -> Image.Image:
    img, d, fond, encre = _pleine_page(post, 1, total)
    chiffre = _chiffre(post)
    if chiffre:
        # Le chiffre en filigrane, coupé par le bord : il se voit de loin
        # dans la grille, sans répéter le titre au premier plan.
        pg = _police("BricolageGrotesque.ttf", 760 if len(chiffre) <= 2 else 560, "ExtraBold")
        d.text((LARGEUR + 40, HAUTEUR - 70), chiffre, font=pg, fill=_ombre(fond), anchor="rs")
    _entete_vif(img, d, fond, encre, post.etiquette)

    largeur = LARGEUR - 2 * MARGE
    fab = lambda t: _police("BricolageGrotesque.ttf", t, "ExtraBold")  # noqa: E731
    p = _ajuster(s.titre, fab, 132, 72, largeur, 640, 1.02)
    pt = texte_police(42, gras=True)
    h = _hauteur(s.titre, p, largeur, 1.02)
    if s.texte:
        h += 48 + _hauteur(s.texte, pt, largeur - 40, 1.3) + 40
    y0 = max(330, 330 + (HAUTEUR - 300 - 330 - h) // 2)
    # Surligneur sous la dernière ligne : la chute de l'accroche.
    lignes = couper(s.titre, p, largeur)
    yl = y0 + int(p.size * 1.02) * (len(lignes) - 1)
    w = d.textlength(lignes[-1], font=p)
    # Jaune sur tous les fonds, blanc sur le jaune ; la ligne surlignée
    # passe toujours en encre foncée.
    marque = (255, 255, 255) if fond == SURLIGNEUR else SURLIGNEUR
    coul_derniere = (17, 20, 19)
    d.rounded_rectangle((MARGE - 14, yl + p.size * 0.14, MARGE + w + 16, yl + p.size * 1.04),
                        radius=14, fill=marque)
    y = y0
    pas = int(p.size * 1.02)
    for k, ligne in enumerate(lignes):
        d.text((MARGE, y), ligne, font=p, fill=coul_derniere if k == len(lignes) - 1 else encre)
        y += pas
    if s.texte:
        # La promesse dans une carte blanche : elle se détache du fond.
        hc = _hauteur(s.texte, pt, largeur - 40, 1.3) + 40
        wc = max(pt.getlength(l) for l in couper(s.texte, pt, largeur - 40)) + 40
        y += 48
        d.rounded_rectangle((MARGE - 6, y, MARGE + wc, y + hc), radius=22,
                            fill=(255, 255, 255))
        _bloc(d, MARGE + 20, y + 20, s.texte, pt, (17, 20, 19), largeur - 40, 1.3)
    if total > 1:
        _pastille(d, LARGEUR - MARGE, HAUTEUR - MARGE - 58, "Glisse", encre, fond, 32,
                  droite=True, fleche=True)
    return img


def _fond_photo(post_id: str) -> str | None:
    c = os.path.join(ICI, "fonds", f"{post_id}.jpg")
    return c if os.path.exists(c) else None


def _couverture_photo(post: Post, s: Slide, total: int, photo: str) -> Image.Image:
    """Couverture sur photo (alluxe_ia/fonds.py) : l'image en pleine page,
    un dégradé noir qui monte du bas pour que le titre blanc se lise
    toujours, la dernière ligne surlignée dans la couleur du post."""
    accent, encre_accent = couleur_du_post(post.id)
    if sum(accent) < 120:
        accent, encre_accent = SURLIGNEUR, (17, 20, 19)
    src = Image.open(photo).convert("RGB")
    k = max(LARGEUR / src.width, HAUTEUR / src.height)
    src = src.resize((int(src.width * k + 1), int(src.height * k + 1)), Image.LANCZOS)
    x0, y0 = (src.width - LARGEUR) // 2, (src.height - HAUTEUR) // 2
    img = src.crop((x0, y0, x0 + LARGEUR, y0 + HAUTEUR))
    # Voile : léger en haut (l'en-tête), fort en bas (le titre).
    voile = Image.new("L", (LARGEUR, HAUTEUR))
    dv = ImageDraw.Draw(voile)
    for y in range(HAUTEUR):
        t = y / HAUTEUR
        a = 70 * max(0.0, 1 - t / 0.22) + 240 * min(1.0, max(0.0, (t - 0.25) / 0.55)) ** 0.9
        dv.line((0, y, LARGEUR, y), fill=int(min(235, a)))
    img = Image.composite(Image.new("RGB", img.size, (8, 10, 10)), img, voile)
    d = ImageDraw.Draw(img)
    blanc = (255, 255, 255)
    _entete_vif(img, d, accent, blanc, "")
    if post.etiquette:
        _pastille(d, LARGEUR - MARGE, MARGE + 80 - 29, post.etiquette, accent, encre_accent,
                  28, droite=True)

    largeur = LARGEUR - 2 * MARGE
    fab = lambda t: _police("BricolageGrotesque.ttf", t, "ExtraBold")  # noqa: E731
    p = _ajuster(s.titre, fab, 124, 70, largeur, 520, 1.02)
    pt = texte_police(40, gras=True)
    lignes = couper(s.titre, p, largeur)
    pas = int(p.size * 1.02)
    hs = _hauteur(s.texte, pt, largeur, 1.3) if s.texte else 0
    bas = HAUTEUR - MARGE - 110
    y = bas - hs - (36 if s.texte else 0) - pas * len(lignes)
    for i, ligne in enumerate(lignes):
        if i == len(lignes) - 1:
            w = d.textlength(ligne, font=p)
            d.rounded_rectangle((MARGE - 14, y + p.size * 0.14, MARGE + w + 16,
                                 y + p.size * 1.04), radius=14, fill=accent)
            d.text((MARGE, y), ligne, font=p, fill=encre_accent)
        else:
            d.text((MARGE, y), ligne, font=p, fill=blanc)
        y += pas
    if s.texte:
        _bloc(d, MARGE, y + 36, s.texte, pt, (235, 235, 230), largeur, 1.3)
    if total > 1:
        _pastille(d, LARGEUR - MARGE, HAUTEUR - MARGE - 58, "Glisse", blanc, (17, 20, 19), 32,
                  droite=True, fleche=True)
    return img


def _entete_interieur(img, d, numero: int, total: int, accent, encre_accent) -> None:
    cx, cy, r = MARGE + 70, MARGE + 70, 70
    m = medaillon(2 * r, contenu_taille=104)
    img.paste(m, (cx - r, cy - r), m)
    d.text((cx + r + 20, cy - 4), NOM, font=titre_police(34), fill=ENCRE, anchor="ls")
    d.text((cx + r + 20, cy + 30), PSEUDO, font=texte_police(26), fill=DOUX, anchor="ls")
    _pastille(d, LARGEUR - MARGE, cy - 27, f"{numero}/{total}", accent, encre_accent, 26,
              droite=True)


def _texte_vif(img, d, s: Slide, accent) -> None:
    largeur = LARGEUR - 2 * MARGE - 34
    x = MARGE + 34
    fab = lambda t: _police("BricolageGrotesque.ttf", t, "ExtraBold")  # noqa: E731
    p = _ajuster(s.titre, fab, 80, 50, largeur, 340, 1.08)
    hp = _hauteur(s.titre, p, largeur, 1.08)
    pt = _ajuster(s.texte, texte_police, 46, 30, largeur, 760 - hp, 1.4)
    h = hp + 44 + _hauteur(s.texte, pt, largeur, 1.4)
    y0 = max(290, 290 + (HAUTEUR - 150 - 290 - h) // 2)
    # La barre de couleur du post : on sait sur quel post on est, même au milieu.
    d.rounded_rectangle((MARGE, y0 + 6, MARGE + 12, y0 + hp - 6), radius=6, fill=accent)
    y = _bloc(d, x, y0, s.titre, p, ENCRE, largeur, 1.08)
    _bloc(d, x, y + 44, s.texte, pt, DOUX, largeur, 1.4)


def _prompt_vif(img, d, s: Slide, accent, encre_accent) -> None:
    """Le prompt dans une fenêtre de conversation : barre de titre, bulle
    « Toi », champ de saisie. Générique : aucune marque d'outil imitée."""
    largeur = LARGEUR - 2 * MARGE
    p = _ajuster(s.titre, lambda t: _police("BricolageGrotesque.ttf", t, "ExtraBold"),
                 70, 44, largeur, 260, 1.08)
    hp = _hauteur(s.titre, p, largeur, 1.08)
    bulle = largeur - 2 * 34 - 60
    interieur = bulle - 2 * 30
    pm = _ajuster(s.prompt, mono_police, 30, 20, interieur, 900 - hp - 300, 1.42)
    hb = int(len(couper(s.prompt, pm, interieur)) * pm.size * 1.42) + 2 * 28
    barre, saisie = 74, 104
    hf = barre + 40 + 36 + hb + 34 + saisie
    y0 = max(280, 280 + (HAUTEUR - 140 - 280 - (hp + 40 + hf)) // 2)
    y = _bloc(d, MARGE, y0, s.titre, p, ENCRE, largeur, 1.08) + 40

    # Ombre portée douce, puis la fenêtre.
    for k in range(10, 0, -2):
        d.rounded_rectangle((MARGE + 4, y + k + 4, LARGEUR - MARGE + 4, y + hf + k + 4),
                            radius=30, fill=tuple(v - 3 * (12 - k) // 2 for v in FOND))
    d.rounded_rectangle((MARGE, y, LARGEUR - MARGE, y + hf), radius=30,
                        fill=(255, 255, 255), outline=BORD, width=2)
    d.rounded_rectangle((MARGE, y, LARGEUR - MARGE, y + barre), radius=30, fill=(242, 240, 234))
    d.rectangle((MARGE, y + barre - 30, LARGEUR - MARGE, y + barre), fill=(242, 240, 234))
    d.line((MARGE, y + barre, LARGEUR - MARGE, y + barre), fill=BORD, width=2)
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        cx = MARGE + 40 + i * 32
        d.ellipse((cx - 10, y + barre // 2 - 10, cx + 10, y + barre // 2 + 10), fill=c)
    d.text((LARGEUR // 2, y + barre // 2), "Nouvelle conversation",
           font=texte_police(26, gras=True), fill=DOUX, anchor="mm")

    yb = y + barre + 40
    xd = LARGEUR - MARGE - 34
    d.text((xd, yb), "Toi", font=texte_police(26, gras=True), fill=DOUX, anchor="rt")
    yb += 36
    d.rounded_rectangle((xd - bulle, yb, xd, yb + hb), radius=28, fill=accent)
    # Coin « queue » de la bulle, en haut à droite.
    d.rectangle((xd - 28, yb, xd, yb + 28), fill=accent)
    _bloc(d, xd - bulle + 30, yb + 28, s.prompt, pm, encre_accent, interieur, 1.42)

    ys = y + hf - saisie + 18
    d.rounded_rectangle((MARGE + 28, ys, LARGEUR - MARGE - 28, ys + saisie - 36),
                        radius=(saisie - 36) // 2, fill=(246, 244, 239), outline=BORD, width=2)
    d.text((MARGE + 60, ys + (saisie - 36) // 2), "Écris ton message…",
           font=texte_police(28), fill=(150, 150, 145), anchor="lm")
    r = (saisie - 36) // 2 - 8
    cx, cy = LARGEUR - MARGE - 28 - r - 10, ys + (saisie - 36) // 2
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(17, 20, 19))
    d.text((cx, cy), "↑", font=mono_police(32), fill=(255, 255, 255), anchor="mm")

    _pastille(d, MARGE, HAUTEUR - MARGE - 52, "PROMPT À VOLER", (17, 20, 19),
              (255, 255, 255), 26)
    d.text((LARGEUR - MARGE, HAUTEUR - MARGE - 26), "Sauvegarde ce post",
           font=texte_police(30, gras=True), fill=DOUX, anchor="rm")


def _appel_vif(post: Post, s: Slide, numero: int, total: int) -> Image.Image:
    img, d, fond, encre = _pleine_page(post, numero, total)
    _entete_vif(img, d, fond, encre, "")
    largeur = LARGEUR - 2 * MARGE
    amorce = s.titre or "Commente"
    pa = _police("BricolageGrotesque.ttf", 78, "ExtraBold")
    pt = texte_police(44, gras=True)
    h = int(78 * 1.1) + 40 + 170 + (40 + _hauteur(s.texte, pt, largeur, 1.35) if s.texte else 0)
    y = max(330, 330 + (HAUTEUR - 150 - 330 - h) // 2)
    d.text((MARGE, y), amorce, font=pa, fill=encre)
    y += int(78 * 1.1) + 40
    pm = _police("BricolageGrotesque.ttf", 116, "ExtraBold")
    w = int(pm.getlength(s.mot_cle))
    # Le cartouche à l'inverse du fond : la seule action demandée.
    d.rounded_rectangle((MARGE - 10, y, MARGE + w + 50, y + 150), radius=26, fill=encre)
    d.text((MARGE + 20, y + 75), s.mot_cle, font=pm, fill=fond, anchor="lm")
    y += 170
    if s.texte:
        _bloc(d, MARGE, y + 40, s.texte, pt, encre, largeur, 1.35)
    return img


def _rendre_vif(post: Post) -> list[Image.Image]:
    total = len(post.slides)
    accent, encre_accent = couleur_du_post(post.id)
    if sum(accent) < 120:            # le noir : la bulle prend le jaune
        accent, encre_accent = SURLIGNEUR, (17, 20, 19)
    images = []
    for i, s in enumerate(post.slides, start=1):
        if s.type == "couverture":
            photo = _fond_photo(post.id)
            images.append(_couverture_photo(post, s, total, photo) if photo
                          else _couverture_vive(post, s, total))
            continue
        if s.type == "appel" and i == total:
            images.append(_appel_vif(post, s, i, total))
            continue
        img = Image.new("RGB", (LARGEUR, HAUTEUR), FOND)
        d = ImageDraw.Draw(img)
        _entete_interieur(img, d, i, total, accent, encre_accent)
        if s.type == "texte":
            _texte_vif(img, d, s, accent)
        elif s.type == "prompt":
            _prompt_vif(img, d, s, accent, encre_accent)
        elif s.type == "appel":
            _appel_milieu_vif(d, s, accent, encre_accent)
        else:
            raise ValueError(f"type de slide inconnu : {s.type!r}")
        images.append(img)
    return images


def _appel_milieu_vif(d, s: Slide, accent, encre_accent) -> None:
    """Le rappel du kit au milieu du post, dans la couleur du post."""
    largeur = LARGEUR - 2 * MARGE
    pt = texte_police(42)
    h = 92 + 180 + (_hauteur(s.texte, pt, largeur, 1.35) if s.texte else 0)
    y = max(290, 290 + (HAUTEUR - 150 - 290 - h) // 2)
    d.text((MARGE, y), s.titre or "Commente",
           font=_police("BricolageGrotesque.ttf", 64, "ExtraBold"), fill=ENCRE)
    y += 92
    pm = _police("BricolageGrotesque.ttf", 110, "ExtraBold")
    w = int(pm.getlength(s.mot_cle))
    d.rounded_rectangle((MARGE - 8, y - 6, MARGE + w + 40, y + 136), radius=24, fill=accent)
    d.text((MARGE + 16, y + 65), s.mot_cle, font=pm, fill=encre_accent, anchor="lm")
    y += 180
    if s.texte:
        _bloc(d, MARGE, y, s.texte, pt, DOUX, largeur, 1.35)


def rendre(post: Post) -> list[Image.Image]:
    """Toutes les slides d'un post, dans l'ordre."""
    if THEME == "vif":
        return _rendre_vif(post)
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
    """La photo de profil : le medaillon Allure seul, lisible en 110 px.

    Instagram la recoupe en cercle : tout le dessin tient dans le disque
    central, rien d'important dans les coins.
    """
    img = Image.new("RGB", (taille, taille), FOND)
    m = medaillon(int(taille * 0.92))
    img.paste(m, ((taille - m.width) // 2, (taille - m.height) // 2), m)
    return img


def couverture_kit() -> tuple[Image.Image, Image.Image]:
    """Couverture (1280 x 720) et vignette (600 x 600) de la page Gumroad du kit,
    dans la charte des slides : meme fond, meme medaillon, meme menthe."""
    cou = Image.new("RGB", (1280, 720), FOND)
    d = ImageDraw.Draw(cou)
    for y in range(720):
        t = 1 - y / 720
        d.line([(0, y), (1280, y)],
               fill=tuple(int(FOND[i] + (FOND_HAUT[i] - FOND[i]) * t) for i in range(3)))
    m = medaillon(380)
    cou.paste(m, (100, 170), m)
    x = 560
    d.text((x, 200), "GRATUIT · PDF", font=mono_police(26), fill=MENTHE)
    d.text((x, 250), "Le kit du", font=titre_police(84), fill=ENCRE)
    d.text((x, 345), "constructeur", font=titre_police(84), fill=ENCRE)
    d.text((x, 470), "Mes prompts pour construire avec l'IA,", font=texte_police(32), fill=DOUX)
    d.text((x, 512), "sans être développeur.", font=texte_police(32), fill=DOUX)
    d.text((x, 590), PSEUDO, font=texte_police(30, gras=True), fill=AMBRE)

    vig = Image.new("RGB", (600, 600), FOND)
    dv = ImageDraw.Draw(vig)
    m = medaillon(300)
    vig.paste(m, (150, 70), m)
    dv.text((300, 430), "Le kit du constructeur", font=titre_police(44), fill=ENCRE, anchor="mm")
    dv.text((300, 492), "gratuit · " + PSEUDO, font=texte_police(28), fill=MENTHE, anchor="mm")
    return cou, vig
