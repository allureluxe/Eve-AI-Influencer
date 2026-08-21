"""Collecte des métriques des publications déjà en ligne."""
from __future__ import annotations

import logging

from eve.agent.state import Store
from eve.publishing.instagram import InstagramPublisher
from eve.publishing.tiktok import TikTokPublisher

log = logging.getLogger(__name__)

# Normalisation : chaque plateforme nomme ses métriques différemment.
ALIASES = {
    "views": ("views", "view_count", "video_views", "plays", "reach"),
    "likes": ("likes", "like_count"),
    "comments": ("comments", "comment_count"),
    "shares": ("shares", "share_count"),
    "saves": ("saved", "save_count"),
}


def normalize(raw: dict) -> dict:
    out = {}
    for key, candidates in ALIASES.items():
        for c in candidates:
            if c in raw and isinstance(raw[c], (int, float)):
                out[key] = raw[c]
                break
        out.setdefault(key, 0)
    views = out["views"] or 0
    interactions = out["likes"] + out["comments"] + out["shares"] + out["saves"]
    out["interactions"] = interactions
    out["engagement_rate"] = round(interactions / views, 4) if views else 0.0
    return out


def collect(store: Store, limit: int = 50) -> int:
    """Récupère les métriques des publications réelles (les dry-runs sont ignorés)."""
    publishers = {"instagram": InstagramPublisher(), "tiktok": TikTokPublisher()}
    collected = 0
    for pub in store.publications(limit=limit, only_live=True):
        publisher = publishers.get(pub["platform"])
        if not publisher or not publisher.configured or not pub["post_id"]:
            continue
        raw = publisher.fetch_metrics(pub["post_id"])
        if not raw:
            continue
        store.record_metrics(pub["piece_id"], pub["platform"], normalize(raw) | {"raw": raw})
        collected += 1
    log.info("Métriques collectées pour %d publication(s).", collected)
    return collected
