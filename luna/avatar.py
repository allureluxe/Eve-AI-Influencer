"""L'avatar : tenues, expressions, ambiances, et la session visio.

L'application dessine Luna en local (avatar vectoriel anime dans le
navigateur, voir luna/web/). Ce module decrit ce qu'il faut dessiner :
la tenue, l'ambiance lumineuse, l'expression du moment.

Si tu branches un prestataire d'avatar video temps reel (HeyGen, D-ID,
Simli...), `FournisseurAvatar` est le point d'accroche : l'interface reste
la meme et le front bascule sur le flux du prestataire.
"""
from __future__ import annotations

import os
import random
from dataclasses import dataclass

from .limites import ADULTE, SENSUEL, TENDRE, rang


@dataclass(frozen=True)
class Tenue:
    cle: str
    nom: str
    registre: str
    # Couleurs utilisees par l'avatar vectoriel : haut, detail, fond.
    couleurs: tuple[str, str, str]
    description: str
    # Scene de luna.photos correspondante. Des qu'un generateur d'images est
    # configure, la visio affiche cette photo au lieu du dessin : c'est le
    # meme personnage, en photorealiste.
    scene: str = ""


TENUES = (
    Tenue("bureau", "tailleur de bureau", TENDRE, ("#2f3a56", "#dfe6f5", "#e8ecf6"),
          "veste cintree, chemisier clair, cheveux attaches", "bureau"),
    Tenue("sport", "tenue de sport", TENDRE, ("#3aa89a", "#e9fbf7", "#e6f7f4"),
          "brassiere et legging, queue de cheval, joues roses", "sport"),
    Tenue("decontracte", "pull oversize", TENDRE, ("#c98f7a", "#fceee6", "#f7efe9"),
          "grand pull confortable, cheveux laches", "romantique"),
    Tenue("soiree", "robe de soiree", TENDRE, ("#7b1f3a", "#f3cdd8", "#2a1622"),
          "robe elegante, boucles d'oreilles, brushing", "soiree"),
    Tenue("cuisine", "tablier a la maison", TENDRE, ("#d8a13f", "#fff3d8", "#f6efe2"),
          "chemise nouee et tablier, chignon rapide", "cuisine"),
    Tenue("vacances", "tenue d'ete", TENDRE, ("#f0c987", "#fff6e6", "#dff1f7"),
          "robe legere, lunettes de soleil sur la tete", "voyage"),
    Tenue("nuisette", "nuisette en soie", SENSUEL, ("#b06a86", "#f6d9e4", "#1f1622"),
          "nuisette soyeuse, epaules nues, lumiere basse", "fenetre"),
    Tenue("lingerie", "lingerie elegante", SENSUEL, ("#8e2b4d", "#f0c3d3", "#1a1018"),
          "ensemble de dentelle raffine, elegant et couvrant, style editorial", "boudoir"),
    Tenue("costume", "costume de jeu", SENSUEL, ("#43306b", "#e0d3f5", "#1b1526"),
          "deguisement choisi ensemble : infirmiere, policiere, chat, secretaire", "costume"),
)

TENUES_PAR_CLE = {t.cle: t for t in TENUES}

# Vers quoi retomber quand le registre ne permet pas la tenue prevue.
_REPLI = {"nuisette": "decontracte", "lingerie": "decontracte",
          "costume": "soiree"}


@dataclass(frozen=True)
class Ambiance:
    cle: str
    nom: str
    fond: tuple[str, str]   # degrade
    lumiere: str
    musique: str


AMBIANCES = (
    Ambiance("jour", "lumiere du jour", ("#eaf1ff", "#ffffff"), "claire et nette", "silence"),
    Ambiance("bureau", "open space", ("#e7ecf5", "#f7f9ff"), "neons doux", "brouhaha lointain"),
    Ambiance("chaleureuse", "salon le soir", ("#3a2a34", "#1d1520"), "lampe ambree", "jazz lent"),
    Ambiance("bougie", "a la bougie", ("#2a1b22", "#140d12"), "flamme vacillante", "piano feutre"),
    Ambiance("neon", "neon rose", ("#2a1030", "#120716"), "rose et violet", "electro lente"),
)

AMBIANCES_PAR_CLE = {a.cle: a for a in AMBIANCES}

# Expressions que sait jouer l'avatar vectoriel.
EXPRESSIONS = ("neutre", "sourire", "rire", "clin", "tendre", "surprise",
               "moue", "pensive", "seductrice")

_INDICES = (
    ("rire", ("😂", "🤣", "mdr", "haha")),
    ("clin", ("😉", "😏")),
    ("tendre", ("❤️", "🥰", "😘", "💕", "💋")),
    ("surprise", ("😮", "quoi ?!", "sérieux ?", "serieux ?")),
    ("moue", ("😢", "😞", "🥺", "boude")),
    ("pensive", ("hmm", "je me demande", "🤔")),
    ("seductrice", ("😈", "🔥", "viens ici")),
)


def expression_pour(texte: str, registre: str = TENDRE) -> str:
    """Devine l'expression a jouer a partir de ce que Luna vient de dire."""
    bas = (texte or "").lower()
    for expression, marqueurs in _INDICES:
        if any(m in bas for m in marqueurs):
            if expression == "seductrice" and rang(registre) < rang(SENSUEL):
                return "clin"
            return expression
    return "sourire"


JEUX = (
    ("tenue", "Choisis ma tenue", "Elle propose trois tenues, tu tranches."),
    ("verite", "Verite ou action (version douce)", "Questions de couple, gages legers."),
    ("questions", "36 questions", "Une question intime — au sens profond — chacun son tour."),
    ("devine", "Devine ce que je porte", "Trois indices, une reponse."),
    ("defi", "Le defi du soir", "Un petit defi a tenir jusqu'a demain."),
    ("quiz", "Tu me connais ?", "Elle te teste sur ce que tu sais d'elle."),
)


@dataclass
class SessionVisio:
    tenue: Tenue
    ambiance: Ambiance
    expression: str
    ouverture: str
    jeux: tuple[tuple[str, str, str], ...]
    registre: str
    fournisseur: str


def demarrer_visio(moment, registre: str = TENDRE, tenue: str = "",
                   ambiance: str = "") -> SessionVisio:
    """Prepare une session visio coherente avec le moment et le registre."""
    autorisees = [t for t in TENUES if rang(t.registre) <= rang(registre)]
    if tenue and tenue in TENUES_PAR_CLE and rang(TENUES_PAR_CLE[tenue].registre) <= rang(registre):
        choisie = TENUES_PAR_CLE[tenue]
    else:
        parordre = {"matin": "bureau", "travail": "bureau", "pause": "bureau",
                    "retour": "decontracte", "soiree": "soiree",
                    "soiree_privee": "nuisette", "nuit": "nuisette"}
        prefere = TENUES_PAR_CLE.get(parordre.get(moment.cle, "decontracte"))
        if prefere not in autorisees:
            # Registre insuffisant : on garde l'esprit du moment plutot que
            # de renvoyer la premiere tenue de la liste. Le soir sans acces
            # adulte, elle est en pull, pas en tailleur.
            prefere = TENUES_PAR_CLE.get(_REPLI.get(
                prefere.cle if prefere else "", "decontracte"))
        choisie = prefere if prefere in autorisees else autorisees[0]
    if ambiance and ambiance in AMBIANCES_PAR_CLE:
        amb = AMBIANCES_PAR_CLE[ambiance]
    else:
        paramoment = {"matin": "jour", "travail": "bureau", "pause": "bureau",
                      "retour": "chaleureuse", "soiree": "chaleureuse",
                      "soiree_privee": "neon", "nuit": "bougie"}
        amb = AMBIANCES_PAR_CLE.get(paramoment.get(moment.cle, "jour"), AMBIANCES[0])
    return SessionVisio(
        tenue=choisie,
        ambiance=amb,
        expression="sourire",
        ouverture=random.choice(moment.ouvertures),
        jeux=JEUX,
        registre=registre,
        fournisseur=FournisseurAvatar().nom,
    )


class FournisseurAvatar:
    """Point d'accroche pour un avatar video temps reel externe.

    Sans configuration, l'application dessine Luna elle-meme : avatar
    vectoriel anime dans le navigateur, synchronise sur la voix. C'est
    fluide, gratuit, et ca ne fuite rien.

    Avec LUNA_AVATAR_URL / LUNA_AVATAR_KEY / LUNA_AVATAR_ID renseignes,
    `configuration()` transmet au front de quoi ouvrir le flux du
    prestataire a la place.
    """

    def __init__(self, url: str = "", cle: str = "", identifiant: str = ""):
        self.url = url or os.getenv("LUNA_AVATAR_URL", "")
        self.cle = cle or os.getenv("LUNA_AVATAR_KEY", "")
        self.identifiant = identifiant or os.getenv("LUNA_AVATAR_ID", "")

    @property
    def disponible(self) -> bool:
        return bool(self.url and self.identifiant)

    @property
    def nom(self) -> str:
        return "externe" if self.disponible else "vectoriel"

    def configuration(self) -> dict:
        """Ce que le front doit savoir. La cle ne sort jamais du serveur."""
        if not self.disponible:
            return {"type": "vectoriel"}
        return {"type": "externe", "url": self.url, "avatar": self.identifiant}
