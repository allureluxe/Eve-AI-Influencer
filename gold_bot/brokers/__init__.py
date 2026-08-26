"""Lieux d'execution du robot."""
from .base import AccountInfo, Broker, BrokerError
from .bitvavo import BitvavoBroker, BitvavoConfig, RegleMarche
from .bitvavo_hardening import harden_bitvavo
from .pionex import PionexBroker, PionexConfig, PionexMarketRule
from .pionex_futures import PionexFuturesBroker, PionexFuturesConfig, PionexFuturesRule
from .paper import PaperBroker, PaperConfig

harden_bitvavo(BitvavoBroker, RegleMarche)


class _ObsoleteBroker(Broker):
    """Bouchon de compatibilite pour d'anciennes configs; jamais executable."""
    name = "obsolete"
    is_live = False

    def __init__(self, *args, **kwargs):
        raise BrokerError("Ce broker a ete retire. Utilisez Bitvavo ou Pionex.")

    def connect(self):
        return False

    def account(self):
        raise BrokerError("Broker obsolete.")

    def positions(self):
        return []

    def open_position(self, *args, **kwargs):
        raise BrokerError("Broker obsolete.")

    def modify_position(self, *args, **kwargs):
        raise BrokerError("Broker obsolete.")

    def close_position(self, *args, **kwargs):
        raise BrokerError("Broker obsolete.")


class _ObsoleteConfig:
    @classmethod
    def from_env(cls):
        raise BrokerError("Configuration obsolete. Utilisez Bitvavo ou Pionex.")


BinanceBroker = BinanceSpotBroker = MoonXBroker = OkxBroker = _ObsoleteBroker
BinanceConfig = SpotConfig = MoonXConfig = OkxConfig = _ObsoleteConfig

__all__ = [
    "Broker", "BrokerError", "AccountInfo",
    "PaperBroker", "PaperConfig",
    "BitvavoBroker", "BitvavoConfig", "RegleMarche",
    "PionexBroker", "PionexConfig", "PionexMarketRule",
    "PionexFuturesBroker", "PionexFuturesConfig", "PionexFuturesRule",
]
