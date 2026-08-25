"""Lieux d'execution du robot.

Bitvavo est le seul broker de production supporte par le projet.
Les anciens connecteurs Binance, MoonX et OKX ont ete retires.
"""
from .base import AccountInfo, Broker, BrokerError
from .bitvavo import BitvavoBroker, BitvavoConfig, RegleMarche
from .bitvavo_hardening import harden_bitvavo
from .paper import PaperBroker, PaperConfig

harden_bitvavo(BitvavoBroker, RegleMarche)

__all__ = [
    "Broker", "BrokerError", "AccountInfo",
    "PaperBroker", "PaperConfig",
    "BitvavoBroker", "BitvavoConfig", "RegleMarche",
]
