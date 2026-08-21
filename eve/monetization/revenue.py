"""Suivi des revenus et projection prudente.

Aucune promesse : le module part des chiffres réellement saisis et applique
des fourchettes publiques (RPM plateformes, taux de conversion moyens).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

# Fourchettes observées publiquement, volontairement basses.
RPM_RANGE = {           # $ pour 1000 vues
    "tiktok_rewards": (0.40, 1.00),   # Creator Rewards, vidéos > 1 min, marchés éligibles
    "instagram_bonus": (0.00, 0.50),  # programmes de bonus, disponibilité variable
}
# Entonnoir réel : une vue ne devient pas un achat. On enchaîne trois taux.
LINK_CTR = (0.002, 0.006)        # part des vues qui cliquent sur le lien en bio
AFFILIATE_PURCHASE = (0.02, 0.05)  # part des clics qui achètent chez le marchand
AFFILIATE_COMMISSION = (1.5, 4.0)  # $ de commission par vente
PRODUCT_PURCHASE = (0.01, 0.02)    # part des clics qui achètent le programme


@dataclass
class RevenueEntry:
    day: str
    source: str          # affiliate | product | sponsorship | platform | tip
    amount_usd: float
    note: str = ""


def project_monthly(followers: int, monthly_views: int,
                    avg_order_usd: float = 19.0) -> dict[str, tuple[float, float]]:
    """Fourchette basse/haute de revenu mensuel, par source."""
    platform_low = monthly_views / 1000 * RPM_RANGE["tiktok_rewards"][0]
    platform_high = monthly_views / 1000 * (RPM_RANGE["tiktok_rewards"][1]
                                            + RPM_RANGE["instagram_bonus"][1])
    affiliate_low = (monthly_views * LINK_CTR[0] * AFFILIATE_PURCHASE[0]
                     * AFFILIATE_COMMISSION[0])
    affiliate_high = (monthly_views * LINK_CTR[1] * AFFILIATE_PURCHASE[1]
                      * AFFILIATE_COMMISSION[1])
    product_low = monthly_views * LINK_CTR[0] * PRODUCT_PURCHASE[0] * avg_order_usd
    product_high = monthly_views * LINK_CTR[1] * PRODUCT_PURCHASE[1] * avg_order_usd
    # Tarif sponsoring usuel : 1 à 2 % du nombre d'abonnés, par publication.
    sponsor_low = followers * 0.01 if followers >= 5000 else 0.0
    sponsor_high = followers * 0.02 * 2 if followers >= 5000 else 0.0

    return {
        "plateformes": (round(platform_low, 2), round(platform_high, 2)),
        "affiliation": (round(affiliate_low, 2), round(affiliate_high, 2)),
        "produits": (round(product_low, 2), round(product_high, 2)),
        "sponsoring": (round(sponsor_low, 2), round(sponsor_high, 2)),
    }


def summarize(entries: list[RevenueEntry]) -> dict[str, float]:
    out: dict[str, float] = {}
    for e in entries:
        out[e.source] = round(out.get(e.source, 0.0) + e.amount_usd, 2)
    out["total"] = round(sum(out.values()), 2)
    return out


def milestones(followers: int) -> list[str]:
    """Prochains paliers concrets, avec la condition d'éligibilité connue."""
    steps = [
        (1000, "TikTok : 1 000 abonnés → LIVE et fonctionnalités créateur."),
        (5000, "Premiers partenariats rémunérés réalistes (produits offerts + petit cachet)."),
        (10000, "TikTok Creator Rewards : 10 000 abonnés + 100 000 vues sur 30 jours, "
                "vidéos de plus d'une minute, marché éligible."),
        (10000, "Instagram : liens en story et crédibilité pour les marques."),
        (25000, "Tarif sponsoring typique : 250 à 500 $ par publication."),
        (100000, "Programme signature payant et partenariats récurrents."),
    ]
    return [label for threshold, label in steps if followers < threshold]


def today() -> str:
    return date.today().isoformat()
