"""La memoire de Luna.

Une compagne qui oublie ton prenom entre deux sessions n'est pas une
compagne. Ce module garde trois choses, dans un simple fichier JSON :

- ce qu'elle sait de toi (prenom, gouts, dates, metier) ;
- les surnoms qu'elle te donne ;
- le fil des derniers echanges, pour la continuite.

L'extraction des faits est volontairement simple et lisible : des motifs
sur le texte. Pas de magie, pas d'appel reseau, rien qui puisse echouer
au milieu d'une conversation.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field

MAX_TOURS = 40
MAX_FAITS = 60


@dataclass
class Fait:
    categorie: str
    valeur: str
    horodatage: float = field(default_factory=time.time)

    def en_dict(self) -> dict:
        return {"categorie": self.categorie, "valeur": self.valeur,
                "horodatage": self.horodatage}


# Les motifs tolerent l'apostrophe droite, la typographique, et son
# absence : « moi c'est Marc », « moi c’est Marc » et « moi c est Marc »
# doivent tous marcher — on tape vite dans une conversation.
_AP = r"['’ ]?"

_MOTIFS = (
    ("prenom", re.compile(
        r"\b(?:je m" + _AP + r"appelle|moi c" + _AP + r"est|"
        r"mon (?:pr[eé]nom|nom) c" + _AP + r"est)\s+([A-Za-zÀ-ÿ'\-]{2,20})", re.I)),
    ("gout", re.compile(
        r"\bj" + _AP + r"(?:adore|aime)\s+(?!pas\b)([^.!?\n]{2,60})", re.I)),
    ("aversion", re.compile(
        r"\bje (?:d[eé]teste|n" + _AP + r"aime pas|supporte pas)\s+([^.!?\n]{2,60})", re.I)),
    ("metier", re.compile(
        r"\bje (?:travaille|bosse)\s+(?:comme|dans|chez)\s+([^.!?\n]{2,60})", re.I)),
    ("lieu", re.compile(
        r"\bj" + _AP + r"habite\s+(?:[aà]|en|au|dans)\s+([^.!?\n]{2,40})", re.I)),
    ("date", re.compile(
        r"\bmon anniversaire\s+(?:c" + _AP + r"est|est)?\s*(?:le\s+)?([^.!?\n]{2,30})", re.I)),
)


def _normaliser(texte: str) -> str:
    return (texte or "").replace("’", "'")


class Memoire:
    def __init__(self, fichier: str | None = None):
        self.fichier = fichier
        self.prenom: str = ""
        self.surnom: str = ""
        self.faits: list[Fait] = []
        self.tours: list[dict] = []
        self.rencontres: int = 0
        self.derniere_vue: float = 0.0
        self._charger()

    # -- persistance ------------------------------------------------------
    def _charger(self) -> None:
        if not self.fichier or not os.path.exists(self.fichier):
            return
        try:
            with open(self.fichier, "r", encoding="utf-8") as f:
                d = json.load(f)
        except (OSError, ValueError):
            return
        self.prenom = str(d.get("prenom", ""))
        self.surnom = str(d.get("surnom", ""))
        self.rencontres = int(d.get("rencontres", 0) or 0)
        self.derniere_vue = float(d.get("derniere_vue", 0.0) or 0.0)
        self.faits = [Fait(f.get("categorie", ""), f.get("valeur", ""),
                           float(f.get("horodatage", 0) or 0))
                      for f in d.get("faits", []) if isinstance(f, dict)]
        self.tours = [t for t in d.get("tours", []) if isinstance(t, dict)][-MAX_TOURS:]

    def sauver(self) -> None:
        if not self.fichier:
            return
        dossier = os.path.dirname(os.path.abspath(self.fichier))
        os.makedirs(dossier, exist_ok=True)
        tmp = self.fichier + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({
                "prenom": self.prenom,
                "surnom": self.surnom,
                "rencontres": self.rencontres,
                "derniere_vue": self.derniere_vue,
                "faits": [x.en_dict() for x in self.faits],
                "tours": self.tours[-MAX_TOURS:],
            }, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.fichier)

    # -- ecriture ---------------------------------------------------------
    def apprendre(self, message: str) -> list[Fait]:
        """Retient ce que le message revele, sans jamais dupliquer."""
        nouveaux: list[Fait] = []
        texte = _normaliser(message)
        for categorie, motif in _MOTIFS:
            for trouve in motif.findall(texte):
                valeur = " ".join(trouve.split()).strip(" ,;:.")
                if not valeur:
                    continue
                if categorie == "prenom":
                    valeur = valeur.capitalize()
                    if self.prenom.lower() == valeur.lower():
                        continue
                    self.prenom = valeur
                if any(f.categorie == categorie and f.valeur.lower() == valeur.lower()
                       for f in self.faits):
                    continue
                fait = Fait(categorie, valeur)
                self.faits.append(fait)
                nouveaux.append(fait)
        if len(self.faits) > MAX_FAITS:
            self.faits = self.faits[-MAX_FAITS:]
        return nouveaux

    def noter(self, role: str, texte: str) -> None:
        self.tours.append({"role": role, "texte": texte, "t": time.time()})
        self.tours = self.tours[-MAX_TOURS:]

    def bonjour(self) -> float:
        """Debut de session. Renvoie les heures ecoulees depuis la derniere."""
        maintenant = time.time()
        ecart = (maintenant - self.derniere_vue) / 3600.0 if self.derniere_vue else 0.0
        self.rencontres += 1
        self.derniere_vue = maintenant
        return ecart

    def oublier(self, categorie: str = "") -> int:
        avant = len(self.faits)
        if categorie:
            self.faits = [f for f in self.faits if f.categorie != categorie]
        else:
            self.faits, self.tours, self.prenom, self.surnom = [], [], "", ""
        self.sauver()
        return avant - len(self.faits)

    # -- lecture ----------------------------------------------------------
    def historique(self, n: int = 12) -> list[dict]:
        return self.tours[-n:]

    def resume(self) -> str:
        """Le bloc de memoire injecte dans le prompt."""
        lignes = []
        if self.prenom:
            lignes.append(f"Il s'appelle {self.prenom}.")
        if self.surnom:
            lignes.append(f"Tu le surnommes « {self.surnom} ».")
        par_categorie: dict[str, list[str]] = {}
        for f in self.faits:
            if f.categorie == "prenom":
                continue
            par_categorie.setdefault(f.categorie, []).append(f.valeur)
        etiquettes = {"gout": "Il aime", "aversion": "Il n'aime pas",
                      "metier": "Travail", "lieu": "Il habite", "date": "Dates"}
        for cle, valeurs in par_categorie.items():
            lignes.append(f"{etiquettes.get(cle, cle)} : " + ", ".join(valeurs[-8:]) + ".")
        if self.rencontres > 1:
            lignes.append(f"Vous vous etes deja parle {self.rencontres} fois.")
        if not lignes:
            return "Tu ne sais encore rien de lui. Sois curieuse, pose des questions."
        return "\n".join(lignes)
