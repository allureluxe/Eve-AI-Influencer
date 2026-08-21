"""Univers d'instruments scannes par le robot.

Le robot est libre du choix du produit : il evalue tous les instruments
actifs et ne prend que la meilleure opportunite validee. L'or reste
prioritaire (poids de conviction plus eleve), mais si aucun facteur n'est
valide sur XAUUSD il bascule sur une autre paire ou une crypto.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass(slots=True)
class Instrument:
    """Definition d'un instrument tradable."""

    symbol: str
    asset_class: str          # "metal" | "forex" | "crypto" | "index" | "energy"
    digits: int               # decimales de cotation
    contract_size: float      # unites par lot (valeur d'1.0 de variation de prix par lot)
    min_lot: float
    lot_step: float
    max_lot: float
    round_step: float         # pas des chiffres ronds psychologiques
    typical_spread: float     # spread normal, en prix
    max_spread: float         # au-dela : on ne trade pas
    sessions: tuple[tuple[int, int], ...] = ()   # fenetres UTC (heure debut, heure fin), vide = 24/7
    weekend: bool = False     # tradable le week-end (crypto)
    priority: float = 1.0     # multiplicateur de conviction (l'or est privilegie)
    quote_currency: str = "USD"
    enabled: bool = True
    # Correlations connues, pour ne pas empiler des risques identiques
    correlation_group: str = ""

    def normalize_lot(self, lot: float, round_down: bool = False) -> float:
        """Aligne un volume sur le pas du broker.

        `round_down=True` arrondit vers le bas : c'est ce qu'il faut pour
        dimensionner une position. Arrondir au plus proche peut faire
        depasser le risque vise (0.065 -> 0.07 lot, soit 8 % de risque en
        plus que prevu). Sur le risque, on arrondit toujours en sa faveur.
        """
        if lot <= 0:
            return 0.0
        ratio = lot / self.lot_step
        steps = math.floor(ratio + 1e-9) if round_down else round(ratio)
        lot = max(self.min_lot, min(self.max_lot, steps * self.lot_step))
        return round(lot, 8)

    def value_per_price_unit(self, lots: float) -> float:
        """Combien vaut 1.0 de variation de prix pour ce volume (en devise du compte)."""
        return lots * self.contract_size

    def is_open(self, ts: Optional[float] = None) -> bool:
        """Le marche est-il ouvert a cet instant (UTC) ?"""
        dt = datetime.fromtimestamp(ts, tz=timezone.utc) if ts else datetime.now(timezone.utc)
        weekday = dt.weekday()   # 0 = lundi, 5 = samedi, 6 = dimanche

        if not self.weekend:
            # Le forex/metaux ouvrent dimanche 22h UTC et ferment vendredi 21h UTC.
            if weekday == 5:
                return False
            if weekday == 6 and dt.hour < 22:
                return False
            if weekday == 4 and dt.hour >= 21:
                return False

        if not self.sessions:
            return True
        hour = dt.hour + dt.minute / 60.0
        for start, end in self.sessions:
            if start <= end:
                if start <= hour < end:
                    return True
            else:  # session qui passe minuit
                if hour >= start or hour < end:
                    return True
        return False


# Sessions UTC : Londres 07h-16h, New York 12h-21h.
# Le chevauchement 12h-16h concentre l'essentiel du volume sur l'or et le forex.
LONDON_NY = ((7, 21),)
LONDON_NY_OVERLAP = ((12, 17),)


DEFAULT_UNIVERSE: list[Instrument] = [
    # --- Metaux : coeur du systeme ---
    Instrument("XAUUSD", "metal", 2, 100.0, 0.01, 0.01, 50.0, 10.0, 0.30, 0.60,
               sessions=LONDON_NY, priority=1.25, correlation_group="metals"),
    Instrument("XAGUSD", "metal", 3, 5000.0, 0.01, 0.01, 30.0, 0.50, 0.020, 0.045,
               sessions=LONDON_NY, priority=1.0, correlation_group="metals"),

    # --- Forex majeur : liquide, spreads serres ---
    Instrument("EURUSD", "forex", 5, 100000.0, 0.01, 0.01, 50.0, 0.0100, 0.00008, 0.00025,
               sessions=LONDON_NY, priority=1.0, correlation_group="usd_major"),
    Instrument("GBPUSD", "forex", 5, 100000.0, 0.01, 0.01, 50.0, 0.0100, 0.00012, 0.00035,
               sessions=LONDON_NY, priority=0.95, correlation_group="usd_major"),
    Instrument("USDJPY", "forex", 3, 100000.0, 0.01, 0.01, 50.0, 1.0, 0.010, 0.030,
               sessions=LONDON_NY, priority=0.95, correlation_group="usd_yen", quote_currency="JPY"),
    Instrument("AUDUSD", "forex", 5, 100000.0, 0.01, 0.01, 50.0, 0.0100, 0.00012, 0.00035,
               sessions=LONDON_NY, priority=0.85, correlation_group="commodity_fx"),
    Instrument("USDCAD", "forex", 5, 100000.0, 0.01, 0.01, 50.0, 0.0100, 0.00015, 0.00040,
               sessions=LONDON_NY, priority=0.8, correlation_group="commodity_fx", quote_currency="CAD"),

    # --- Crypto : prend le relais la nuit et le week-end (24/7) ---
    Instrument("BTCUSD", "crypto", 2, 1.0, 0.001, 0.001, 20.0, 1000.0, 8.0, 30.0,
               weekend=True, priority=1.05, correlation_group="crypto"),
    Instrument("ETHUSD", "crypto", 2, 1.0, 0.01, 0.01, 200.0, 50.0, 0.60, 2.50,
               weekend=True, priority=1.0, correlation_group="crypto"),
    Instrument("SOLUSD", "crypto", 3, 1.0, 0.1, 0.1, 2000.0, 5.0, 0.05, 0.25,
               weekend=True, priority=0.9, correlation_group="crypto"),
    Instrument("XRPUSD", "crypto", 4, 1.0, 1.0, 1.0, 100000.0, 0.10, 0.0008, 0.0035,
               weekend=True, priority=0.8, correlation_group="crypto"),
]


class Universe:
    """Registre des instruments, avec filtrage par disponibilite."""

    def __init__(self, instruments: Optional[list[Instrument]] = None) -> None:
        self._items: dict[str, Instrument] = {}
        for inst in (instruments if instruments is not None else DEFAULT_UNIVERSE):
            self._items[inst.symbol] = inst

    def __iter__(self):
        return iter(self._items.values())

    def __len__(self) -> int:
        return len(self._items)

    def get(self, symbol: str) -> Optional[Instrument]:
        return self._items.get(symbol)

    def add(self, inst: Instrument) -> None:
        self._items[inst.symbol] = inst

    def enable_only(self, symbols: list[str]) -> None:
        for sym, inst in self._items.items():
            inst.enabled = sym in symbols

    def tradable(self, ts: Optional[float] = None) -> list[Instrument]:
        """Instruments actifs et dont le marche est ouvert maintenant.

        C'est ce qui permet au robot de tourner 24h/24 : quand le forex et
        l'or ferment, seules les cryptos restent dans la liste.
        """
        return [i for i in self._items.values() if i.enabled and i.is_open(ts)]

    def symbols(self) -> list[str]:
        return list(self._items.keys())
