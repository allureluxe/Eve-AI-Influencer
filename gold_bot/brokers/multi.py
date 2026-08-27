"""Multi-broker orchestration with isolated broker failures.

The router never sends an order itself: it delegates to one selected worker and
keeps broker health independent.  Concrete workers can be registered later
without changing the strategy/risk layer.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class BrokerHealth:
    name: str
    failures: int = 0
    blocked_until: float = 0.0
    last_error: str | None = None

    @property
    def available(self) -> bool:
        return time.monotonic() >= self.blocked_until

    def success(self) -> None:
        self.failures = 0
        self.blocked_until = 0.0
        self.last_error = None

    def failure(self, error: Exception, cooldown: float = 30.0) -> None:
        self.failures += 1
        self.last_error = f"{type(error).__name__}: {error}"
        self.blocked_until = time.monotonic() + min(cooldown * (2 ** (self.failures - 1)), 900.0)


@dataclass
class MultiBrokerRouter:
    """Broker router with per-broker circuit breakers."""
    workers: dict[str, Any] = field(default_factory=dict)
    health: dict[str, BrokerHealth] = field(default_factory=dict)

    def register(self, name: str, worker: Any) -> None:
        key = name.lower()
        self.workers[key] = worker
        self.health[key] = BrokerHealth(key)

    def available(self) -> list[str]:
        return [n for n in self.workers if self.health[n].available]

    def call(self, name: str, method: str, *args: Any, **kwargs: Any) -> Any:
        key = name.lower()
        if key not in self.workers:
            raise KeyError(f"Broker inconnu: {name}")
        if not self.health[key].available:
            raise RuntimeError(f"Broker {key} temporairement isole")
        try:
            result = getattr(self.workers[key], method)(*args, **kwargs)
            self.health[key].success()
            return result
        except Exception as exc:
            self.health[key].failure(exc)
            raise

    def snapshot(self) -> dict[str, dict[str, Any]]:
        return {
            name: {
                "available": self.health[name].available,
                "failures": self.health[name].failures,
                "last_error": self.health[name].last_error,
            }
            for name in self.workers
        }
