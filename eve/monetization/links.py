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
    """Catalogue construit depuis la config — n'expose que ce qui est renseigné."""
    m = settings.monetization
    offers: list[Offer] = []

    if m.linkinbio_url:
        offers.append(Offer(
            "linkinbio", "Tous mes programmes", "service", m.linkinbio_url,
            ("motivation", "quick_workout", "qa"),
            "Programmes, guides et liens : tout est dans le lien en bio."))
    if m.shop_url:
        offers.append(Offer(
            "shop", "Boutique", "product", m.shop_url,
            ("lifestyle", "motivation"),
            "Mes essentiels d'entraînement sont en boutique."))
    if m.stripe_payment_link:
        offers.append(Offer(
            "program_4w", "Programme 4 semaines (PDF)", "product", m.stripe_payment_link,
            ("quick_workout", "form_check", "motivation"),
            "Le programme complet 4 semaines en PDF est dispo."))
    if m.amazon_tag:
        offers.append(Offer(
            "gear", "Matériel de base", "affiliate",
            f"https://www.amazon.com/s?k=resistance+bands&tag={m.amazon_tag}",
            ("quick_workout", "form_check"),
            "Les élastiques que j'utilise (moins de 20 $).",
            requires_disclosure=True))
    if m.paypal_me:
        offers.append(Offer(
            "tip", "Soutenir la chaîne", "tip", m.paypal_me,
            ("motivation", "lifestyle"),
            "Si le contenu t'aide, tu peux m'offrir un café."))
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
