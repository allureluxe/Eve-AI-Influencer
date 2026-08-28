"""Combien de positions le robot peut-il tenir en meme temps ?

POURQUOI CE CALCUL EXISTE

« Il prend peu de positions a mon gout ; sur une journee il y a enormement
d'opportunites avec 70 instruments, donc il y a un truc qui va pas. »

L'observation est juste et la cause est verifiable. Trois reglages
plafonnent le nombre de positions simultanees, independamment l'un de
l'autre :

    max_positions            le plafond direct
    groupes correles         max_per_correlation_group x nombre de groupes
    budget de risque         max_total_risk_pct / risque par trade
    capital                  ce que le ticket minimum de la plateforme
                             laisse tenir (calcul deja fait par
                             `engine.positions_tenables`, passe ici pour
                             que la reponse reste unique)

Le nombre de places reellement disponibles est le PLUS PETIT des quatre.
D'ou le piege : desserrer `max_positions` alors que le budget de risque
plafonne au meme endroit ne change strictement rien, et donne l'impression
que le reglage est casse alors qu'il est simplement masque.

Ce module donne les quatre chiffres et nomme celui — ou ceux — qui brident.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Capacite:
    places: int                       # ce que le robot peut tenir
    limites: dict[str, int] = field(default_factory=dict)
    bride_par: list[str] = field(default_factory=list)

    @property
    def plusieurs_verrous(self) -> bool:
        """Vrai si desserrer un seul reglage ne changerait rien."""
        return len(self.bride_par) > 1


AUCUN_PLAFOND = 999


def places_simultanees(max_positions: int, max_par_groupe: int,
                       n_groupes: int, max_risque_total_pct: float,
                       risque_par_trade_pct: float,
                       places_par_capital: int = 0) -> Capacite:
    """Les plafonds, et lequel serre le plus.

    `places_par_capital` vient de `engine.positions_tenables` : ce que le
    ticket minimum de la plateforme laisse reellement tenir. Il est passe
    en parametre plutot que recalcule, pour qu'il n'existe qu'UNE reponse
    a cette question dans le projet. 0 = non renseigne, on l'ignore.

    `risque_par_trade_pct` est le risque REELLEMENT applique — echelle
    anti-martingale comprise. Prendre `base_risk_pct` a la place ferait
    croire a plus de places qu'il n'y en a apres une semaine perdante,
    exactement au moment ou l'ecart compte.
    """
    limites: dict[str, int] = {}

    # 0 ou moins = aucun plafond, meme convention que le reste du projet.
    limites["max_positions"] = max_positions if max_positions > 0 else AUCUN_PLAFOND

    if n_groupes > 0 and max_par_groupe > 0:
        limites["groupes correles"] = n_groupes * max_par_groupe
    else:
        limites["groupes correles"] = AUCUN_PLAFOND

    if risque_par_trade_pct > 0:
        limites["budget de risque"] = int(max_risque_total_pct // risque_par_trade_pct)
    else:
        limites["budget de risque"] = AUCUN_PLAFOND

    if places_par_capital > 0:
        limites["capital"] = places_par_capital

    places = min(limites.values())
    bride = [nom for nom, v in limites.items() if v == places]
    return Capacite(places=places, limites=limites, bride_par=bride)
