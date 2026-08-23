"""Fenetre promotionnelle sans commission, a expiration automatique.

Bitvavo offre parfois un volume sans frais sur une periode courte. Cela
change reellement ce que la strategie peut viser : sans commission, le
cout d'un aller-retour tombe de 0,60 % a 0,10 % — il ne reste que le
spread et le glissement — et le M15 redevient praticable la ou seul le D1
tenait.

CE MODULE EXISTE POUR UNE SEULE RAISON : L'EXPIRATION
------------------------------------------------------
Le lendemain de la fin, un trade M15 coute 78 % du risque. Un robot qui
continuerait sur la configuration promotionnelle viderait le compte en
quelques jours, sans erreur ni alerte — chaque trade serait simplement
perdant d'avance.

Compter sur quelqu'un pour changer un reglage a une date donnee n'est pas
une strategie. La fenetre porte donc sa propre fin, le robot la verifie a
chaque cycle, et revient tout seul au regime normal. Oublier de le faire
devient impossible.

Le plafond de volume est suivi de la meme facon : une promotion se termine
par la date OU par le volume, selon ce qui arrive en premier.
"""
from __future__ import annotations

import datetime as _dt
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class Promotion:
    """Une periode sans commission, bornee par une date et un volume."""

    active: bool = False
    fin: str = ""                      # date incluse, format AAAA-MM-JJ
    volume_plafond: float = 0.0        # 0 = pas de plafond
    volume_consomme: float = 0.0

    @classmethod
    def depuis_config(cls, brut: Optional[dict]) -> "Promotion":
        if not isinstance(brut, dict):
            return cls()
        return cls(
            active=bool(brut.get("active", False)),
            fin=str(brut.get("sans_frais_jusqu_au", "") or ""),
            volume_plafond=float(brut.get("volume_plafond", 0) or 0),
        )

    def jours_restants(self, aujourd_hui: Optional[_dt.date] = None) -> int:
        """Nombre de jours avant la fin, le dernier jour compte pour 1."""
        if not self.fin:
            return 0
        try:
            fin = _dt.date.fromisoformat(self.fin)
        except ValueError:
            logger.warning("date de fin de promotion illisible : %r", self.fin)
            return 0
        return (fin - (aujourd_hui or _dt.date.today())).days + 1

    def volume_restant(self) -> float:
        if self.volume_plafond <= 0:
            return float("inf")
        return max(0.0, self.volume_plafond - self.volume_consomme)

    def en_cours(self, aujourd_hui: Optional[_dt.date] = None) -> bool:
        """La fenetre est-elle encore ouverte, en date ET en volume ?

        Les deux conditions doivent tenir. Une promotion se termine par ce
        qui arrive en premier, et se tromper de cote coute cher : croire la
        fenetre ouverte alors qu'elle est fermee fait trader a perte
        garantie.
        """
        if not self.active:
            return False
        return self.jours_restants(aujourd_hui) > 0 and self.volume_restant() > 0

    def frais_effectifs(self, frais_reels: float,
                        aujourd_hui: Optional[_dt.date] = None) -> float:
        """Commission a retenir pour le calibrage."""
        return 0.0 if self.en_cours(aujourd_hui) else frais_reels

    def consommer(self, notionnel: float) -> None:
        """Enregistre le volume d'un ordre passe."""
        if self.active and notionnel > 0:
            self.volume_consomme += notionnel

    def resume(self, aujourd_hui: Optional[_dt.date] = None) -> str:
        if not self.active:
            return "aucune promotion declaree"
        if not self.en_cours(aujourd_hui):
            jours = self.jours_restants(aujourd_hui)
            motif = "date depassee" if jours <= 0 else "volume epuise"
            return f"promotion terminee ({motif}) — tarif normal applique"
        restant = self.volume_restant()
        volume = "sans plafond" if restant == float("inf") else f"{restant:.0f} de volume restant"
        return (f"SANS FRAIS jusqu'au {self.fin} inclus "
                f"({self.jours_restants(aujourd_hui)} jour(s), {volume})")
