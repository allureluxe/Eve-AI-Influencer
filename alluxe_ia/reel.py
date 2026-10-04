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
import math
import os
import subprocess
import sys
from dataclasses import dataclass

from PIL import Image, ImageDraw

from alluxe_ia.musique import ecrire_wav
from alluxe_ia.slides import (AMBRE, DOUX, ENCRE, FOND, FOND_HAUT, MENTHE, NOM, PSEUDO,
                              SURLIGNEUR, _police, couleur_du_post, couper, medaillon,
                              mono_police, texte_police, titre_police)

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
        "ambiance": "motivation",
        "fond": "01-tout-construit", "etiquette": "COULISSES",
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
    # 4 oct. : histoire vraie du jour (l'assistant de alluxe.fr, gpt-oss-20b,
    # a répondu « à partir de 79 € » pour le kit gratuit). Court : ~18 s.
    "02-ia-invente-un-prix": {
        "ambiance": "mystere",
        "fond": "15-expliquer-un-bug", "etiquette": "HISTOIRE VRAIE",
        "legende": (
            "Mon assistant IA a inventé un prix pour un kit… qui est gratuit.\n\n"
            "Une IA ne dit pas « je ne sais pas » toute seule : sans les faits, elle "
            "invente la réponse la plus probable. Ces 3 phrases l'en empêchent. "
            "Garde-les pour tes propres prompts.\n\n"
            "📎 Le kit du constructeur (gratuit) : lien dans ma bio.\n\n"
            "#ia #chatgpt #claude #prompt #intelligenceartificielle #nocode #buildinpublic"),
        "temps": [
            Temps("Mon assistant IA a inventé un prix.", 2.4, taille=110),
            Temps("« Le kit ? À partir de 79 €. »", 2.4, taille=104, couleur=AMBRE),
            Temps("Le kit est gratuit.", 2.0, taille=118, couleur=MENTHE),
            Temps("3 phrases l'ont fait arrêter :", 2.2, taille=100),
            Temps("1. « Voici les faits : […] »", 2.0),
            Temps("2. « N'invente aucun prix ni lien. »", 2.2),
            Temps("3. « Si tu ne sais pas, dis-le. »", 2.4, couleur=MENTHE),
            Temps("Le prompt complet est dans le kit.", 3.0, taille=96, couleur=ENCRE,
                  sous_texte="12 prompts que j'utilise vraiment.",
                  mot_cle="Lien en bio"),
        ],
    },
    # 4 oct., décision de l'opérateur : des sujets INTEMPORELS, utiles à
    # celui qui regarde, plus des histoires personnelles. Pensés pour être
    # enregistrés et partagés : c'est ce qui fait grandir un compte.
    "03-ia-invente": {
        "ambiance": "mystere",
        "fond": "24-ia-qui-invente", "etiquette": "À SAUVEGARDER",
        "legende": (
            "Une IA ne dit presque jamais « je ne sais pas » d'elle-même : sans les faits, elle "
            "invente la réponse la plus probable.\n\n"
            "Colle ces 3 phrases à la fin de tes prompts.\n\n"
            "💾 Enregistre-le. 👉 Envoie-le à quelqu'un qui croit tout ce que dit ChatGPT.\n\n"
            "📎 Le kit gratuit (12 prompts) : lien dans ma bio.\n\n"
            "#chatgpt #ia #intelligenceartificielle #prompt #astuce #productivite #outilsia"),
        "temps": [
            Temps("ChatGPT invente quand il ne sait pas.", 2.6, taille=110),
            Temps("3 phrases l'en empêchent. La dernière change tout.", 2.6, taille=96,
                  couleur=MENTHE),
            Temps("1. « Réponds uniquement avec ces informations. »", 2.8),
            Temps("2. « N'invente aucun chiffre, nom ou lien. »", 2.8),
            Temps("3. « Si tu ne sais pas, dis-le. »", 2.6, couleur=MENTHE),
            Temps("Enregistre-le pour ton prochain prompt.", 2.4, taille=96),
            Temps("12 prompts comme ça, gratuits :", 3.0, taille=96,
                  sous_texte="abonne-toi pour la suite.", mot_cle="Lien en bio"),
        ],
    },
    "04-sept-phrases": {
        "ambiance": "energie",
        "fond": "25-sept-mots", "etiquette": "À SAUVEGARDER",
        "legende": (
            "Pas besoin de longs prompts : ajoute une de ces phrases à la fin, et la réponse "
            "change.\n\n"
            "💾 Enregistre-le. 👉 Envoie-le à la personne qui utilise ChatGPT tous les jours.\n\n"
            "📎 Le kit gratuit (12 prompts) : lien dans ma bio.\n\n"
            "#chatgpt #ia #intelligenceartificielle #prompt #astuce #productivite #outilsia"),
        "temps": [
            Temps("7 phrases qui changent n'importe quelle réponse d'IA.", 2.8, taille=104),
            Temps("La n°4 est la plus sous-estimée.", 1.9, taille=100, couleur=MENTHE),
            Temps("« Étape par étape »", 1.8, taille=104, couleur=MENTHE),
            Temps("« Pose-moi d'abord des questions »", 2.0, taille=100),
            Temps("« Donne 3 options différentes »", 1.9, taille=100, couleur=MENTHE),
            Temps("« Critique ta réponse, puis améliore-la »", 2.2, taille=96),
            Temps("« Explique-le à un enfant de 10 ans »", 2.1, taille=96, couleur=MENTHE),
            Temps("« Avec un exemple concret »", 1.9, taille=100),
            Temps("« En tableau »", 1.8, taille=110, couleur=MENTHE),
            Temps("Les prompts complets :", 3.0, taille=100,
                  sous_texte="abonne-toi : un prompt utile par jour.", mot_cle="Lien en bio"),
        ],
    },
    "05-comme-google": {
        "ambiance": "punch",
        "fond": "23-chatgpt-comme-google", "etiquette": "MÉTHODE",
        "legende": (
            "Tu tapes 4 mots comme sur Google ? L'IA te répond comme Google : vague. "
            "Donne-lui ces 4 choses.\n\n"
            "💾 Enregistre-le. 👉 Envoie-le à quelqu'un qui trouve que ChatGPT ne sert à rien.\n\n"
            "📎 Le kit gratuit (12 prompts) : lien dans ma bio.\n\n"
            "#chatgpt #ia #intelligenceartificielle #prompt #astuce #productivite #outilsia"),
        "temps": [
            Temps("Tu parles à ChatGPT comme à Google ?", 2.4, taille=110),
            Temps("Voilà pourquoi ses réponses sont vagues. Il lui manque 4 choses.", 2.6,
                  taille=96, couleur=MENTHE),
            Temps("1. Un rôle : « Tu es prof de maths. »", 2.6),
            Temps("2. Une tâche : « Rédige, compare, corrige. »", 2.6),
            Temps("3. Le contexte : pour qui, pourquoi.", 2.6, couleur=MENTHE,
                  sous_texte="celle que tout le monde oublie."),
            Temps("4. Le format : « en 5 points ».", 2.4),
            Temps("Le modèle à copier :", 3.0, taille=100,
                  sous_texte="+ 11 autres prompts, gratuits.", mot_cle="Lien en bio"),
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


# ---------------------------------------------------------------- style « vif »
#
# 4 oct., même demande que pour les carrousels : un Reel qui accroche dès
# la première image. La photo du post (alluxe_ia/fonds) en plein écran,
# qui avance lentement (effet « Ken Burns » : l'image vit sans distraire),
# un voile sombre pour que le blanc se lise, et les phrases fortes
# surlignées dans la couleur du post. Sans photo, l'ancien fond reste.

ZOOM = 1.14     # la photo avance de 14 % sur toute la durée

# LE RYTHME (4 oct., demande de l'opérateur : « que ça tape, que ça les
# tienne concentrés »). Chaque ambiance a le tempo typique de ses styles
# (phonk ~140, funk/jersey ~130, drill ~142, afro ~108, lo-fi ~84). Chaque
# texte dure un nombre PAIR de temps (arrondi au-dessus : le temps de
# lecture n'est jamais raccourci), donc chaque changement tombe sur un
# temps fort ; la photo donne un petit coup de zoom à chaque temps, un plus
# franc à chaque nouveau texte.
#
# Limite honnête : avec notre musique composée, le calage est exact (même
# tempo, départ à 0). Avec un son Instagram, le tempo est le bon ordre de
# grandeur mais le départ du morceau n'est pas maîtrisé.
TEMPOS = {"mystere": 140, "energie": 130, "punch": 142, "motivation": 108, "chill": 140}
# Le beat composé de chaque ambiance (alluxe_ia/musique.py) : plus de piano.
STYLE_DE_L_AMBIANCE = {"mystere": "phonk", "energie": "funk", "punch": "drill",
                       "motivation": "afro", "chill": "trap"}


def tempo(reel_id: str) -> float:
    return TEMPOS.get(REELS[reel_id].get("ambiance", "chill"), 140)


def durees_calees(reel_id: str) -> list[float]:
    battement = 60.0 / tempo(reel_id)
    return [2 * math.ceil(t.duree / battement / 2) * battement for t in REELS[reel_id]["temps"]]


def _coup(dt: float, force: float, chute: float) -> float:
    return force * math.exp(-dt / chute) if dt >= 0 else 0.0


def _photo_reel(post_id: str) -> Image.Image | None:
    c = os.path.join(ICI, "fonds", f"{post_id}.jpg")
    if not os.path.exists(c):
        return None
    src = Image.open(c).convert("RGB")
    lg, ht = int(LARGEUR * ZOOM), int(HAUTEUR * ZOOM)
    k = max(lg / src.width, ht / src.height)
    src = src.resize((int(src.width * k + 1), int(src.height * k + 1)), Image.LANCZOS)
    x0, y0 = (src.width - lg) // 2, (src.height - ht) // 2
    return src.crop((x0, y0, x0 + lg, y0 + ht))


def _voile_vif() -> Image.Image:
    """Noir translucide : léger en haut, plus dense derrière le texte et
    sous la légende d'Instagram."""
    v = Image.new("RGBA", (LARGEUR, HAUTEUR))
    d = ImageDraw.Draw(v)
    for y in range(HAUTEUR):
        t = y / HAUTEUR
        a = 150 + 60 * min(1.0, max(0.0, (t - 0.25) / 0.35)) - 40 * max(0.0, (t - 0.85) / 0.15)
        d.line((0, y, LARGEUR, y), fill=(6, 8, 8, int(a)))
    return v


def _entete_vif(img: Image.Image, accent, encre_accent, etiquette: str) -> None:
    d = ImageDraw.Draw(img)
    r = 110
    m = medaillon(2 * r, contenu_taille=160)
    img.paste(m, (GAUCHE, HAUT_LIBRE - 60), m)
    cy = HAUT_LIBRE - 60 + r
    blanc = (255, 255, 255)
    d.text((GAUCHE + 2 * r + 26, cy - 4), NOM, font=titre_police(42), fill=blanc, anchor="ls")
    d.text((GAUCHE + 2 * r + 26, cy + 38), PSEUDO, font=texte_police(30), fill=(225, 225, 220),
           anchor="ls")
    if etiquette:
        p = texte_police(30, gras=True)
        w = int(p.getlength(etiquette)) + 52
        y = cy + 70
        x = GAUCHE + 2 * r + 26
        d.rounded_rectangle((x, y, x + w, y + 56), radius=28, fill=accent)
        d.text((x + 26, y + 28), etiquette, font=p, fill=encre_accent, anchor="lm")


def _calque_vif(t: Temps, accent, encre_accent) -> tuple[Image.Image, int]:
    """Texte blanc ; un temps en couleur devient une phrase surlignée."""
    police = _police("BricolageGrotesque.ttf", t.taille, "ExtraBold")
    lignes = couper(t.texte, police, LARGEUR_TEXTE)
    interligne = int(t.taille * 1.14)
    fort = t.couleur != ENCRE
    h = interligne * len(lignes)
    if t.mot_cle:
        h += 70 + 80 + 120
    if t.sous_texte:
        h += 30 + 50 * len(couper(t.sous_texte, texte_police(40, gras=True), LARGEUR_TEXTE))
    img = Image.new("RGBA", (LARGEUR, h + 40), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    y = 0
    for ligne in lignes:
        if fort:
            w = d.textlength(ligne, font=police)
            d.rounded_rectangle((GAUCHE - 14, y + t.taille * 0.12, GAUCHE + w + 16,
                                 y + t.taille * 1.06), radius=14, fill=accent)
        d.text((GAUCHE, y), ligne, font=police, fill=encre_accent if fort else (255, 255, 255))
        y += interligne
    if t.mot_cle:
        y += 70
        d.text((GAUCHE, y + 6), t.amorce, font=_police("BricolageGrotesque.ttf", 58, "ExtraBold"),
               fill=(255, 255, 255))
        y += 80
        pm = _police("BricolageGrotesque.ttf", 92, "ExtraBold")
        w = int(d.textlength(t.mot_cle, font=pm))
        d.rounded_rectangle((GAUCHE, y - 6, GAUCHE + w + 48, y + 110), radius=22, fill=accent)
        d.text((GAUCHE + 24, y + 52), t.mot_cle, font=pm, fill=encre_accent, anchor="lm")
        y += 120
    if t.sous_texte:
        y += 30
        for ligne in couper(t.sous_texte, texte_police(40, gras=True), LARGEUR_TEXTE):
            d.text((GAUCHE, y), ligne, font=texte_police(40, gras=True), fill=(230, 230, 225))
            y += 50
    return img, h


def images_vif(reel_id: str):
    """Les images du Reel en style vif, ou None s'il n'a pas de photo."""
    r = REELS[reel_id]
    photo = _photo_reel(r.get("fond", ""))
    if photo is None:
        return None
    accent, encre_accent = couleur_du_post(r["fond"])
    if sum(accent) < 120:
        accent, encre_accent = SURLIGNEUR, (17, 20, 19)
    voile = _voile_vif()
    temps = r["temps"]
    durees = durees_calees(reel_id)
    total = sum(durees)
    battement = 60.0 / tempo(reel_id)
    entree = min(ENTREE, battement * 0.5)      # le texte claque sur le temps

    def gen():
        debut = 0.0
        for k, (t, duree) in enumerate(zip(temps, durees)):
            calque, h = _calque_vif(t, accent, encre_accent)
            y0 = max(HAUT_LIBRE + 330, (HAUT_LIBRE + 330 + BAS_LIBRE) // 2 - h // 2)
            for i in range(round(duree * IPS)):
                s = i / IPS
                u = (debut + s) / total
                horloge = debut + s
                coup = (_coup(horloge % battement, 0.012, 0.10)
                        + (_coup(s, 0.035, 0.16) if k else 0.0))
                lg = (photo.width - (photo.width - LARGEUR) * u) / (1 + coup)
                ht = min(lg * HAUTEUR / LARGEUR, photo.height)
                x0, yb = (photo.width - lg) / 2, max(0.0, (photo.height - ht) / 2)
                img = photo.resize((LARGEUR, HAUTEUR), Image.BILINEAR,
                                   box=(x0, yb, x0 + lg, yb + ht)).convert("RGBA")
                img.alpha_composite(voile)
                _entete_vif(img, accent, encre_accent, r.get("etiquette", ""))
                p = 1.0 if k == 0 else _adoucir(s / entree)
                c = calque
                if p < 1:
                    c = calque.copy()
                    c.putalpha(c.getchannel("A").point(lambda a, p=p: int(a * p)))
                img.alpha_composite(c, (0, int(y0 + (1 - p) * 60)))
                d = ImageDraw.Draw(img)
                d.rectangle((GAUCHE, BAS_LIBRE + 40, LARGEUR - 160, BAS_LIBRE + 46),
                            fill=(255, 255, 255, 70))
                d.rectangle((GAUCHE, BAS_LIBRE + 40,
                             GAUCHE + int((LARGEUR - 160 - GAUCHE) * u), BAS_LIBRE + 46),
                            fill=accent)
                yield img.convert("RGB")
            debut += duree
    return gen()


def rendre(reel_id: str, sortie: str | None = None, style: str = "vif") -> str:
    temps = REELS[reel_id]["temps"]
    sortie = sortie or os.path.join(RACINE, "data", "alluxe_ia", "reels", f"{reel_id}.mp4")
    os.makedirs(os.path.dirname(sortie), exist_ok=True)
    flux = images_vif(reel_id) if style == "vif" else None
    if flux is not None:
        duree, bpm = sum(durees_calees(reel_id)), tempo(reel_id)
    else:
        duree, bpm = sum(t.duree for t in temps), None
    piste = sortie + ".musique.wav"
    style_musique = STYLE_DE_L_AMBIANCE.get(REELS[reel_id].get("ambiance", ""))
    ecrire_wav(piste, duree, graine=reel_id, bpm=bpm, style=style_musique)
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{LARGEUR}x{HAUTEUR}",
           "-r", str(IPS), "-i", "-",
           "-i", piste,
           "-t", f"{duree:.2f}",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-profile:v", "high",
           "-preset", "medium", "-crf", "20", "-movflags", "+faststart",
           "-c:a", "aac", "-b:a", "128k", "-shortest", sortie]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for img in flux or images(temps):
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
    print(rendre(sys.argv[1] if len(sys.argv) > 1 else "01-tout-construit",
                 style=sys.argv[2] if len(sys.argv) > 2 else "vif"))
