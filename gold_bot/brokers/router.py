"""Routage multi-broker avec isolation des pannes."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Iterable

from .base import Broker, BrokerError


@dataclass
class BrokerState:
    broker: Broker
    failures: int = 0
    blocked_until: float = 0.0
    last_error: str = ""

    @property
    def available(self) -> bool:
        return time.time() >= self.blocked_until


class BrokerRouter:
    """Un moteur principal, plusieurs brokers indépendants.

    Une panne d'un broker ne propage jamais d'exception au reste du pool.
    Le routeur bloque temporairement le broker fautif puis le reteste.
    """

    def __init__(self, brokers: Iterable[Broker], cooldown: float = 60.0,
                 max_failures: int = 3) -> None:
        self.cooldown = max(5.0, cooldown)
        self.max_failures = max(1, max_failures)
        self.states = {b.name: BrokerState(b) for b in brokers}

    def connect_all(self) -> dict[str, bool]:
        result: dict[str, bool] = {}
        for name, state in self.states.items():
            try:
                result[name] = bool(state.broker.connect())
                if result[name]:
                    state.failures = 0
                    state.last_error = ""
                else:
                    self._fail(state, "connexion refusée")
            except Exception as exc:
                result[name] = False
                self._fail(state, str(exc))
        return result

    def healthy(self) -> dict[str, bool]:
        result: dict[str, bool] = {}
        for name, state in self.states.items():
            if not state.available:
                result[name] = False
                continue
            try:
                result[name] = bool(state.broker.healthy())
            except Exception as exc:
                self._fail(state, str(exc))
                result[name] = False
        return result

    def available(self, predicate: Callable[[Broker], bool] | None = None) -> list[Broker]:
        out: list[Broker] = []
        for state in self.states.values():
            if not state.available:
                continue
            if predicate is not None and not predicate(state.broker):
                continue
            try:
                if state.broker.healthy():
                    out.append(state.broker)
            except Exception as exc:
                self._fail(state, str(exc))
        return out

    def call(self, broker_name: str, method: str, *args, **kwargs):
        state = self.states[broker_name]
        if not state.available:
            raise BrokerError(f"broker {broker_name} temporairement isolé")
        try:
            value = getattr(state.broker, method)(*args, **kwargs)
            state.failures = 0
            state.last_error = ""
            return value
        except Exception as exc:
            self._fail(state, str(exc))
            raise

    def _fail(self, state: BrokerState, error: str) -> None:
        state.failures += 1
        state.last_error = error[:500]
        if state.failures >= self.max_failures:
            state.blocked_until = time.time() + self.cooldown

    def status(self) -> dict[str, dict]:
        return {
            name: {
                "available": state.available,
                "failures": state.failures,
                "last_error": state.last_error,
                "blocked_until": state.blocked_until,
            }
            for name, state in self.states.items()
        }
