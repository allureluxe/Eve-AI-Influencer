"""Réglages de jeu pour la voix off.

Leçon apprise en écoutant les essais : **plus on dirige, plus c'est joué.**
Demander « voix jeune et énergique » produit une imitation de jeunesse, pas
une jeune femme. Les rendus les plus crédibles viennent de consignes qui
demandent de *ne rien faire* — ton neutre, aucune intention ajoutée.

Le naturel vient du texte, pas de la performance : c'est l'écriture parlée
(phrases courtes, reprises, mots avalés) qui porte le réalisme.
"""
from __future__ import annotations

PRESETS: dict[str, str] = {
    # Défaut. Le moins dirigé, donc le plus crédible.
    "neutre": (
        "Ne joue pas. Lis à voix normale, comme si tu relisais un message que "
        "tu viens d'écrire. Ton neutre, sans intention particulière, sans "
        "énergie ajoutée. N'accentue aucun mot, ne fais aucune intonation "
        "expressive, ne souris pas dans la voix."),

    # Aucune consigne du tout : le modèle lit brut. À essayer en premier si
    # « neutre » sonne encore joué.
    "aucun": "",

    "confidence": (
        "Parle à voix basse, près du micro, sans projeter. Comme si quelqu'un "
        "dormait dans la pièce d'à côté. Ne joue rien, n'accentue rien."),

    "whatsapp": (
        "Comme un message vocal envoyé à une amie, enregistré en marchant. "
        "Débit irrégulier, quelques mots avalés. Tu ne lis pas, tu parles. "
        "Aucune intention de bien dire."),

    "fatigue": (
        "Voix basse et relâchée, fin de journée. Aucun effort de diction, "
        "aucune énergie. Tu parles parce qu'on te l'a demandé."),

    "sud": (
        "Ne joue pas, ton neutre. Léger accent du sud de la France, naturel, "
        "sans exagération et sans chanter."),
}

DEFAUT = "neutre"


def resolve(preset: str = "", style_libre: str = "") -> str:
    """Consigne finale envoyée au moteur vocal.

    Un style libre écrit à la main l'emporte sur le preset ; sinon on prend
    le preset demandé, et à défaut le défaut. Un preset inconnu ne casse
    rien : on retombe sur le défaut.
    """
    if style_libre.strip():
        return style_libre.strip()
    return PRESETS.get((preset or DEFAUT).strip().lower(), PRESETS[DEFAUT])
