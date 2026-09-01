"""Interface d'execution.

Toute la logique du robot est ecrite contre cette interface : le moteur ne
sait pas s'il parle a un simulateur ou a MoonX. Changer de lieu
d'execution ne demande donc aucune modification de la strategie.
"""
from __future__ import annotations

import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from ..core import BrokerTransaction, ClosedTrade, Position, Side, Tick
from ..universe import Instrument


class BrokerError(RuntimeError):
    """Echec d'une operation d'execution."""


@dataclass(slots=True)
class AccountInfo:
    equity: float
    balance: float
    currency: str = "EUR"
    margin_used: float = 0.0
    margin_free: float = 0.0
    leverage: float = 0.0


class Broker(ABC):
    """Contrat minimal d'un lieu d'execution."""

    name: str = "abstract"
    is_live: bool = False
    # Certains lieux d'execution ne permettent que l'achat (le spot, par
    # exemple). Le moteur doit le savoir pour ne pas proposer de ventes
    # qu'il ne pourra pas passer.
    supports_short: bool = True

    @abstractmethod
    def connect(self) -> bool:
        """Ouvre la session. Retourne False si la configuration est incomplete."""

    @abstractmethod
    def account(self) -> AccountInfo:
        """Etat du compte."""

    def reprendre(self, position: Position) -> bool:
        """Remet en gestion une position ouverte avant un redemarrage.

        Les lieux d'execution au comptant n'ont pas de notion de position :
        ils ne voient que des avoirs. Apres un redemarrage, une position
        ouverte leur est donc invisible. Son stop reste depose chez la
        plateforme — la protection survit — mais l'objectif, le break-even
        et le suivi ne sont plus assures par personne, et la place qu'elle
        occupe ne compte plus dans les plafonds.

        Les brokers concernes redeclarent ici la position memorisee ; les
        autres n'ont rien a faire, la plateforme sait ce qu'elle detient.
        """
        return False

    @abstractmethod
    def positions(self) -> list[Position]:
        """Positions actuellement ouvertes."""

    @abstractmethod
    def open_position(
        self,
        instrument: Instrument,
        side: Side,
        lots: float,
        stop_loss: float,
        take_profit: float,
        comment: str = "",
    ) -> Position:
        """Ouvre une position AU MARCHE, stop-loss et take-profit inclus."""

    @abstractmethod
    def modify_position(
        self,
        position_id: str,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> bool:
        """Deplace le stop et/ou l'objectif d'une position ouverte."""

    @abstractmethod
    def close_position(self, position_id: str, volume: Optional[float] = None,
                       reason: str = "") -> Optional[ClosedTrade]:
        """Ferme tout ou partie d'une position."""

    # --- optionnel ---
    def sync(self) -> None:
        """Rafraichit l'etat depuis le lieu d'execution (positions, compte)."""

    def closed_trades(self) -> list[ClosedTrade]:
        return []

    def recent_transactions(self, since: float = 0.0) -> list[BrokerTransaction]:
        return []

    def healthy(self) -> bool:
        return True


def new_position_id() -> str:
    return uuid.uuid4().hex[:12]
