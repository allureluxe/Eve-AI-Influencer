"""Ponderation adaptative : le robot apprend ce qui marche chez lui.

Porte du robot « mega_scalper », dont la classe `AdaptiveWeights` etait
correctement ecrite — bornes, taille d'echantillon minimale, qualite
mesuree par un rapport rendement/volatilite. Un seul defaut, mais fatal :
`observe()` n'etait appele nulle part. Le cerveau existait, personne ne le
nourrissait, et il ne pouvait donc rien apprendre.

Ici il est branche sur le journal des trades fermes, qui est la seule
source de verite disponible : ce que le robot a REELLEMENT gagne ou perdu.

CE QU'IL APPREND, ET CE QU'IL NE TOUCHERA JAMAIS
------------------------------------------------
Il apprend une ponderation par famille de configuration. C'est tout.

Il ne modifie ni les stops, ni le risque par trade, ni les plafonds de
perte, ni le code d'execution. Un systeme qui ajuste seul son propre
risque a partir de ses bons resultats est un systeme qui augmente la mise
juste avant de rendre les gains. La ponderation est bornee entre un
plancher et un plafond pour la meme raison : meme convaincu, il ne peut
pas doubler la taille.

POURQUOI VINGT TRADES AVANT DE BOUGER
--------------------------------------
Sous vingt observations, l'ecart entre deux configurations n'est pas
distinguable du hasard. Ponderer sur cinq trades, c'est apprendre le
bruit — et le bruit d'un echantillon ne se reproduit pas. Le poids reste
donc neutre jusqu'a ce que l'echantillon dise quelque chose.
"""
from __future__ import annotations

import json
import logging
import math
import os
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Optional

logger = logging.getLogger(__name__)

MINIMUM_OBSERVATIONS = 20
PLANCHER = 0.70
PLAFOND = 1.30


@dataclass
class Statistiques:
    """Resultats observes pour une famille de configuration."""

    n: int = 0
    gagnants: int = 0
    somme: float = 0.0
    somme_carres: float = 0.0

    def observer(self, resultat_r: float) -> None:
        self.n += 1
        self.gagnants += int(resultat_r > 0)
        self.somme += resultat_r
        self.somme_carres += resultat_r * resultat_r

    @property
    def moyenne(self) -> float:
        return self.somme / self.n if self.n else 0.0

    @property
    def taux_reussite(self) -> float:
        return self.gagnants / self.n if self.n else 0.0

    @property
    def qualite(self) -> float:
        """Rendement moyen rapporte a sa propre volatilite.

        Deux configurations a +0,2 R de moyenne ne se valent pas si l'une
        y arrive regulierement et l'autre par un coup de chance au milieu
        de dix pertes. Diviser par l'ecart-type separe les deux.
        """
        if self.n < 2:
            return 0.0
        variance = max(1e-12, self.somme_carres / self.n - self.moyenne ** 2)
        return self.moyenne / math.sqrt(variance)


class PoidsAdaptatifs:
    """Ponderation bornee, apprise sur les trades reellement fermes."""

    def __init__(self, minimum: int = MINIMUM_OBSERVATIONS,
                 plancher: float = PLANCHER, plafond: float = PLAFOND) -> None:
        self.stats: dict[str, Statistiques] = defaultdict(Statistiques)
        self.minimum = max(1, minimum)
        self.plancher = plancher
        self.plafond = plafond

    def observer(self, famille: str, resultat_r: float) -> None:
        if not famille:
            return
        self.stats[famille].observer(float(resultat_r))

    def poids(self, famille: str) -> float:
        """Poids d'une famille : 1.0 tant qu'on ne sait pas.

        La tangente hyperbolique borne naturellement l'effet : meme une
        qualite excellente ne donne pas un poids infini, et une serie
        catastrophique ne descend pas sous le plancher. Le robot penche,
        il ne bascule pas.
        """
        s = self.stats.get(famille)
        if s is None or s.n < self.minimum:
            return 1.0
        ajustement = 0.30 * math.tanh(s.qualite * 3.0)
        return max(self.plancher, min(self.plafond, 1.0 + ajustement))

    def connue(self, famille: str) -> bool:
        s = self.stats.get(famille)
        return bool(s and s.n >= self.minimum)

    def rapport(self) -> list[dict]:
        """Etat lisible, trie du meilleur au pire."""
        lignes = [
            {
                "famille": nom,
                "trades": s.n,
                "reussite_pct": round(s.taux_reussite * 100, 1),
                "moyenne_r": round(s.moyenne, 3),
                "qualite": round(s.qualite, 3),
                "poids": round(self.poids(nom), 3),
                "actif": s.n >= self.minimum,
            }
            for nom, s in self.stats.items()
        ]
        lignes.sort(key=lambda l: (-l["qualite"], -l["trades"]))
        return lignes


def famille_du_trade(trade: dict) -> str:
    """Famille de configuration d'un trade, telle qu'inscrite au journal.

    On regroupe par motif d'entree quand il est disponible, sinon par
    raison de sortie : meme grossiere, une famille stable vaut mieux
    qu'une cle unique par trade, sur laquelle rien ne s'apprend.
    """
    for cle in ("setup", "strategie", "strategy", "comment"):
        valeur = trade.get(cle)
        if valeur:
            return str(valeur).split("|")[0].strip()[:40] or "inconnu"
    return "inconnu"


def alimenter_depuis_journal(
    poids: PoidsAdaptatifs,
    chemin: str,
    limite: Optional[int] = None,
) -> int:
    """Nourrit la ponderation avec les trades fermes du journal.

    C'est le chainon qui manquait au robot d'origine. Retourne le nombre
    de trades pris en compte.

    Les fermetures partielles sont ignorees : compter deux fois le meme
    trade parce qu'il est sorti en deux fois fausserait la taille de
    l'echantillon, donc la confiance accordee a la famille.
    """
    if not os.path.exists(chemin):
        logger.info("journal absent (%s) : ponderation neutre", chemin)
        return 0

    lignes: list[dict] = []
    try:
        with open(chemin, "r", encoding="utf-8") as fh:
            for ligne in fh:
                ligne = ligne.strip()
                if not ligne:
                    continue
                try:
                    trade = json.loads(ligne)
                except json.JSONDecodeError:
                    continue
                if isinstance(trade, dict) and not trade.get("partial"):
                    lignes.append(trade)
    except OSError as exc:
        logger.warning("journal illisible (%s) : %s", chemin, exc)
        return 0

    if limite:
        lignes = lignes[-limite:]

    retenus = 0
    for trade in lignes:
        r = trade.get("r_multiple")
        if r is None:
            continue
        try:
            poids.observer(famille_du_trade(trade), float(r))
            retenus += 1
        except (TypeError, ValueError):
            continue

    if retenus:
        actives = sum(1 for l in poids.rapport() if l["actif"])
        logger.info("ponderation alimentee : %d trades, %d famille(s) au-dessus "
                    "du seuil de %d observations", retenus, actives, poids.minimum)
    return retenus
