"""Le capital decide de ce que la strategie peut faire.

Principe pose dans V8_ARCHITECTURE.md : « No fixed 220 EUR assumption is
embedded in the engine ». Rien ici ne suppose un capital particulier — on
en deduit ce qui est possible.

DEUX MURS ENSERRENT LE STOP, PAR LE HAUT ET PAR LE BAS
-------------------------------------------------------
Un stop trop SERRE se fait manger par les frais :

    frais aller-retour / stop >= plafond acceptable  ->  refuse

    stop minimum = 2 x frais / plafond_cout

Un stop trop LARGE rend la position trop petite pour la plateforme. La
taille d'une position vaut risque_en_euros / distance_du_stop : plus le
stop s'elargit, plus la position retrecit, et sous le ticket minimum
l'ordre est refuse.

    stop maximum = (capital x risque_pct) / ticket_minimum

Entre les deux se trouve la fenetre des stops praticables. Elle peut etre
VIDE — et c'est une information capitale, pas une erreur : cela signifie
qu'a ce capital, sur cette plateforme, aucune unite de temps ne tient.

CE QUE LE CALIBRAGE AJUSTE, ET CE QU'IL NE TOUCHE PAS
------------------------------------------------------
Il peut REMONTER le risque par trade, dans la limite fixee par
l'utilisateur, quand c'est le seul moyen d'atteindre le ticket minimum.

Ce n'est pas la meme chose que la ponderation adaptative : celle-la
apprend des RESULTATS, et un robot qui augmente sa mise parce qu'il vient
de gagner se ruine. Ici on deduit d'une CONTRAINTE arithmetique connue
d'avance — le ticket minimum de la plateforme — et le plafond reste celui
que l'utilisateur a ecrit dans sa configuration.

Si meme au risque maximum la fenetre reste vide, le calibrage ne force
rien : il annonce le capital qu'il faudrait, et le robot ne trade pas.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Amplitude typique d'un stop, en fraction du prix, par unite de temps.
# Ces valeurs viennent des tableaux de frais des configurations livrees.
# Elles servent a preselectionner : la distance reelle reste calculee sur
# l'ATR de l'instrument au moment du trade.
STOP_TYPIQUE = {
    "M1": 0.0013, "M3": 0.0022, "M5": 0.0042, "M15": 0.0077,
    "M30": 0.0110, "H1": 0.0154, "H4": 0.0308, "D1": 0.0600,
}

# Ce qu'un aller-retour coute MEME sans commission : le spread, franchi
# une fois, et le glissement, subi des deux cotes. Aucune promotion ne
# l'annule — il est paye au marche, pas a la plateforme.
COUT_INCOMPRESSIBLE = 0.0010      # 10 points de base

ORDRE_UNITES = ["M1", "M3", "M5", "M15", "M30", "H1", "H4", "D1"]


@dataclass
class Calibrage:
    """Ce que ce capital permet, sur cette plateforme."""

    equity: float
    ticket_minimum: float
    frais_par_cote: float
    risk_pct: float                     # risque par trade finalement retenu
    risk_pct_demande: float             # celui de la configuration
    positions: int
    stop_min_pct: float
    stop_max_pct: float
    unites: list[str] = field(default_factory=list)
    viable: bool = False
    capital_minimum: float = 0.0
    explication: str = ""

    @property
    def unite_conseillee(self) -> str:
        """La plus rapide des unites praticables.

        La plus rapide, car a cout acceptable elle offre le plus
        d'occasions. Les unites plus lentes restent disponibles si le
        marche l'exige.
        """
        return self.unites[0] if self.unites else ""

    def resume(self) -> list[str]:
        lignes = [
            f"capital {self.equity:.2f} | ticket minimum {self.ticket_minimum:.2f} "
            f"| frais {self.frais_par_cote * 100:.3f} % par cote"
            + (" (SANS COMMISSION — spread et glissement restent dus)"
               if self.frais_par_cote <= 0 else ""),
            f"stop praticable entre {self.stop_min_pct * 100:.2f} % "
            f"et {self.stop_max_pct * 100:.2f} % du prix",
        ]
        if self.risk_pct != self.risk_pct_demande:
            # risk_pct et risk_pct_demande sont DEJA en pourcentage.
            lignes.append(
                f"risque par trade remonte de {self.risk_pct_demande:.3f} % "
                f"a {self.risk_pct:.3f} % pour atteindre le ticket minimum")
        if self.viable:
            lignes.append(f"unites praticables : {', '.join(self.unites)} "
                          f"-> conseillee {self.unite_conseillee}")
            lignes.append(f"positions simultanees tenables : {self.positions}")
        else:
            lignes.append(f"AUCUNE unite praticable — {self.explication}")
        return lignes


def calibrer(
    equity: float,
    ticket_minimum: float,
    frais_par_cote: float,
    risk_pct_demande: float,
    risk_pct_max: float,
    plafond_cout_pct: float = 15.0,
    plafond_positions: int = 6,
    part_engageable_pct: float = 80.0,
    cout_incompressible: float = COUT_INCOMPRESSIBLE,
) -> Calibrage:
    """Deduit du capital ce que la strategie peut viser.

    `risk_pct_demande` et `risk_pct_max` sont en pourcentage (0.22 = 0,22 %).
    """
    equity = max(0.0, equity)
    ticket_minimum = max(0.0, ticket_minimum)
    plafond_cout = max(1e-9, plafond_cout_pct / 100.0)
    demande = max(0.0, risk_pct_demande) / 100.0
    maximum = max(demande, max(0.0, risk_pct_max) / 100.0)

    # Mur du bas : en dessous, le COUT TOTAL mange le trade.
    #
    # Ne compter que la commission serait une erreur grave quand elle vaut
    # zero : le calibrage declarerait le M1 praticable alors que le spread
    # et le glissement lui coutent encore 77 % du risque. « Sans frais »
    # ne veut pas dire « sans cout » — c'est precisement pendant une
    # promotion que la distinction devient dangereuse.
    cout_total = 2.0 * max(0.0, frais_par_cote) + max(0.0, cout_incompressible)
    stop_min = cout_total / plafond_cout

    def stop_max_pour(risque: float) -> float:
        # Un capital nul n'ouvre aucune fenetre : sans argent, aucune
        # position n'atteint le ticket minimum, quel que soit le stop.
        if equity <= 0:
            return 0.0
        if ticket_minimum <= 0:
            return float("inf")      # pas de ticket minimum = pas de mur haut
        return (equity * risque) / ticket_minimum

    risque = demande
    stop_max = stop_max_pour(risque)

    # Unite de temps la moins lente que les frais autorisent. C'est elle
    # qu'il faut pouvoir atteindre : viser la frontiere theorique `stop_min`
    # ouvrirait une fenetre de largeur nulle, ou aucune unite ne rentre.
    atteignables = sorted(v for v in STOP_TYPIQUE.values() if v >= stop_min)
    cible = atteignables[0] if atteignables else stop_min

    # On remonte le risque des que la cible est hors de portee — que la
    # fenetre soit vide OU simplement trop basse pour contenir une unite
    # reelle. Les deux cas ont la meme cause : la position n'atteindrait
    # pas le ticket minimum.
    if stop_max < cible and equity > 0 and ticket_minimum > 0:
        requis = (cible * ticket_minimum) / equity
        risque = min(max(demande, requis), maximum)
        stop_max = stop_max_pour(risque)

    unites = [tf for tf in ORDRE_UNITES
              if stop_min <= STOP_TYPIQUE[tf] <= stop_max]

    cal = Calibrage(
        equity=equity, ticket_minimum=ticket_minimum,
        frais_par_cote=frais_par_cote,
        risk_pct=round(risque * 100, 4),
        risk_pct_demande=round(demande * 100, 4),
        positions=0,
        stop_min_pct=stop_min, stop_max_pct=stop_max,
        unites=unites, viable=bool(unites),
    )

    if not unites:
        if equity <= 0:
            cal.explication = "capital nul : aucune position possible"
            return cal

        # Capital qu'il faudrait, au risque maximum autorise, pour que la
        # premiere unite praticable rentre dans la fenetre.
        if maximum > 0 and ticket_minimum > 0 and atteignables:
            cal.capital_minimum = round((cible * ticket_minimum) / maximum, 2)

        cal.explication = (
            f"le ticket minimum de {ticket_minimum:.2f} limite les stops a "
            f"{stop_max * 100:.2f} %, alors que les frais en exigent au moins "
            f"{stop_min * 100:.2f} % et que la premiere unite praticable en "
            f"demande {cible * 100:.2f} %.")
        if cal.capital_minimum:
            cal.explication += (f" Il faudrait environ {cal.capital_minimum:.0f} "
                                f"de capital, ou des frais plus bas.")
        return cal

    from .engine import positions_tenables
    cal.positions, _ = positions_tenables(
        equity, ticket_minimum, part_engageable_pct, plafond_positions)
    return cal
