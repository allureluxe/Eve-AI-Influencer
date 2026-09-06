"""Liens monétisés : affiliation, boutique, lien en bio.

Règle non négociable : tout lien affilié est signalé dans la légende
(obligation FTC — « #ad » ou mention explicite). Une légende non signalée
peut coûter le partenariat et exposer à une sanction.
"""
from __future__ import annotations

import random
import urllib.parse
from dataclasses import dataclass

from eve.config import settings

AFFILIATE_DISCLOSURE_FR = "Lien affilié — je touche une petite commission, sans surcoût pour toi."
AFFILIATE_DISCLOSURE_EN = "#ad · affiliate link"


@dataclass(frozen=True)
class Offer:
    key: str
    label: str
    kind: str            # affiliate | product | service | tip
    url: str
    pillars: tuple[str, ...]
    pitch: str
    requires_disclosure: bool = False


def _utm(url: str, campaign: str, source: str) -> str:
    if not url:
        return ""
    parts = urllib.parse.urlparse(url)
    query = dict(urllib.parse.parse_qsl(parts.query))
    query.update({"utm_source": source, "utm_medium": "social",
                  "utm_campaign": campaign, "utm_content": "eve"})
    return urllib.parse.urlunparse(parts._replace(query=urllib.parse.urlencode(query)))


def build_offers() -> list[Offer]:
    """Catalogue construit depuis la config — n'expose que ce qui est renseigné.

    Aucune offre financière ici, par construction : rien concernant le
    système de trading n'est vendu, promu ou recruté.
    """
    m = settings.monetization
    offers: list[Offer] = []

    if m.linkinbio_url:
        offers.append(Offer(
            "linkinbio", "Tous mes liens", "service", m.linkinbio_url,
            ("lifestyle", "qa", "mindset"),
            "Les adresses et les pièces dont je parle sont dans le lien en bio."))
    if m.shop_url:
        offers.append(Offer(
            "shop", "La boutique", "product", m.shop_url,
            ("fashion", "lifestyle"),
            "Les pièces de la sélection sont en boutique."))
    if m.amazon_tag:
        offers.append(Offer(
            "selection", "Ma sélection", "affiliate",
            f"https://www.amazon.com/s?k=capsule+wardrobe+essentials&tag={m.amazon_tag}",
            ("fashion", "travel"),
            "Les basiques que j'utilise vraiment.",
            requires_disclosure=True))
    if m.paypal_me:
        offers.append(Offer(
            "tip", "Soutenir le compte", "tip", m.paypal_me,
            ("lifestyle", "mindset"),
            "Si le contenu te plaît, tu peux m'offrir un café."))
    return offers


def pick_offer(pillar: str, offers: list[Offer] | None = None,
               rng: random.Random | None = None) -> Offer | None:
    """Une offre pertinente pour ce pilier, sinon rien.

    Mieux vaut ne rien vendre que placer une offre hors sujet : le ratio
    valeur/promotion conditionne la portée comme la confiance.
    """
    offers = offers if offers is not None else build_offers()
    rng = rng or random
    matching = [o for o in offers if pillar in o.pillars]
    return rng.choice(matching) if matching else None


def monetization_line(offer: Offer | None, platform: str, campaign: str) -> str:
    """Ligne prête à coller en fin de légende (avec mention légale si besoin)."""
    if not offer:
        return ""
    url = _utm(offer.url, campaign, platform)
    line = f"👉 {offer.pitch}"
    if platform == "tiktok":
        line += " Lien en bio."
    elif url:
        line += f" {url}"
    if offer.requires_disclosure:
        line += f"\n{AFFILIATE_DISCLOSURE_FR} {AFFILIATE_DISCLOSURE_EN}"
    return line
