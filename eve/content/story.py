"""Le récit d'Eve, indexé sur l'avancée réelle du projet.

Principe : **l'histoire ne peut pas devancer la réalité.** Chaque épisode de
l'arc est verrouillé tant que l'étape correspondante n'a pas été franchie
pour de vrai, dans `data/trading/journal.json` — un fichier que tu remplis
au fur et à mesure.

C'est ce qui distingue « construire en public » d'une mise en scène : le
jour où le compte perd, Eve le raconte, parce que le fichier le dit.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from eve.config import settings

JOURNAL_PATH = settings.paths.data / "trading" / "journal.json"


class JournalError(ValueError):
    """Journal présent mais incohérent : on préfère bloquer que raconter faux."""


@dataclass(frozen=True)
class Entree:
    date: str
    etape: str                    # clé d'une étape de l'arc, ou ""
    solde_eur: float | None       # None tant qu'aucun compte réel n'existe
    note: str = ""

    @property
    def a_un_solde(self) -> bool:
        return self.solde_eur is not None


@dataclass
class Journal:
    capital_depart_eur: float
    entrees: list[Entree] = field(default_factory=list)

    @property
    def etapes_franchies(self) -> set[str]:
        return {e.etape for e in self.entrees if e.etape}

    @property
    def derniere(self) -> Entree | None:
        return self.entrees[-1] if self.entrees else None

    @property
    def solde_actuel(self) -> float | None:
        for e in reversed(self.entrees):
            if e.a_un_solde:
                return e.solde_eur
        return None

    @property
    def variation_eur(self) -> float | None:
        solde = self.solde_actuel
        return None if solde is None else round(solde - self.capital_depart_eur, 2)

    @property
    def variation_pct(self) -> float | None:
        variation = self.variation_eur
        if variation is None or not self.capital_depart_eur:
            return None
        return round(variation / self.capital_depart_eur * 100, 1)

    @property
    def plus_bas_eur(self) -> float | None:
        soldes = [e.solde_eur for e in self.entrees if e.a_un_solde]
        return min(soldes) if soldes else None

    def resume_chiffre(self) -> str:
        """Une ligne de chiffres qui dit toujours la baisse, pas que la hausse."""
        solde = self.solde_actuel
        if solde is None:
            return ""
        bouts = [f"{solde:.2f} € sur le compte",
                 f"départ {self.capital_depart_eur:.0f} €",
                 f"soit {self.variation_pct:+.1f} %"]
        bas = self.plus_bas_eur
        if bas is not None and bas < self.capital_depart_eur:
            bouts.append(f"plus bas atteint {bas:.2f} €")
        return " · ".join(bouts)


def load_journal(path: Path | None = None) -> Journal | None:
    """Charge le journal. None si le projet n'a encore rien à raconter."""
    src = path or JOURNAL_PATH
    if not src.exists():
        return None
    try:
        data = json.loads(src.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise JournalError(f"{src} n'est pas un JSON valide : {exc}") from exc

    if "capital_depart_eur" not in data:
        raise JournalError(f"{src} : `capital_depart_eur` est obligatoire.")

    entrees: list[Entree] = []
    aujourdhui = date.today().isoformat()
    for i, brut in enumerate(data.get("entrees", [])):
        if not brut.get("date"):
            raise JournalError(f"{src} : entrée {i} sans date.")
        if brut["date"] > aujourdhui:
            raise JournalError(
                f"{src} : entrée datée du futur ({brut['date']}). "
                "Le récit ne peut pas devancer le projet réel.")
        solde = brut.get("solde_eur")
        entrees.append(Entree(date=str(brut["date"]), etape=str(brut.get("etape", "")),
                              solde_eur=None if solde is None else float(solde),
                              note=str(brut.get("note", ""))))

    entrees.sort(key=lambda e: e.date)
    return Journal(float(data["capital_depart_eur"]), entrees)


def episodes_disponibles(persona, journal: Journal | None) -> list[dict]:
    """Épisodes de l'arc réellement racontables aujourd'hui.

    Le premier (« pourquoi je m'y suis mise ») est toujours ouvert : il ne
    prétend à aucun résultat. Tous les autres exigent leur étape franchie.
    """
    arc = persona.raw().get("story", {}).get("arc", [])
    franchies = journal.etapes_franchies if journal else set()
    return [e for i, e in enumerate(arc) if i == 0 or e["key"] in franchies]


def prochaine_etape(persona, journal: Journal | None) -> dict | None:
    """La prochaine étape à franchir — ce que l'agent attend de toi."""
    arc = persona.raw().get("story", {}).get("arc", [])
    franchies = journal.etapes_franchies if journal else set()
    for i, etape in enumerate(arc):
        if i > 0 and etape["key"] not in franchies:
            return etape
    return None
