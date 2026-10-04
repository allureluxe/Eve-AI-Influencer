"""Le « style pop » des carrousels de @alluxe.ia (4 oct.).

Demande de l'opérateur : « que mon compte claque, que les gens soient pris
dès qu'ils tombent dessus ». Ce qui marche chez les comptes IA qui
grossissent : fond clair et contrasté, couleurs vives, une étiquette qui
intrigue, de gros chiffres, des fenêtres d'IA réalistes, une phrase
citable en grand. Le sombre d'avant était mal lu et assombri encore par
la compression d'Instagram.

Chaque post reçoit une couleur vive (tournante d'un post à l'autre) : la
grille du profil devient une mosaïque de couleurs, pas un mur noir.

Mêmes données que slides.py (alluxe_ia/posts.json), même format 1080x1350.
"""
from __future__ import annotations

from PIL import Image, ImageDraw

from alluxe_ia.slides import (HAUTEUR, LARGEUR, PSEUDO, Post, Slide, couper, medaillon,
                              mono_police, texte_police, titre_police)

CREME = (250, 247, 240)
NOIR = (17, 20, 19)
GRIS = (78, 86, 82)
BLANC = (255, 255, 255)
COULEURS = [
    (255, 214, 64),    # jaune
    (92, 224, 198),    # menthe
    (255, 128, 96),    # corail
    (186, 168, 255),   # lilas
    (120, 190, 255),   # bleu ciel
]
M = 84                                   # marge


def couleur_du_post(post: Post) -> tuple:
    """Même couleur que la couverture photo de slides.py : un post = une couleur.
    Les couleurs trop sombres pour un fond de page passent au jaune."""
    from alluxe_ia import slides as base
    c = base.couleur_du_post(post.id)[0]
    return c if sum(c) >= 360 else COULEURS[0]


def etiquette(post: Post) -> str:
    if getattr(post, "etiquette", ""):
        return post.etiquette
    for s in post.slides:
        if s.type == "couverture" and s.etiquette:
            return s.etiquette
    histoire = any(s.type == "texte" and s.titre.startswith(("Ce qui s'est passé", "Le problème",
                                                                "Ce que je voyais", "Le symptôme",
                                                                "La proposition"))
                   for s in post.slides)
    prompt = any(s.type == "prompt" for s in post.slides)
    if histoire and prompt:
        return "HISTOIRE VRAIE + PROMPT"
    if histoire:
        return "HISTOIRE VRAIE"
    if prompt:
        return "PROMPT À COPIER"
    return "À GARDER"


def _ajuste(texte: str, depart: int, mini: int, largeur: int, hmax: int, inter: float):
    t = depart
    while t > mini:
        p = titre_police(t)
        if len(couper(texte, p, largeur)) * t * inter <= hmax:
            return p
        t -= 4
    return titre_police(mini)


def _ajuste_texte(texte: str, depart: int, mini: int, largeur: int, hmax: int, inter: float):
    t = depart
    while t > mini:
        p = texte_police(t)
        if len(couper(texte, p, largeur)) * t * inter <= hmax:
            return p
        t -= 2
    return texte_police(mini)


def _lignes(d, x, y, texte, police, couleur, largeur, inter) -> int:
    for li in couper(texte, police, largeur):
        d.text((x, y), li, font=police, fill=couleur)
        y += int(police.size * inter)
    return y


def _pastille(d, x, y, texte, fond, encre, taille=30) -> int:
    p = texte_police(taille, gras=True)
    w = d.textlength(texte, font=p)
    d.rounded_rectangle((x, y, x + w + 44, y + taille + 30), radius=(taille + 30) // 2, fill=fond)
    d.text((x + 22, y + 13), texte, font=p, fill=encre)
    return int(x + w + 44)


def _entete(img, d, numero, total, sur_couleur: bool) -> None:
    # Logo agrandi le 4 oct. : 96 -> 150 px, pseudo 32 -> 44 px.
    m = medaillon(150, contenu_taille=112)
    img.paste(m, (M, 50), m)
    d.text((M + 168, 104), PSEUDO, font=texte_police(44, gras=True), fill=NOIR)
    if total > 1:
        texte = f"{numero}/{total}"
        p = mono_police(26)
        w = d.textlength(texte, font=p)
        d.rounded_rectangle((LARGEUR - M - w - 32, 86, LARGEUR - M, 132), radius=23,
                            fill=NOIR if sur_couleur else BLANC, outline=None if sur_couleur else (226, 222, 212),
                            width=2)
        d.text((LARGEUR - M - w - 16, 94), texte, font=p, fill=BLANC if sur_couleur else NOIR)


def _fleche(d, couleur_fond) -> None:
    """Le bouton « glisse » : un rond noir et une flèche, en bas à droite."""
    cx, cy, r = LARGEUR - M - 50, HAUTEUR - M - 40, 50
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=NOIR)
    d.line((cx - 20, cy, cx + 18, cy), fill=couleur_fond, width=8)
    d.line((cx + 2, cy - 18, cx + 20, cy, cx + 2, cy + 18), fill=couleur_fond, width=8, joint="curve")
    d.text((cx - r - 20, cy), "GLISSE", font=texte_police(32, gras=True), fill=NOIR, anchor="rm")


def _couverture(img, d, s: Slide, post: Post, couleur) -> None:
    larg = LARGEUR - 2 * M
    y = 250
    _pastille(d, M, y, etiquette(post), NOIR, couleur, 30)
    y += 110
    p = _ajuste(s.titre, 132, 72, larg, 640, 1.04)
    lignes = couper(s.titre, p, larg)
    inter = int(p.size * 1.04)
    # La dernière ligne sur un ruban blanc : c'est la chute de l'accroche.
    yl = y + inter * (len(lignes) - 1)
    w = d.textlength(lignes[-1], font=p)
    d.rounded_rectangle((M - 14, yl + p.size * 0.12, M + w + 16, yl + p.size * 1.06), radius=14,
                        fill=BLANC)
    for li in lignes:
        d.text((M, y), li, font=p, fill=NOIR)
        y += inter
    if s.texte:
        _lignes(d, M, y + 36, s.texte, texte_police(42, gras=True), NOIR, larg - 40, 1.3)
    _fleche(d, couleur)


def _texte(img, d, s: Slide, couleur) -> None:
    larg = LARGEUR - 2 * M
    titre, numero = s.titre, ""
    # « 2. Les commentaires invisibles » -> un gros chiffre de couleur au-dessus.
    if len(titre) > 2 and titre[0].isdigit() and titre[1] == ".":
        numero, titre = titre[0], titre[2:].strip()
    pt = _ajuste(titre, 92, 56, larg, 320, 1.08)
    ht = len(couper(titre, pt, larg)) * int(pt.size * 1.08)
    hn = 230 if numero else 0
    px = _ajuste_texte(s.texte, 56, 34, larg - 40, HAUTEUR - 330 - hn - ht - 40, 1.38)
    hx = len(couper(s.texte, px, larg - 40)) * int(px.size * 1.38)
    # Le bloc entier est centré entre l'en-tête et le bas : plus de grand vide.
    y = max(220, 200 + (HAUTEUR - 200 - 80 - (hn + ht + 40 + hx)) // 2)
    if numero:
        d.text((M - 6, y - 40), numero, font=titre_police(240), fill=couleur,
               stroke_width=7, stroke_fill=NOIR)
        y += hn
    y = _lignes(d, M, y, titre, pt, NOIR, larg, 1.08) + 40
    # Trait de couleur à gauche du texte, comme une note surlignée.
    d.rounded_rectangle((M, y + 6, M + 12, y + hx - 14), radius=6, fill=couleur)
    _lignes(d, M + 40, y, s.texte, px, GRIS, larg - 40, 1.38)


def _lecon(img, d, s: Slide, couleur) -> None:
    """La phrase citable : en grand, sur noir. C'est elle qui se partage."""
    larg = LARGEUR - 2 * M
    _pastille(d, M, 250, s.titre.upper(), couleur, NOIR, 28)
    d.text((M - 10, 300), "“", font=titre_police(260), fill=couleur)
    p = _ajuste(s.texte, 80, 46, larg, 620, 1.16)
    y = 540
    _lignes(d, M, y, s.texte, p, BLANC, larg, 1.16)
    d.text((M, HAUTEUR - M - 30), "Partage-le à quelqu'un qui en a besoin",
           font=texte_police(32, gras=True), fill=couleur, anchor="ls")


def _prompt(img, d, s: Slide, couleur) -> None:
    larg = LARGEUR - 2 * M
    pt = _ajuste(s.titre, 72, 48, larg, 200, 1.08)
    y = _lignes(d, M, 250, s.titre, pt, NOIR, larg, 1.08) + 34
    interieur = larg - 2 * 40
    pm = mono_police(34)
    for t in range(34, 20, -1):
        pm = mono_police(t)
        if len(couper(s.prompt, pm, interieur)) * t * 1.45 <= HAUTEUR - y - 330:
            break
    corps = len(couper(s.prompt, pm, interieur)) * int(pm.size * 1.45) + 60
    # Ombre, puis la fenêtre : barre noire à trois points, corps blanc.
    d.rounded_rectangle((M + 10, y + 14, LARGEUR - M + 10, y + 84 + corps + 14), radius=26, fill=(222, 216, 204))
    d.rounded_rectangle((M, y, LARGEUR - M, y + 84 + corps), radius=26, fill=BLANC,
                        outline=NOIR, width=4)
    d.rounded_rectangle((M, y, LARGEUR - M, y + 80), radius=26, fill=NOIR)
    d.rectangle((M, y + 50, LARGEUR - M, y + 80), fill=NOIR)
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        d.ellipse((M + 30 + i * 40, y + 28, M + 54 + i * 40, y + 52), fill=c)
    _pastille(d, LARGEUR - M - 240, y + 16, "COPIE-MOI", couleur, NOIR, 24)
    _lignes(d, M + 40, y + 114, s.prompt, pm, NOIR, interieur, 1.45)
    # Le marque-page : enregistrer est le signal le plus fort pour Instagram.
    bx, by = M, HAUTEUR - M - 64
    d.polygon([(bx, by), (bx + 36, by), (bx + 36, by + 48), (bx + 18, by + 34), (bx, by + 48)], fill=NOIR)
    d.text((bx + 56, by + 6), "Enregistre ce post pour plus tard", font=texte_police(34, gras=True), fill=NOIR)


def _appel(img, d, s: Slide, couleur) -> None:
    larg = LARGEUR - 2 * M
    y = 420
    d.text((M, y), s.titre or "Le kit gratuit :", font=titre_police(76), fill=NOIR)
    y += 130
    pm = titre_police(118)
    w = d.textlength(s.mot_cle, font=pm)
    d.rounded_rectangle((M - 10, y, M + w + 50, y + 168), radius=84, fill=NOIR)
    d.text((M + 20, y + 14), s.mot_cle, font=pm, fill=couleur)
    y += 230
    if s.texte:
        _lignes(d, M, y, s.texte, texte_police(46, gras=True), NOIR, larg, 1.3)


LECONS = ("La leçon", "Les 3 leçons", "La règle", "Mon critère", "La case qui compte")


def rendre(post: Post) -> list[Image.Image]:
    couleur = couleur_du_post(post)
    total = len(post.slides)
    images = []
    for i, s in enumerate(post.slides, start=1):
        # Couverture : la photo du sujet (alluxe_ia/fonds/<id>.jpg) si elle existe,
        # avec le voile et le titre surligné de slides.py ; sinon la couleur pleine.
        if s.type == "couverture":
            from alluxe_ia import slides as base
            photo = base._fond_photo(post.id)
            if photo:
                if not getattr(post, "etiquette", ""):
                    try:
                        post.etiquette = etiquette(post)
                    except AttributeError:
                        pass
                images.append(base._couverture_photo(post, s, total, photo))
                continue
        lecon = s.type == "texte" and s.titre.startswith(LECONS)
        sur_couleur = s.type in ("couverture", "appel")
        fond = couleur if sur_couleur else NOIR if lecon else CREME
        img = Image.new("RGB", (LARGEUR, HAUTEUR), fond)
        d = ImageDraw.Draw(img)
        if lecon:
            m = medaillon(150, contenu_taille=112)
            img.paste(m, (M, 50), m)
            d.text((M + 168, 104), PSEUDO, font=texte_police(44, gras=True), fill=BLANC)
        else:
            _entete(img, d, i, total, sur_couleur)
        if s.type == "couverture":
            _couverture(img, d, s, post, couleur)
        elif lecon:
            _lecon(img, d, s, couleur)
        elif s.type == "texte":
            _texte(img, d, s, couleur)
        elif s.type == "prompt":
            _prompt(img, d, s, couleur)
        elif s.type == "appel":
            _appel(img, d, s, couleur)
        else:
            raise ValueError(f"type de slide inconnu : {s.type!r}")
        images.append(img)
    return images
