"""Decrire la methode du robot EN LA LISANT, jamais en la recopiant.

Ce module existe a cause d'une erreur precise. Jusqu'au 19 septembre, la
phrase affichee dans l'application etait ecrite en dur. Elle a menti
pendant une semaine : elle annoncait « canal a 20 jours » et
« pyramidage jusqu'a 3 etages » alors que le robot tournait a 10 jours
et en pyramidage illimite depuis le 12 septembre. C'est l'operateur qui
l'a releve — « il me semble qu'on avait modifie la methode ? ».

Un texte qui decrit un reglage sans le LIRE finit toujours par decrire
autre chose que ce qui tourne.

Deux longueurs, une seule source :

    phrase_methode(cfg)   la description complete, pour une fiche
    resume_methode(cfg)   trois mots, pour un onglet

Les deux se deduisent du fichier de configuration reellement charge.
Elles vivent ICI, et pas dans `ops/`, parce que le robot lui-meme doit
pouvoir publier sa propre methode au demarrage — deux comptes de
simulation tournent desormais en parallele, et chacun doit dire ce qu'il
fait.
"""
from __future__ import annotations

from .croissance import PALIERS
from .settings import BotConfig


def _mot_pyramide(etages: int) -> str:
    if etages >= 99:
        return "pyramidage Turtle illimite"
    if etages <= 0:
        return "sans pyramidage"
    return f"pyramidage Turtle jusqu'a {etages} etages"


def phrase_methode(cfg: BotConfig) -> str:
    """La description complete, telle que l'application l'affiche."""
    canal = min(cfg.strategy.donchian_entrees or [20])
    pyramide = _mot_pyramide(cfg.risk.pyramide_max)
    jours_stop = (cfg.trade.time_stop_minutes or 0) / 1440.0
    trail = f"{cfg.trade.trail_atr_mult:.1f}".replace(".", ",")

    paliers = ", ".join(
        f"{p.risque_pct:.1f} % ".replace(".", ",")
        + (f"au palier {p.nom}" if p.trades_minimum <= 0 else
           f"a partir de {p.trades_minimum} trades et d'une esperance nette "
           f">= {p.esperance_minimale:+.2f} R".replace(".", ","))
        for p in PALIERS)

    return (
        f"Strategie {cfg.strategy.entry_tf} {cfg.strategy.famille.capitalize()}-{canal} "
        f"(cassure de canal a {canal} jours), {pyramide}, stop suiveur a "
        f"{trail} ATR, stop temporel de {jours_stop:.0f} jours. "
        f"Le risque par trade suit le palier atteint : {paliers}."
    )


def resume_methode(cfg: BotConfig) -> str:
    """Trois mots pour un onglet. En francais courant, sans jargon.

    L'operateur lit ce texte sur un bouton de quelques centimetres : il
    doit distinguer deux comptes d'un coup d'oeil, pas decrire la
    strategie. On ne garde donc que ce qui DIFFERE en pratique entre
    deux simulations — le canal, le pyramidage, la reserve.
    """
    canal = min(cfg.strategy.donchian_entrees or [20])
    morceaux = [f"Canal {canal} j"]

    etages = cfg.risk.pyramide_max
    if etages >= 99:
        morceaux.append("pyramide illimitée")
    elif etages <= 0:
        morceaux.append("sans pyramide")
    else:
        morceaux.append(f"pyramide {etages}")

    reserve = float(getattr(cfg.risk, "reserve_pyramide_pct", 0.0) or 0.0)
    total = float(cfg.risk.max_total_risk_pct or 0.0)
    if reserve > 0 and total > 0:
        part = reserve / total
        # « un tiers » se lit mieux que « 1,67 % sur 5 % ».
        if abs(part - 1 / 3) < 0.03:
            morceaux.append("⅓ réservé aux renforts")
        elif abs(part - 0.25) < 0.03:
            morceaux.append("¼ réservé aux renforts")
        elif abs(part - 0.5) < 0.03:
            morceaux.append("½ réservé aux renforts")
        else:
            morceaux.append(f"{reserve:.2f} % réservé".replace(".", ","))
    else:
        morceaux.append("rien de réservé")

    # LE POINT MORT DOIT FIGURER, SINON DEUX COMPTES SE RESSEMBLENT.
    #
    # Constate le 20 sept. : les comptes 1 et 3 ne different QUE par ce
    # reglage, et leurs deux onglets affichaient exactement la meme
    # phrase. Un selecteur qui ne distingue pas ce qu'il selectionne ne
    # sert a rien.
    #
    # Dit en francais courant : c'est le moment ou la position ne peut
    # plus rien coûter. Jamais « breakeven », jamais « R » -- l'operateur
    # ne connait pas ce vocabulaire, et un mot qu'il ne comprend pas le
    # fait douter du reste.
    protection = float(getattr(cfg.trade, "breakeven_at_r", 0.0) or 0.0)
    if protection > 0:
        morceaux.append(f"à l'abri dès {protection:.1f}× le risque"
                        .replace(".", ","))

    return " · ".join(morceaux)
