"""Calendrier éditorial : quels piliers, quels jours, quels créneaux.

Le planificateur respecte les pondérations du character bible tout en
évitant deux fois le même pilier d'affilée, et peut être ré-pondéré par le
module d'analytics (`analytics/optimizer.py`) au vu des performances.
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date as Date, timedelta

from eve.config import settings
from eve.persona.persona import Persona


@dataclass(frozen=True)
class Slot:
    day: Date
    time: str
    pillar: str

    @property
    def key(self) -> str:
        return f"{self.day.isoformat()}_{self.time.replace(':', '')}_{self.pillar}"


def _weighted_order(pillars: list[tuple[str, float]], n: int, rng: random.Random,
                    avoid_repeat: bool = True) -> list[str]:
    """Tire n piliers selon leurs poids, sans répétition immédiate."""
    keys = [k for k, _ in pillars]
    weights = [max(w, 0.001) for _, w in pillars]
    out: list[str] = []
    for _ in range(n):
        candidates, cw = keys, weights
        if avoid_repeat and out:
            filtered = [(k, w) for k, w in zip(keys, weights) if k != out[-1]]
            if filtered:
                candidates = [k for k, _ in filtered]
                cw = [w for _, w in filtered]
        out.append(rng.choices(candidates, weights=cw, k=1)[0])
    return out


def plan_days(
    persona: Persona,
    start: Date,
    days: int = 7,
    posts_per_day: int | None = None,
    weights: dict[str, float] | None = None,
    seed: int | None = None,
) -> list[Slot]:
    posts_per_day = posts_per_day or settings.publishing.posts_per_day
    times = settings.publishing.time_slots or ["07:00", "18:00"]
    rng = random.Random(seed if seed is not None else f"{start.isoformat()}:{days}")

    base = [(p.key, p.share) for p in persona.pillars]
    if weights:
        base = [(k, weights.get(k, w)) for k, w in base]

    order = _weighted_order(base, days * posts_per_day, rng)
    slots: list[Slot] = []
    i = 0
    for d in range(days):
        day = start + timedelta(days=d)
        for s in range(posts_per_day):
            time = times[s % len(times)]
            slots.append(Slot(day, time, order[i]))
            i += 1
    return slots


def summarize(slots: list[Slot]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for s in slots:
        counts[s.pillar] = counts.get(s.pillar, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))
