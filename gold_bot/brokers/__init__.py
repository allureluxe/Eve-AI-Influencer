"""Lieux d'execution du robot.

Bitvavo est le seul broker de production supporte par le projet.
Les anciens connecteurs Binance, MoonX et OKX ont ete retires. Les noms de
compatibilite ci-dessous evitent qu'une ancienne configuration chargee par
un processus ne provoque un ImportError ; ils refusent toute tentative
d'utilisation.
"""
from .base import AccountInfo, Broker, BrokerError
from .bitvavo import BitvavoBroker, BitvavoConfig, RegleMarche
from .bitvavo_hardening import harden_bitvavo
from .paper import PaperBroker, PaperConfig

harden_bitvavo(BitvavoBroker, RegleMarche)


class _ObsoleteBroker(Broker):
    name = "obsolete"
    is_live = False

    def __init__(self, *args, **kwargs):
        raise BrokerError("Ce broker a ete retire. Utilisez exclusivement Bitvavo.")

    def connect(self):
        return False

    def account(self):
        raise BrokerError("Broker obsolete.")

    def positions(self):
        return []


class _ObsoleteConfig:
    @classmethod
    def from_env(cls):
        raise BrokerError("Configuration obsolete. Utilisez exclusivement Bitvavo.")


# Compatibilite d'import uniquement : aucun de ces connecteurs n'est executable.
BinanceBroker = BinanceSpotBroker = MoonXBroker = OkxBroker = _ObsoleteBroker
BinanceConfig = SpotConfig = MoonXConfig = OkxConfig = _ObsoleteConfig

__all__ = [
    "Broker", "BrokerError", "AccountInfo",
    "PaperBroker", "PaperConfig",
    "BitvavoBroker", "BitvavoConfig", "RegleMarche",
]
