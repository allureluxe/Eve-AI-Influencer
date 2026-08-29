"""Plan de croissance du capital, adosse a l'esperance REELLEMENT mesuree.

POURQUOI CE MODULE EXISTE
-------------------------
« Aller vite a 3 000 EUR » n'est pas un reglage : c'est une duree, et cette
duree est entierement determinee par trois nombres — le risque par trade,
l'esperance en R, et le nombre de trades par jour. Les trois se mesurent.
Aucun ne se decide.

    croissance par trade = risque_pct x esperance_R
    jours = ln(cible / capital) / (trades_par_jour x ln(1 + croissance))

La consequence est brutale et vaut d'etre ecrite : **si l'esperance est
negative, augmenter le risque ou le nombre de trades ne fait qu'atteindre
zero plus vite.** Le levier, la cadence et la taille amplifient le signe de
l'esperance ; ils ne le changent pas.

D'ou la regle qui structure les paliers ci-dessous : le risque ne monte
qu'apres qu'un echantillon SUFFISANT ait montre une esperance positive.
Un compte de 186 EUR qui vise 3 000 EUR n'a pas besoin d'aller vite : il a
besoin de ne pas mourir avant d'avoir prouve qu'il gagne.

Le 28 aout, 72 trades ont donne 2,8 % de reussite et -0,406 R d'esperance.
A ce chiffre, doubler le risque aurait divise le temps de survie par deux.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

# Nombre de trades en dessous duquel une esperance ne veut rien dire.
# 30 trades a 50 % de reussite ont un ecart-type de ~9 points : une serie
# chanceuse peut afficher 60 % sans qu'aucun avantage n'existe.
ECHANTILLON_MINIMAL = 40


@dataclass(frozen=True)
class Palier:
    """Un cran du plan : ce qu'il autorise, et ce qu'il exige pour y entrer."""

    nom: str
    risque_pct: float             # risque par trade autorise a ce palier
    trades_minimum: int           # echantillon exige pour ENTRER dans ce palier
    esperance_minimale: float     # esperance en R exigee pour y entrer
    capital_minimum: float = 0.0  # capital exige en plus, si pertinent
    commentaire: str = ""


# Les paliers. Chacun demande PLUS de preuve que le precedent, parce que
# chacun autorise plus de risque. Le premier n'exige rien : il faut bien
# commencer, et c'est lui qui produit l'echantillon.
PALIERS: tuple[Palier, ...] = (
    Palier("preuve", 0.60, 0, -math.inf,
           commentaire="produire un echantillon ; l'objectif n'est pas de "
                       "gagner vite mais de savoir si on gagne"),
    Palier("croissance", 1.00, ECHANTILLON_MINIMAL, 0.05,
           commentaire="esperance positive etablie sur un echantillon reel"),
    Palier("acceleration", 1.50, 150, 0.15,
           commentaire="avantage confirme ; 1,5 % est le plafond dur du robot"),
)


@dataclass
class Diagnostic:
    """Ou en est le compte, et ce qui le retient."""

    capital: float
    cible: float
    trades: int
    esperance_r: float
    taux_reussite_pct: float
    trades_par_jour: float
    palier: Palier
    palier_suivant: Optional[Palier]
    manques: list[str] = field(default_factory=list)

    @property
    def croissance_par_trade(self) -> float:
        """Fraction du capital gagnee en moyenne par trade."""
        return self.risque_effectif() / 100.0 * self.esperance_r

    def risque_effectif(self) -> float:
        return self.palier.risque_pct

    def jours_jusqu_a_la_cible(self) -> Optional[float]:
        """None quand la cible est hors d'atteinte a ce rythme.

        Une esperance nulle ou negative ne rend pas le calcul « long » :
        elle le rend impossible. Retourner un grand nombre laisserait
        croire qu'il suffit d'attendre.
        """
        if self.capital <= 0 or self.cible <= self.capital:
            return 0.0
        g = self.croissance_par_trade
        if g <= 0 or self.trades_par_jour <= 0:
            return None
        return math.log(self.cible / self.capital) / (
            self.trades_par_jour * math.log(1.0 + g))

    def echantillon_suffisant(self) -> bool:
        return self.trades >= ECHANTILLON_MINIMAL

    def esperance_fiable(self) -> bool:
        """L'esperance mesuree est-elle distinguable du hasard ?

        Test grossier mais honnete : l'erreur type de la moyenne des R.
        Avec un ecart-type de ~1 R par trade — ordre de grandeur usuel
        quand le stop vaut 1 R — l'incertitude vaut 1/sqrt(n). On exige
        que l'esperance depasse deux fois cette incertitude.
        """
        if self.trades < ECHANTILLON_MINIMAL:
            return False
        incertitude = 1.0 / math.sqrt(self.trades)
        return self.esperance_r > 2.0 * incertitude


def palier_courant(trades: int, esperance_r: float, capital: float) -> Palier:
    """Le palier le plus haut dont TOUTES les conditions sont remplies."""
    retenu = PALIERS[0]
    for p in PALIERS:
        if (trades >= p.trades_minimum
                and esperance_r >= p.esperance_minimale
                and capital >= p.capital_minimum):
            retenu = p
    return retenu


def palier_suivant(courant: Palier) -> Optional[Palier]:
    for i, p in enumerate(PALIERS):
        if p.nom == courant.nom:
            return PALIERS[i + 1] if i + 1 < len(PALIERS) else None
    return None


def ce_qui_manque(suivant: Optional[Palier], trades: int,
                  esperance_r: float, capital: float) -> list[str]:
    """Les conditions non encore remplies pour monter d'un cran."""
    if suivant is None:
        return []
    manques = []
    if trades < suivant.trades_minimum:
        manques.append(f"{suivant.trades_minimum - trades} trade(s) de plus "
                       f"({trades}/{suivant.trades_minimum})")
    if esperance_r < suivant.esperance_minimale:
        manques.append(f"esperance a {esperance_r:+.3f} R, il en faut "
                       f"{suivant.esperance_minimale:+.2f}")
    if capital < suivant.capital_minimum:
        manques.append(f"capital a {capital:.0f} EUR, il en faut "
                       f"{suivant.capital_minimum:.0f}")
    return manques


def diagnostiquer(capital: float, cible: float, stats: dict,
                  trades_par_jour: float) -> Diagnostic:
    """Assemble le diagnostic a partir des statistiques du journal reel."""
    trades = int(stats.get("trades", 0) or 0)
    esperance = float(stats.get("esperance_R", 0.0) or 0.0)
    reussite = float(stats.get("taux_reussite_pct", 0.0) or 0.0)
    courant = palier_courant(trades, esperance, capital)
    suivant = palier_suivant(courant)
    return Diagnostic(
        capital=capital, cible=cible, trades=trades,
        esperance_r=esperance, taux_reussite_pct=reussite,
        trades_par_jour=trades_par_jour,
        palier=courant, palier_suivant=suivant,
        manques=ce_qui_manque(suivant, trades, esperance, capital),
    )


def projeter(capital: float, cible: float, risque_pct: float,
             esperance_r: float, trades_par_jour: float) -> Optional[float]:
    """Jours necessaires pour aller de `capital` a `cible`. None si impossible."""
    d = Diagnostic(capital=capital, cible=cible, trades=0,
                   esperance_r=esperance_r, taux_reussite_pct=0.0,
                   trades_par_jour=trades_par_jour,
                   palier=Palier("hypothese", risque_pct, 0, -math.inf),
                   palier_suivant=None)
    return d.jours_jusqu_a_la_cible()


def drawdown_probable(risque_pct: float, taux_reussite_pct: float,
                      trades: int = 200) -> dict:
    """Ce que coute une serie noire, qui arrive toujours.

    La plus longue serie de pertes attendue sur n trades vaut environ
    ln(n) / -ln(1-p) avec p la probabilite de perdre. Ce n'est pas un
    scenario pessimiste : c'est la valeur CENTRALE. La moitie du temps,
    ce sera pire.
    """
    p_perte = max(1e-9, min(1 - 1e-9, 1.0 - taux_reussite_pct / 100.0))
    serie = math.log(max(trades, 2)) / -math.log(p_perte)
    perte = 1.0 - (1.0 - risque_pct / 100.0) ** serie
    return {"serie_attendue": round(serie, 1),
            "perte_pct": round(perte * 100.0, 1)}
