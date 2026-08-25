"""Lieux d'execution disponibles."""
from .base import AccountInfo, Broker, BrokerError
from .binance import BinanceBroker, BinanceConfig
from .binance_spot import BinanceSpotBroker, SpotConfig
from .bitvavo import BitvavoBroker, BitvavoConfig
from .bitvavo_hardening import harden_bitvavo
from .moonx import MoonXBroker, MoonXConfig
from .okx import OkxBroker, OkxConfig
from .paper import PaperBroker, PaperConfig

# Active les garde-fous Bitvavo apres le chargement des classes, avant toute
# construction de broker : tickSize reel et annulation ciblee des stops.
harden_bitvavo(BitvavoBroker, __import__(
    ".bitvavo", globals(), locals(), ["RegleMarche"], 1).RegleMarche)

__all__ = ["Broker", "BrokerError", "AccountInfo",
           "PaperBroker", "PaperConfig",
           "MoonXBroker", "MoonXConfig",
           "BinanceBroker", "BinanceConfig",
           "BinanceSpotBroker", "SpotConfig",
           "BitvavoBroker", "BitvavoConfig",
           "OkxBroker", "OkxConfig"]
