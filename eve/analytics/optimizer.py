"""Boucle d'apprentissage : ce qui marche est reproduit, le reste recule.

Réglage volontairement conservateur — on déplace les pondérations par petits
pas, sinon l'agent surréagit à une seule vidéo virale.
"""
from __future__ import annotations

from dataclasses import dataclass

from eve.agent.state import Store
from eve.persona.persona import Persona

MIN_SAMPLES = 3          # en dessous, on ne conclut rien
MAX_SHIFT = 0.35         # variation maximale d'un poids par cycle
FLOOR = 0.04             # aucun pilier ne descend à zéro : on garde de la variété


@dataclass
class PillarPerformance:
    pillar: str
    samples: int
    avg_views: float
    avg_engagement: float
    score: float


def performance_by_pillar(store: Store, limit: int = 300) -> list[PillarPerformance]:
    rows = store.latest_metrics(limit=limit)
    buckets: dict[str, list[dict]] = {}
    seen: set[tuple[str, str]] = set()
    for row in rows:
        key = (row["piece_id"], row["platform"])
        if key in seen:      # on ne garde que la mesure la plus récente
            continue
        seen.add(key)
        buckets.setdefault(row["pillar"], []).append(row["payload"])

    out: list[PillarPerformance] = []
    for pillar, payloads in buckets.items():
        views = [p.get("views", 0) for p in payloads]
        eng = [p.get("engagement_rate", 0.0) for p in payloads]
        avg_views = sum(views) / len(views)
        avg_eng = sum(eng) / len(eng)
        # Vues normalisées + engagement : la portée seule récompense le putaclic.
        out.append(PillarPerformance(pillar, len(payloads), round(avg_views, 1),
                                     round(avg_eng, 4), 0.0))

    max_views = max((p.avg_views for p in out), default=0.0) or 1.0
    max_eng = max((p.avg_engagement for p in out), default=0.0) or 1.0
    scored = [PillarPerformance(p.pillar, p.samples, p.avg_views, p.avg_engagement,
                                round(0.5 * p.avg_views / max_views + 0.5 * p.avg_engagement / max_eng, 4))
              for p in out]
    return sorted(scored, key=lambda p: -p.score)


def suggest_weights(persona: Persona, store: Store) -> dict[str, float]:
    """Nouvelles pondérations de piliers, normalisées à 1."""
    base = {p.key: p.share for p in persona.pillars}
    perf = {p.pillar: p for p in performance_by_pillar(store)}
    if not perf:
        return base

    scores = [p.score for p in perf.values() if p.samples >= MIN_SAMPLES]
    if not scores:
        return base
    mean = sum(scores) / len(scores)

    adjusted: dict[str, float] = {}
    for pillar, weight in base.items():
        p = perf.get(pillar)
        if not p or p.samples < MIN_SAMPLES or mean == 0:
            adjusted[pillar] = weight
            continue
        delta = max(-MAX_SHIFT, min(MAX_SHIFT, (p.score - mean) / mean))
        adjusted[pillar] = max(FLOOR, weight * (1 + delta))

    total = sum(adjusted.values()) or 1.0
    return {k: round(v / total, 4) for k, v in adjusted.items()}


def recommendations(store: Store, persona: Persona) -> list[str]:
    """Conseils lisibles par un humain, à partir des données réelles."""
    perf = performance_by_pillar(store)
    if not perf:
        return ["Pas encore assez de données publiées : continuer 7 à 14 jours avant d'optimiser."]

    labels = {p.key: p.label for p in persona.pillars}
    out = [f"Meilleur pilier : {labels.get(perf[0].pillar, perf[0].pillar)} "
           f"({perf[0].samples} posts, {perf[0].avg_views:.0f} vues moy., "
           f"{perf[0].avg_engagement * 100:.1f} % d'engagement)."]
    if len(perf) > 1:
        worst = perf[-1]
        out.append(f"Pilier le plus faible : {labels.get(worst.pillar, worst.pillar)} "
                   f"({worst.avg_views:.0f} vues moy.) — réduire la fréquence ou retravailler les hooks.")
    thin = [p.pillar for p in perf if p.samples < MIN_SAMPLES]
    if thin:
        out.append(f"Échantillon trop faible pour conclure sur : {', '.join(thin)}.")
    best_eng = max(perf, key=lambda p: p.avg_engagement)
    if best_eng.pillar != perf[0].pillar:
        out.append(f"Fort engagement mais peu de portée sur « {best_eng.pillar} » : "
                   "meilleur candidat pour une offre payante.")
    return out
