"""Lecture de la microstructure : carnet, flux, balayages de liquidite.

Ces trois lectures viennent d'un robot tiers (« mega_scalper ») dont le
code d'execution etait inutilisable, mais dont les idees de signaux
valaient d'etre reprises. Elles interrogent une famille d'information que
le reste de la strategie ignorait : non pas ou va le prix, mais QUI pousse.

Trois fonctions pures, sans reseau ni etat, donc entierement testables.

CE QUI EST BRANCHE, ET CE QUI NE L'EST PAS
------------------------------------------
`desequilibre_carnet` est aliment sans appel supplementaire : les tickers
de Bitvavo et d'OKX renvoient deja les tailles au meilleur prix dans la
reponse que le robot demande de toute facon.

`desequilibre_flux` exige la bande des transactions recentes, soit un
appel de plus par instrument — 85 appels par cycle. Il n'est donc PAS
branche au chemin de decision pour l'instant. La fonction est portee et
testee ; elle sera activee si le backtest montre qu'elle gagne plus
qu'elle ne coute. Un module non branche qu'on presente comme actif, c'est
exactement le defaut du robot d'ou vient cette idee.
"""
from __future__ import annotations

from typing import Iterable, Optional, Sequence

from .core import Candle


def desequilibre_carnet(taille_achat: float, taille_vente: float) -> float:
    """Desequilibre du carnet au meilleur prix, entre -1 et +1.

    +1 = il n'y a que des acheteurs, -1 = que des vendeurs, 0 = equilibre
    ou information absente. C'est une mesure de pression immediate : elle
    dit ce qui est POSE dans le carnet, pas ce qui a ete execute.
    """
    a = max(0.0, taille_achat or 0.0)
    v = max(0.0, taille_vente or 0.0)
    total = a + v
    return 0.0 if total <= 0 else (a - v) / total


def desequilibre_flux(echanges: Sequence[tuple], fenetre: int = 100) -> float:
    """Desequilibre du flux execute, entre -1 et +1.

    Chaque echange est un triplet (prix, quantite, sens) ou `sens` vaut
    « buy » ou « sell ». Contrairement au carnet, on mesure ici ce qui a
    REELLEMENT ete echange : un carnet peut etre garni d'ordres qu'on
    retire a la premiere alerte, un echange execute ne se retire pas.

    La sequence est copiee en liste avant decoupage : passer un `deque`
    directement leve un TypeError, et c'est precisement le defaut qui
    faisait planter le robot d'origine des le premier trade recu.
    """
    if not echanges:
        return 0.0
    derniers = list(echanges)[-max(1, fenetre):]
    achats = 0.0
    ventes = 0.0
    for ligne in derniers:
        try:
            _, quantite, sens = ligne[0], float(ligne[1]), str(ligne[2]).lower()
        except (IndexError, TypeError, ValueError):
            continue
        if quantite <= 0:
            continue
        if sens == "buy":
            achats += quantite
        elif sens == "sell":
            ventes += quantite
    total = achats + ventes
    return 0.0 if total <= 0 else (achats - ventes) / total


def balayage_de_liquidite(
    bougies: Sequence[Candle],
    atr: float,
    fenetre: int = 10,
    rejet_minimum: float = 0.35,
) -> tuple[int, float, str]:
    """Detecte un balayage de liquidite suivi d'un rejet.

    Le motif : le prix casse brievement l'extreme des dernieres bougies —
    declenchant les stops qui dormaient juste derriere — puis revient
    aussitot dans l'intervalle. Ce n'est pas une cassure, c'est une prise
    de liquidite, et elle part souvent dans le sens inverse.

    Retourne (sens, force, description) ou `sens` vaut +1 (balayage vers le
    bas, donc signal haussier), -1 (l'inverse) ou 0 (rien).

    `force` est la profondeur du rejet rapportee a l'ATR : un retour de
    moins de `rejet_minimum` ATR n'est pas un rejet, c'est du bruit.
    """
    if atr <= 0 or len(bougies) < fenetre + 2:
        return 0, 0.0, "historique insuffisant"

    reference = list(bougies)[-(fenetre + 2):-2]
    if not reference:
        return 0, 0.0, "historique insuffisant"
    sommet = max(c.high for c in reference)
    creux = min(c.low for c in reference)

    balayeuse = bougies[-2]
    actuelle = bougies[-1]

    # Balayage vers le BAS : la meche passe sous le creux, la cloture
    # revient au-dessus, et la bougie suivante confirme la reprise.
    if balayeuse.low < creux and balayeuse.close > creux and actuelle.close > balayeuse.close:
        force = (balayeuse.close - balayeuse.low) / atr
        if force >= rejet_minimum:
            return 1, round(force, 3), (
                f"balayage du creux {creux:.6g}, rejet de {force:.2f} ATR")

    # Balayage vers le HAUT : symetrique.
    if balayeuse.high > sommet and balayeuse.close < sommet and actuelle.close < balayeuse.close:
        force = (balayeuse.high - balayeuse.close) / atr
        if force >= rejet_minimum:
            return -1, round(force, 3), (
                f"balayage du sommet {sommet:.6g}, rejet de {force:.2f} ATR")

    return 0, 0.0, "pas de balayage"
