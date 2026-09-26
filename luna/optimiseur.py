"""Boucle d'apprentissage simple pour la strategie Luna.

Le score favorise les signaux utiles a la croissance : completion video,
partages/sauvegardes et conversion en followers. Les chiffres restent
descriptifs : ils servent a modifier la production, pas a garantir un resultat.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Performance:
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0
    saves: int = 0
    completion_rate: float | None = None
    followers_delta: int = 0


def score(p: Performance) -> float:
    if p.views <= 0:
        return 0.0
    engagement = (p.likes + 2*p.comments + 3*p.shares + 3*p.saves) / p.views
    completion = (p.completion_rate or 0.0) / 100.0
    conversion = max(0.0, p.followers_delta) / p.views * 1000
    return 0.45 * engagement + 0.40 * completion + 0.15 * min(conversion, 10.0)


def recommander(rows: list[dict]) -> dict:
    scores = []
    for row in rows:
        p = Performance(
            views=int(row.get("views") or 0),
            likes=int(row.get("likes") or 0),
            comments=int(row.get("comments") or 0),
            shares=int(row.get("shares") or 0),
            saves=int(row.get("saves") or 0),
            completion_rate=float(row["completion_rate"])
                if row.get("completion_rate") is not None else None,
            followers_delta=int(row.get("followers_delta") or 0),
        )
        scores.append((score(p), row))
    scores.sort(key=lambda x: x[0], reverse=True)

    formats = {}
    pillars = {}
    for sc, row in scores[:30]:
        fmt = row.get("content_format") or "unknown"
        pillar = row.get("pillar") or "unknown"
        formats[fmt] = formats.get(fmt, 0.0) + sc
        pillars[pillar] = pillars.get(pillar, 0.0) + sc

    return {
        "top": scores[:10],
        "formats": dict(sorted(formats.items(), key=lambda x: x[1], reverse=True)),
        "piliers": dict(sorted(pillars.items(), key=lambda x: x[1], reverse=True)),
    }
